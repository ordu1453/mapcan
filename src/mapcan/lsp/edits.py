"""Правки текста карты для языкового сервера: быстрые исправления, переименование и ссылки,
добавление, копирование и удаление узлов.

Правки строятся по тексту с сохранением отступов, комментариев и стиля записи (блок или «{…}»).
Позиции 0-based, как в :mod:`mapcan.lsp.analysis`.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .. import model as M
from ..bits import occupied_bits
from ..canopen import CANOPEN_DLC, FUNCTION_CODES, compute_id
from ..i18n import _
from ..units import UNITS
from ..validate import STYLE_RE
from .analysis import Analysis, Path_, Pos, _txt, doc_language, enum_choices, model_for

_PLAIN = re.compile(r"^[A-Za-z0-9_.+-]+$")


@dataclass
class Edit:
    start: Pos
    end: Pos
    text: str


@dataclass
class Action:
    title: str
    edits: list[Edit]
    preferred: bool = False
    diagnostics: list[int] = field(default_factory=list)   # индексы исправляемых диагностик


def yaml_scalar(value: str) -> str:
    """Строка для записи в YAML: как есть, если это простое слово, иначе в двойных кавычках."""
    if _PLAIN.match(value) and not re.fullmatch(r"(?i)true|false|yes|no|on|off|null|~|[-+]?[\d.]+(e[-+]?\d+)?", value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# --------------------------------------------------------------------------- #
# Доступ к узлам
# --------------------------------------------------------------------------- #


def raw_at(a: Analysis, path: Path_):
    obj = a.result.raw
    for el in path:
        try:
            obj = obj[el]
        except (KeyError, IndexError, TypeError):
            return None
    return obj


def value_range(a: Analysis, path: Path_) -> tuple[Pos, Pos] | None:
    n = a.nodes.get(path)
    return (n.start, a.token_end(n.start)) if n else None


def key_range(a: Analysis, path: Path_) -> tuple[Pos, Pos] | None:
    """Позиция ключа ``path[-1]`` (слева от значения на той же строке)."""
    n = a.nodes.get(path)
    if n is None or not path or isinstance(path[-1], int):
        return None
    line, col = n.start
    key = re.escape(str(path[-1]))
    m = re.search(rf"({key})\s*:\s*$", a.lines[line][:col])
    if m:
        return (line, m.start(1)), (line, m.end(1))
    # Блочный список или словарь: значение начинается со следующей строки, ключ — выше
    if a.lines[line][:col].strip() in ("", "-"):
        for i in range(line - 1, -1, -1):
            m = re.match(rf"^\s*(?:-\s+)?({key})\s*:\s*(?:#.*)?$", a.lines[i])
            if m:
                return (i, m.start(1)), (i, m.end(1))
            if a.lines[i].strip() and not a.lines[i].lstrip().startswith("#"):
                break
    return None


def _is_flow(a: Analysis, path: Path_) -> bool:
    n = a.nodes.get(path)
    return n is not None and a.lines[n.start[0]][n.start[1]:n.start[1] + 1] in ("{", "[")


def set_value(a: Analysis, path: Path_, text: str) -> list[Edit]:
    """Заменить скалярное значение или добавить ключ в родительский словарь."""
    if path in a.nodes and not isinstance(raw_at(a, path), (dict, list)):
        start, end = value_range(a, path)
        return [Edit(start, end, text)]
    return insert_key(a, path[:-1], str(path[-1]), text)


def insert_key(a: Analysis, map_path: Path_, key: str, text: str) -> list[Edit]:
    n = a.nodes.get(map_path)
    if n is None:
        return []
    if _is_flow(a, map_path):
        close = a._closing(n.start)
        if close is None:
            return []
        pos = (close[0], close[1] - 1)
        return [Edit(pos, pos, f", {key}: {text}")]
    _, (end_line, _end_col) = a.block(map_path)
    pos = (end_line + 1, 0)
    return [Edit(pos, pos, f"{' ' * n.start[1]}{key}: {text}\n")]


def delete_key(a: Analysis, path: Path_) -> list[Edit]:
    """Удалить ключ со скалярным значением, если он записан на отдельной строке или внутри «{…}»."""
    kr = key_range(a, path)
    vr = value_range(a, path)
    if kr is None or vr is None:
        return []
    (line, kcol), (_, vend) = kr[0], vr[1]
    text = a.lines[line]
    if _is_flow(a, path[:-1]):
        after = re.match(r"\s*,\s*", text[vend:])
        if after:
            return [Edit((line, kcol), (line, vend + after.end()), "")]
        before = re.search(r",\s*$", text[:kcol])
        return [Edit((line, before.start() if before else kcol), (line, vend), "")]
    if text[:kcol].strip():
        return []      # ключ на строке «- …» или после другого ключа
    return [Edit((line, 0), (line + 1, 0), "")]


# --------------------------------------------------------------------------- #
# Быстрые исправления
# --------------------------------------------------------------------------- #


def _suggest(word: str, options, cutoff: float = 0.6) -> list[str]:
    return difflib.get_close_matches(word, [o for o in options if o != word], n=3, cutoff=cutoff)


def _bus_devices(a: Analysis, path: Path_) -> list[str]:
    devices = raw_at(a, path[:2] + ("devices",)) if len(path) >= 2 else None
    return [d["name"] for d in devices or [] if isinstance(d, dict) and isinstance(d.get("name"), str)]


def to_style(name: str, style: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])", name) if w]
    if style == "snake_case":
        return "_".join(w.lower() for w in words)
    if style == "UPPER_SNAKE":
        return "_".join(w.upper() for w in words)
    if style == "camelCase":
        return words[0].lower() + "".join(w.capitalize() for w in words[1:]) if words else name
    if style == "PascalCase":
        return "".join(w.capitalize() for w in words)
    return name


def quick_fixes(a: Analysis, diags: list[tuple[str, list, Pos]]) -> list[Action]:
    """Исправления для диагностик (код, путь узла, начало); ``Action.diagnostics`` — их индексы."""
    out: list[Action] = []
    for i, (code, node, start) in enumerate(diags):
        path = tuple(node or ())
        acts = _yaml_fixes(a, start) if code == "yaml" else _fixes_for(a, code, path)
        for act in acts:
            act.diagnostics = [i]
            out.append(act)
    return out


def _fixes_for(a: Analysis, code: str, path: Path_) -> list[Action]:
    n = a.nodes.get(path)
    if code in ("number-comma", "number-cyrillic-x", "number-quoted") and n:
        line, col = n.start
        text = a.lines[line][col:]
        patterns = {
            "number-comma": (r"[+-]?\d+,\d+", lambda s: s.replace(",", ".")),
            "number-cyrillic-x": (r"0[хХ][0-9a-fA-F]+", lambda s: "0x" + s[2:]),
            "number-quoted": (r"""(["'])\s*0[xX][0-9a-fA-F]+\s*\1""", lambda s: s[1:-1].strip()),
        }
        pattern, fix = patterns[code]
        m = re.match(pattern, text)
        if m:
            new = fix(m.group(0))
            return [Action(_("Заменить на {value}", value=new),
                           [Edit((line, col), (line, col + m.end()), new)], preferred=True)]
        return []

    if code == "unknown-receiver" or code == "unknown-sender":
        value = raw_at(a, path)
        vr = value_range(a, path)
        if not isinstance(value, str) or vr is None:
            return []
        return [Action(_("Заменить на {value!r}", value=s), [Edit(*vr, s)], preferred=k == 0)
                for k, s in enumerate(_suggest(value, _bus_devices(a, path), 0.4))]

    if code == "schema" and path and isinstance(path[-1], str):
        key = path[-1]
        cls = model_for(path[:-1])
        if cls is not None and key not in cls.model_fields:
            kr = key_range(a, path)
            fields = [f for f in cls.model_fields if not f.startswith("_")]
            return [Action(_("Заменить на {value!r}", value=s), [Edit(*kr, s)], preferred=k == 0)
                    for k, s in enumerate(_suggest(key, fields))] if kr else []
        value = raw_at(a, path)
        choices = enum_choices().get(key) if cls is not None and key in cls.model_fields else None
        vr = value_range(a, path)
        if isinstance(value, str) and choices and value not in choices and vr:
            return [Action(_("Заменить на {value!r}", value=s), [Edit(*vr, s)], preferred=k == 0)
                    for k, s in enumerate(_suggest(value, choices, 0.4))]
        return []

    if code == "can-id-range" and path and path[-1] == "id":
        return [Action(_("Добавить extended: true"), set_value(a, path[:-1] + ("extended",), "true"),
                       preferred=True)]

    if code == "j1939-destination":
        edits = delete_key(a, path) if path and path[-1] == "destination" else []
        return [Action(_("Удалить destination"), edits)] if edits else []

    if code == "history-version":
        hv = value_range(a, ("document", "history", 0, "version"))
        if hv and ("document", "version") in a.nodes:
            latest = a.lines[hv[0][0]][hv[0][1]:hv[1][1]]
            return [Action(_("Заменить на {value}", value=latest),
                           set_value(a, ("document", "version"), latest), preferred=True)]
        return []

    if code == "name-style" and path:
        name = raw_at(a, path)
        style = _style_for(a, path)
        if isinstance(name, str) and style:
            new = to_style(name, style)
            if new and new != name and STYLE_RE[style].match(new):
                edits = rename_edits(a, path, new) if path[-1] == "name" else _rename_key(a, path, new)
                return [Action(_("Переименовать в {value!r}", value=new), edits, preferred=True)] if edits else []
        return []

    if code in ("bit-overlap", "signal-out-of-frame"):
        act = move_to_free_bits(a, path)
        return [act] if act else []

    if code == "duplicate-can-id" and path and path[-1] == "type":
        # Другой тип того же назначения (PDO TX → свободный PDO TX), чей ID не занят
        current = raw_at(a, path)
        prefix = re.sub(r"\d+$", "", current) if isinstance(current, str) else ""
        free = [t["type"] for t in frame_types(a, path[:-1])
                if t["taken"] is None and t["type"] != current and prefix.startswith("pdo_")
                and t["type"].startswith(prefix)]
        vr = value_range(a, path)
        return [Action(_("Заменить тип на {value}", value=t), [Edit(*vr, t)], preferred=k == 0)
                for k, t in enumerate(free)] if vr else []
    return []


def _yaml_fixes(a: Analysis, start: Pos) -> list[Action]:
    """«-name: x» вместо «- name: x»: элемент списка без пробела после «-»."""
    line = start[0]
    m = re.match(r"^(\s*)-(?=[A-Za-z_\"'{\[])", a.lines[line]) if line < len(a.lines) else None
    if not m:
        return []
    pos = (line, m.end())
    return [Action(_("Вставить пробел после «-»"), [Edit(pos, pos, " ")], preferred=True)]


def _style_for(a: Analysis, path: Path_) -> str | None:
    lint = a.map.lint if a.map else M.LintRules()
    if "values" in path:
        return lint.value_name
    owner = path[-3] if len(path) >= 3 and path[-1] == "name" else None
    return {"signals": lint.signal_name, "flags": lint.signal_name, "frames": lint.frame_name,
            "devices": lint.device_name}.get(owner)


def _rename_key(a: Analysis, path: Path_, new: str) -> list[Edit]:
    """Имя значения enum — это значение ``name`` или сама строка значения."""
    vr = value_range(a, path + ("name",)) if (path + ("name",)) in a.nodes else value_range(a, path)
    return [Edit(*vr, yaml_scalar(new))] if vr else []


# --------------------------------------------------------------------------- #
# Свободные биты
# --------------------------------------------------------------------------- #


def _coexist(a: M.Signal, b: M.Signal) -> bool:
    if a.mux is None or b.mux is None:
        return True
    return bool(set(a.mux_values) & set(b.mux_values))


def free_start(frame: M.Frame, length: int, step: int, skip: M.Signal | None = None) -> int | None:
    """Первая позиция (кратная ``step``) little-endian поля длиной ``length`` без пересечений."""
    taken: set[int] = set()
    for s in frame.signals:
        if s is not skip and (skip is None or _coexist(s, skip)):
            taken.update(occupied_bits(s.start_bit or 0, s.bit_length or 1, s.byte_order == "big_endian"))
    for start in range(0, frame.dlc * 8 - length + 1, step):
        if not taken & set(range(start, start + length)):
            return start
    return None


def move_to_free_bits(a: Analysis, path: Path_) -> Action | None:
    if a.map is None or len(path) < 2 or path[-2] != "signals":
        return None
    frame = _find(a.map, path[:-2])
    sig = _find(a.map, path)
    raw = raw_at(a, path)
    if not isinstance(frame, M.Frame) or not isinstance(sig, M.Signal) or not isinstance(raw, dict):
        return None
    if sig.byte_order == "big_endian":
        return None
    length = sig.bit_length or 1
    if "start_bit" in raw:
        start = free_start(frame, length, 1, sig)
        edits = set_value(a, path + ("start_bit",), str(start)) if start is not None else []
    elif "bit" in raw:
        start = free_start(frame, length, 1, sig)
        edits = [] if start is None else (set_value(a, path + ("byte",), str(start // 8))
                                          + set_value(a, path + ("bit",), str(start % 8)))
    else:
        # Без «bit» поле начинается с границы байта; добавить «bit» нельзя — изменилась бы длина по умолчанию
        start = free_start(frame, length, 8, sig)
        edits = set_value(a, path + ("byte",), str(start // 8)) if start is not None else []
    if not edits:
        return None
    hi = start + length - 1
    bits = _("бит {bit}", bit=start) if length == 1 else _("биты {lo}–{hi}", lo=start, hi=hi)
    return Action(_("Переместить на свободные биты: {bits}", bits=bits), edits, preferred=True)


def _find(cmap: M.MapCan, path: Path_):
    obj = cmap
    for el in path:
        try:
            obj = obj[el] if isinstance(el, int) else getattr(obj, el)
        except (IndexError, AttributeError, TypeError):
            return None
    return obj


# --------------------------------------------------------------------------- #
# Ссылки на устройства, переименование
# --------------------------------------------------------------------------- #


def _frame_paths(a: Analysis, bus_path: Path_) -> list[Path_]:
    out = [bus_path + ("frames", i) for i, _ in enumerate(raw_at(a, bus_path + ("frames",)) or [])]
    for di, dev in enumerate(raw_at(a, bus_path + ("devices",)) or []):
        frames = dev.get("frames") if isinstance(dev, dict) else None
        out += [bus_path + ("devices", di, "frames", i) for i, _ in enumerate(frames or [])]
    return out


def device_refs(a: Analysis, bus_path: Path_, name: str) -> tuple[Path_ | None, list[Path_]]:
    """(объявление устройства, ссылки на него в receivers и sender) на шине."""
    decl = None
    for di, dev in enumerate(raw_at(a, bus_path + ("devices",)) or []):
        if isinstance(dev, dict) and dev.get("name") == name:
            decl = bus_path + ("devices", di, "name")
            break
    refs = []
    for fp in _frame_paths(a, bus_path):
        frame = raw_at(a, fp)
        if not isinstance(frame, dict):
            continue
        for i, r in enumerate(frame.get("receivers") or []):
            if r == name and fp + ("receivers", i) in a.nodes:
                refs.append(fp + ("receivers", i))
        if frame.get("sender") == name and fp + ("sender",) in a.nodes:
            refs.append(fp + ("sender",))
    return decl, refs


def name_at(a: Analysis, pos: Pos) -> Path_ | None:
    """Путь имени под курсором: ``…name`` любого узла или ссылка на устройство в receivers/sender."""
    for path, n in a.nodes.items():
        if not path or n.start[0] != pos[0]:
            continue
        is_name = path[-1] == "name" and isinstance(raw_at(a, path), str)
        is_ref = (path[-1] == "sender" or (len(path) >= 2 and path[-2] == "receivers")) \
            and isinstance(raw_at(a, path), str)
        if (is_name or is_ref) and n.start <= pos <= a.token_end(n.start):
            return path
    return None


def _device_target(a: Analysis, path: Path_) -> tuple[Path_, str] | None:
    """(путь шины, имя устройства), если ``path`` — имя устройства или ссылка на него."""
    if len(path) < 2 or path[0] != "buses":
        return None
    value = raw_at(a, path)
    is_decl = len(path) == 5 and path[2] == "devices" and path[4] == "name"
    is_ref = path[-1] == "sender" or (len(path) >= 2 and path[-2] == "receivers")
    return (path[:2], value) if (is_decl or is_ref) and isinstance(value, str) else None


def definition(a: Analysis, pos: Pos) -> tuple[Pos, Pos] | None:
    path = name_at(a, pos)
    target = _device_target(a, path) if path else None
    if target is None:
        return None
    decl, _refs = device_refs(a, *target)
    return value_range(a, decl) if decl else None


def references(a: Analysis, pos: Pos, include_declaration: bool = True) -> list[tuple[Pos, Pos]]:
    path = name_at(a, pos)
    target = _device_target(a, path) if path else None
    if target is None:
        return [value_range(a, path)] if path and include_declaration else []
    decl, refs = device_refs(a, *target)
    paths = ([decl] if decl and include_declaration else []) + refs
    return [r for p in paths if (r := value_range(a, p))]


def rename_edits(a: Analysis, path: Path_, new: str) -> list[Edit]:
    text = yaml_scalar(new)
    target = _device_target(a, path)
    if target is None:
        vr = value_range(a, path)
        return [Edit(*vr, text)] if vr else []
    decl, refs = device_refs(a, *target)
    return [Edit(*vr, text) for p in ([decl] if decl else []) + refs if (vr := value_range(a, p))]


# --------------------------------------------------------------------------- #
# Добавление, копирование и удаление узлов (дерево карты)
# --------------------------------------------------------------------------- #


@dataclass
class TextChange:
    text: str
    cursor: Pos


def _unique(base: str, taken) -> str:
    taken = set(taken)
    if base not in taken:
        return base
    i = 2
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"


def _names(items) -> list[str]:
    return [i.get("name") for i in items or [] if isinstance(i, dict)]


def _join(a: Analysis, lines: list[str]) -> str:
    """Текст из строк с переводом строки исходного файла (CRLF или LF) и тем же окончанием."""
    eol = "\r\n" if "\r\n" in a.text else "\n"
    return eol.join(lines) + (eol if a.text.endswith(("\n", "\r")) else "")


def _splice(lines: list[str], at_line: int, new_lines: list[str]) -> list[str]:
    return lines[:at_line] + new_lines + lines[at_line:]


def _dash_col(a: Analysis, item_path: Path_) -> int:
    line, col = a.nodes[item_path].start
    m = re.search(r"-\s*$", a.lines[line][:col])
    return m.start() if m else max(col - 2, 0)


def append_item(a: Analysis, owner: Path_, key: str, fields: list[tuple[str, str]]) -> TextChange | None:
    """Добавить элемент ``{fields}`` в список ``owner.key`` в стиле этого списка."""
    lines = list(a.lines)
    items = raw_at(a, owner + (key,))
    first = f"{fields[0][0]}: {fields[0][1]}"
    if isinstance(items, list) and items and _is_flow(a, owner + (key,)):
        close = a._closing(a.nodes[owner + (key,)].start)
        if close is None:
            return None
        line, col = close[0], close[1] - 1
        flow = "{" + ", ".join(f"{k}: {v}" for k, v in fields) + "}"
        lines[line] = lines[line][:col] + ", " + flow + lines[line][col:]
        return TextChange(_join(a, lines), (line, col + 3 + len(f"{fields[0][0]}: ")))
    if isinstance(items, list) and items:
        last = owner + (key, len(items) - 1)
        dash = _dash_col(a, last)
        indent = a.nodes[last].start[1]
        at = a.block(last)[1][0] + 1
    else:
        slot = _empty_list_slot(a, owner, key, lines)
        if slot is None:
            return None
        dash, at = slot
        indent = dash + 2
    new = [" " * dash + "- " + first] + [" " * indent + f"{k}: {v}" for k, v in fields[1:]]
    lines = _splice(lines, at, new)
    return TextChange(_join(a, lines), (at, dash + 2 + len(f"{fields[0][0]}: ")))


def _empty_list_slot(a: Analysis, owner: Path_, key: str, lines: list[str]) -> tuple[int, int] | None:
    """Место первого элемента пустого или отсутствующего списка ``owner.key``: (колонка «-», строка).
    Ключ списка при необходимости записывается в ``lines``."""
    n = a.nodes.get(owner)
    if n is None:
        return None
    kr = key_range(a, owner + (key,)) if owner + (key,) in a.nodes else None
    if kr:      # «key: []» или «key:» без значения: элементы — блоком под ключом
        kline = kr[0][0]
        lines[kline] = lines[kline][:kr[1][1]] + ":"
        return kr[0][1] + 2, kline + 1
    at = a.block(owner)[1][0] + 1
    lines[at:at] = [" " * n.start[1] + f"{key}:"]
    return n.start[1] + 2, at + 1


HISTORY: Path_ = ("document", "history")


def _entry_value(key: str, value: str) -> str:
    """Версия вида 1.2.3 — без кавычек (YAML не читает её как число), остальное — как текст."""
    if key == "version" and re.fullmatch(r"\d+\.\d+\.\d+[\w.+-]*", value):
        return value
    return yaml_text(value)


def apply_edits(text: str, edits: list[Edit]) -> str:
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    def offset(p: Pos) -> int:
        return starts[p[0]] + p[1] if p[0] < len(lines) else len(text)

    for e in sorted(edits, key=lambda e: e.start, reverse=True):
        text = text[:offset(e.start)] + e.text + text[offset(e.end):]
    return text


def add_history(a: Analysis, entry: dict, changes: list[str]) -> TextChange | None:
    """Запись первой в ``document.history`` (поля ``entry``: version, date, author, github и
    изменения по строке); версия и дата документа — из неё. Курсор — на версии новой записи."""
    from .analysis import analyze

    items = raw_at(a, HISTORY)
    if isinstance(items, list) and items and _is_flow(a, HISTORY):
        return None
    lines = list(a.lines)
    if isinstance(items, list) and items:
        first = HISTORY + (0,)
        dash, at = _dash_col(a, first), a.nodes[first].start[0]
    else:
        slot = _empty_list_slot(a, HISTORY[:-1], HISTORY[-1], lines)
        if slot is None:
            return None
        dash, at = slot
    fields = [f"{k}: {_entry_value(k, str(v))}" for k, v in entry.items() if v]
    pad = " " * (dash + 2)
    new = [" " * dash + "- " + fields[0]] + [pad + f for f in fields[1:]]
    if changes:
        new += [pad + "changes:"] + [pad + "  - " + yaml_text(c) for c in changes]
    text = _join(a, _splice(lines, at, new))
    for key in ("version", "date"):
        if entry.get(key):
            b = analyze(text, a.result.source.file)
            text = apply_edits(text, set_value(b, ("document", key), _entry_value(key, str(entry[key]))))
    b = analyze(text, a.result.source.file)
    n = b.nodes.get(HISTORY + (0, "version"))
    return TextChange(text, n.start if n else (at, dash + 2))


#: Типы PDO в порядке, в котором их получают новые кадры устройства CANopen.
PDO_TYPES = [f"pdo_{d}{n}" for d in ("tx", "rx") for n in range(1, 5)]


def _new_frame(a: Analysis, owner: Path_) -> list[tuple[str, str]]:
    """Поля нового кадра, как в веб-редакторе: у кадра устройства CANopen — первый свободный тип PDO
    (ID вычисляется из типа и node_id), у J1939 — свободный PGN, иначе — свободный явный ID."""
    bus = raw_at(a, owner[:2]) or {}
    protocol = bus.get("protocol") or "canopen"
    device = len(owner) == 4
    taken = [raw_at(a, fp + ("name",)) for fp in _frame_paths(a, owner[:2])]
    base = f"{raw_at(a, owner + ('name',))}_frame" if device else "frame"
    fields = [("name", _unique(base, taken))]
    if protocol == "j1939":
        used = {raw_at(a, fp + ("pgn",)) for fp in _frame_paths(a, owner[:2])}
        pgn = next((p for p in range(0xFF00, 0x10000) if p not in used), 0xFF00)
        fields += [("pgn", f"0x{pgn:04X}"), ("priority", "6")]
    else:
        types = {f.get("type") for f in raw_at(a, owner + ("frames",)) or [] if isinstance(f, dict)}
        free = next((t for t in PDO_TYPES if t not in types), None) if protocol == "canopen" and device else None
        fields.append(("type", free) if free else ("id", f"0x{_free_id(a, owner[:2]):03X}"))
    return fields + [("dlc", "8"), ("cycle_ms", "100"), ("signals", "[]")]


def _free_id(a: Analysis, bus_path: Path_) -> int:
    used = set()
    if a.map is not None:
        bus = _find(a.map, bus_path)
        used = {f.can_id for f in bus.all_frames() if f.can_id is not None} if isinstance(bus, M.Bus) else set()
    else:
        for fp in _frame_paths(a, bus_path):
            fid = raw_at(a, fp + ("id",))
            if isinstance(fid, int):
                used.add(fid)
    start = max([u for u in used if u <= 0x7FF], default=0xFF) + 1
    while start in used:
        start += 1
    return start


def _free_number(values, lo: int, hi: int) -> int | None:
    used = {v for v in values if isinstance(v, int)}
    return next((v for v in range(lo, hi + 1) if v not in used), None)


def _default_title(a: Analysis, ru: str, en: str, siblings) -> str:
    """Полное название нового узла на языке документа: «Шина 2», «Device 3» — первое свободное среди соседей
    (как в веб-редакторе)."""
    lang = doc_language(a)
    base = en if lang == "en" else ru
    taken = {_txt(s.get("title"), lang) for s in siblings or [] if isinstance(s, dict)}
    n = len(siblings or []) + 1
    while f"{base} {n}" in taken:
        n += 1
    return f"{base} {n}"


def add_node(a: Analysis, path: Path_, kind: str) -> TextChange | None:
    """Добавить шину (в карту), устройство (в шину), кадр (в шину или устройство) или сигнал (в кадр)."""
    if kind == "bus" and path == ():
        buses = raw_at(a, ("buses",)) or []
        return append_item(a, (), "buses", [("name", _unique("bus", _names(buses))),
                                            ("title", yaml_text(_default_title(a, "Шина", "Bus", buses))),
                                            ("protocol", "can")])
    if kind == "device" and len(path) == 2:
        devices = raw_at(a, path + ("devices",)) or []
        fields = [("name", _unique("device", _names(devices))),
                  ("title", yaml_text(_default_title(a, "Устройство", "Device", devices)))]
        protocol = (raw_at(a, path) or {}).get("protocol", "canopen")
        if protocol == "canopen" and (nid := _free_number([d.get("node_id") for d in devices
                                                          if isinstance(d, dict)], 1, 127)):
            fields.append(("node_id", f"0x{nid:02X}"))
        elif protocol == "j1939" and (sa := _free_number([d.get("address") for d in devices
                                                         if isinstance(d, dict)], 0, 253)) is not None:
            fields.append(("address", f"0x{sa:02X}"))
        return append_item(a, path, "devices", fields)
    if kind == "frame" and path and path[0] == "buses" and len(path) in (2, 4):
        return append_item(a, path, "frames", _new_frame(a, path))
    if kind == "signal" and len(path) >= 2 and path[-2] == "frames":
        signals = raw_at(a, path + ("signals",)) or []
        frame = _find(a.map, path) if a.map else None
        name = ("name", _unique("signal", _names(signals)))
        byte = free_start(frame, 8, 8) if isinstance(frame, M.Frame) else 0
        if byte is not None:
            return append_item(a, path, "signals", [name, ("byte", str(byte // 8))])
        # Целого свободного байта нет — однобитный сигнал на первом свободном бите
        bit = free_start(frame, 1, 1)
        return append_item(a, path, "signals", [name, ("start_bit", str(bit or 0)), ("bit_length", "1")])
    return None


def duplicate_node(a: Analysis, path: Path_) -> TextChange | None:
    """Копия элемента списка сразу после него: имя с суффиксом, у кадра — свободный ID."""
    if not path or not isinstance(path[-1], int) or path not in a.nodes:
        return None
    raw = raw_at(a, path)
    siblings = raw_at(a, path[:-1])
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        return None
    new_name = _unique(f"{raw['name']}_copy", _names(siblings))
    replace = {path + ("name",): yaml_scalar(new_name)}
    if path[-2] == "frames" and isinstance(raw.get("id"), int):
        replace[path + ("id",)] = f"0x{_free_id(a, path[:2]):03X}"
    if path[-2] == "devices":
        for key, lo, hi in (("node_id", 1, 127), ("address", 0, 253)):
            if isinstance(raw.get(key), int):
                free = _free_number([d.get(key) for d in siblings if isinstance(d, dict)], lo, hi)
                if free is not None:
                    replace[path + (key,)] = f"0x{free:02X}"
    (sl, sc), (el, ec) = a.block(path)
    lines = list(a.lines)
    if sl == el and _is_flow(a, path[:-1]):
        # Элемент «{…}» в списке «[…]»: копия через запятую на той же строке
        text = _with_replacements(a, path, replace, (sl, sc), (el, ec))
        lines[sl] = lines[sl][:ec] + ", " + text + lines[sl][ec:]
        name_col = ec + 2 + (a.nodes[path + ("name",)].start[1] - sc)
        return TextChange(_join(a, lines), (sl, name_col))
    dash = _dash_col(a, path)
    block = " " * dash + _with_replacements(a, path, replace, (sl, dash), (el, len(a.lines[el])))
    new_lines = block.split("\n")
    nl, nc = a.nodes[path + ("name",)].start
    lines = _splice(lines, el + 1, new_lines)
    return TextChange(_join(a, lines), (el + 1 + nl - sl, nc))


def _with_replacements(a: Analysis, path: Path_, replace: dict, start: Pos, end: Pos) -> str:
    """Текст от ``start`` до ``end`` с заменой значений (все замены — внутри этого текста)."""
    spans = sorted((value_range(a, p), v) for p, v in replace.items() if p in a.nodes)
    out, cur = [], start
    for (s, e), v in spans:
        out.append(_slice(a, cur, s))
        out.append(v)
        cur = e
    out.append(_slice(a, cur, end))
    return "".join(out)


def _slice(a: Analysis, s: Pos, e: Pos) -> str:
    if s[0] == e[0]:
        return a.lines[s[0]][s[1]:e[1]]
    return "\n".join([a.lines[s[0]][s[1]:], *a.lines[s[0] + 1:e[0]], a.lines[e[0]][:e[1]]])


def delete_node(a: Analysis, path: Path_) -> TextChange | None:
    """Удалить элемент списка (шина, устройство, кадр, сигнал, флаг, SDO-обмен)."""
    if not path or not isinstance(path[-1], int) or path not in a.nodes:
        return None
    siblings = raw_at(a, path[:-1])
    (sl, sc), (el, ec) = a.block(path)
    lines = list(a.lines)
    if _is_flow(a, path[:-1]) and sl == el:
        text = lines[sl]
        after = re.match(r"\s*,\s*", text[ec:])
        if after:
            lines[sl] = text[:sc] + text[ec + after.end():]
        else:
            before = re.search(r"\s*,\s*$", text[:sc])
            lines[sl] = text[:before.start() if before else sc] + text[ec:]
        return TextChange(_join(a, lines), (sl, sc))
    del lines[sl:el + 1]
    cursor = (max(sl - 1, 0), 0)
    if isinstance(siblings, list) and len(siblings) == 1:
        # Последний элемент блочного списка: «key:» → «key: []», иначе значение стало бы null
        kr = key_range(a, path[:-1])
        if kr and kr[0][0] < sl:
            kline = kr[0][0]
            lines[kline] = lines[kline][:kr[1][1]] + ": []"
            cursor = (kline, kr[0][1])
    return TextChange(_join(a, lines), cursor)


# --------------------------------------------------------------------------- #
# Поля узла (форма в боковой панели)
# --------------------------------------------------------------------------- #

#: Тексты, которые могут быть записаны на нескольких языках ({ru, en}).
TEXT_KEYS = {"title", "subtitle", "description", "comment"}
#: Поля, которые пишутся в шестнадцатеричном виде.
HEX_KEYS = {"id", "pgn", "node_id", "address", "index", "subindex", "command", "destination"}


def node_kind(path: Path_) -> str | None:
    """Тип узла дерева по форме пути."""
    if len(path) == 2 and path[0] == "buses":
        return "bus"
    if len(path) >= 2 and isinstance(path[-1], int):
        return {"devices": "device", "frames": "frame", "signals": "signal", "flags": "flag",
                "sdo": "sdo"}.get(path[-2])
    return None


_RESERVED = re.compile(r"(?i)true|false|yes|no|on|off|null|~|[-+]?(0x[0-9a-f]+|[\d.]+(e[-+]?\d+)?)")


def yaml_text(value: str) -> str:
    """Текст для людей в YAML: без кавычек, если YAML прочитает его как ту же строку (пробелы и любые
    буквы допустимы; запятые и скобки — нет, чтобы текст годился и для записи «{…}»), иначе в кавычках."""
    plain = (value == value.strip() and value != "" and value[0] not in "-?:!&*|>'\"%@`"
             and not any(c in value for c in ",[]{}#\n\r\t") and ": " not in value and not value.endswith(":")
             and not _RESERVED.fullmatch(value))
    return value if plain else '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _insert_field(a: Analysis, map_path: Path_, key: str, text: str) -> list[Edit]:
    """Добавить ключ в словарь: в блочной записи — перед первым вложенным списком или словарём
    (``signals``, ``values``…), чтобы поле оказалось рядом с остальными полями узла."""
    n = a.nodes.get(map_path)
    raw = raw_at(a, map_path)
    if n is None or _is_flow(a, map_path) or not isinstance(raw, dict):
        return insert_key(a, map_path, key, text)
    for k, v in raw.items():
        kr = key_range(a, map_path + (k,)) if isinstance(v, (dict, list)) else None
        if kr and kr[0][0] > n.start[0]:
            pos = (kr[0][0], 0)
            return [Edit(pos, pos, f"{' ' * n.start[1]}{key}: {text}\n")]
    return insert_key(a, map_path, key, text)


def format_value(key: str, value) -> str:
    """Значение поля формы → текст YAML."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if key in HEX_KEYS and value >= 0:
            width = 2 if value <= 0xFF else 3 if value <= 0xFFF else 4 if value <= 0xFFFF else 8
            return f"0x{value:0{width}X}"
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return yaml_text(str(value)) if key in TEXT_KEYS or key == "unit" else yaml_scalar(str(value))


def frame_types(a: Analysis, path: Path_) -> list[dict]:
    """Типы кадра CANopen для формы: {type, label, taken}. У кадра шины (без node_id устройства) —
    только типы с ID, не зависящим от узла; ``taken`` — имя другого кадра шины с тем же CAN ID."""
    owner = raw_at(a, path[:4]) if len(path) >= 6 and path[2] == "devices" else None
    node_id = owner.get("node_id") if isinstance(owner, dict) else None
    used: dict[int, str] = {}
    if a.map is not None:
        bus, me = _find(a.map, path[:2]), _find(a.map, path)
        for f in bus.all_frames() if isinstance(bus, M.Bus) else []:
            if f is not me and f.can_id is not None:
                used.setdefault(f.can_id, f.name)
    out = [{"type": "raw", "label": "Raw (explicit ID)", "taken": None}]
    for fc in FUNCTION_CODES.values():
        if fc.per_node and owner is None:
            continue
        can_id = compute_id(fc.type, node_id if isinstance(node_id, int) else None)
        out.append({"type": fc.type, "label": fc.label_en, "taken": used.get(can_id) if can_id is not None else None})
    return out


def node_fields(a: Analysis, path: Path_) -> dict | None:
    """Данные узла для формы: тип, язык документа, протокол шины, владелец кадра, устройства шины
    и скалярные поля (тексты {ru, en} — на языке документа)."""
    raw = raw_at(a, path)
    kind = node_kind(path)
    if kind is None or not isinstance(raw, dict):
        return None
    lang = doc_language(a)
    bus = raw_at(a, path[:2]) if path[:1] == ("buses",) else None
    bus = bus if isinstance(bus, dict) else {}
    values = {}
    for k, v in raw.items():
        if isinstance(v, dict) and k in TEXT_KEYS:
            values[k] = _txt(v, lang)
        elif isinstance(v, (str, int, float, bool)) or v is None:
            values[k] = v
        elif isinstance(v, list) and all(isinstance(x, (str, int)) for x in v):
            values[k] = list(v)
        elif not isinstance(v, (dict, list)):
            values[k] = str(v)
    # Значение SDO-обмена — вложенный словарь: его поля идут в форму под ключами «value.<поле>»
    if kind == "sdo" and isinstance(raw.get("value"), dict):
        for k, v in raw["value"].items():
            if isinstance(v, dict) and k in TEXT_KEYS:
                values[f"value.{k}"] = _txt(v, lang)
            elif isinstance(v, (str, int, float, bool)):
                values[f"value.{k}"] = v
    owner = raw_at(a, path[:4]) if len(path) >= 6 and path[2] == "devices" else None
    devices = [(d.get("name"), _txt(d.get("short"), lang) or _txt(d.get("title"), lang) or d.get("name"))
               for d in bus.get("devices") or [] if isinstance(d, dict) and isinstance(d.get("name"), str)]
    # Вычисленный тип сигнала (kind по умолчанию выводится из полей), если карта разобрана
    signal = _find(a.map, path) if a.map is not None and kind == "signal" else None
    # Есть ли в кадре другой сигнал-селектор мультиплексора (тогда сигналу доступно поле mux)
    siblings = raw_at(a, path[:-1]) if kind == "signal" else None
    has_selector = any(isinstance(s, dict) and s.get("multiplexer") and s is not raw for s in siblings or [])
    return {"kind": kind, "path": list(path), "lang": lang, "protocol": bus.get("protocol") or "canopen",
            "owner": owner.get("name") if isinstance(owner, dict) else None,
            "signalKind": signal.kind if isinstance(signal, M.Signal) else values.get("kind"),
            "bitLength": signal.bit_length if isinstance(signal, M.Signal) else None,
            "hasSelector": has_selector,
            "devices": [{"name": n, "label": str(lbl)} for n, lbl in devices], "values": values,
            "frameTypes": frame_types(a, path) if kind == "frame" else [],
            # Справочник единиц (ru, en) для подсказок в поле «Единица»; свой текст тоже допустим
            "units": [list(u) for u in UNITS] if kind == "signal" else [],
            **_layout_fields(a, path, kind, raw, lang)}


def _layout_fields(a: Analysis, path: Path_, kind: str, raw: dict, lang: str) -> dict:
    """Раскладка кадра узла (кадр, сигнал, флаг, SDO-обмен) — как в веб-редакторе, — таблица значений
    и флаги сигнала. Значение записи таблицы — как в YAML (``raw``), чтобы форма могла его дополнить."""
    from ..docmodel import PALETTE
    from ..web.session import frame_view

    out: dict = {"frame": None, "palette": PALETTE, "valueTable": None, "flags": None}
    frame_path = next((path[:i + 1] for i in range(len(path) - 1, 0, -1)
                       if path[i - 1] == "frames" and isinstance(path[i], int)), None)
    frame = _find(a.map, frame_path) if a.map is not None and frame_path else None
    if isinstance(frame, M.Frame):
        out["frame"] = frame_view(frame)
    if kind not in ("signal", "flag"):
        return out
    values = raw.get("values")
    if isinstance(values, dict):
        rows = []
        for k, v in values.items():
            entry = v if isinstance(v, dict) else {}
            rows.append({"key": str(k), "value": k if isinstance(k, int) else None,
                         "name": str(entry.get("name") or "") if entry else ("" if v is None else str(v)),
                         "description": _txt(entry.get("description"), lang), "raw": v})
        out["valueTable"] = sorted(rows, key=lambda r: (r["value"] is None, r["value"] or 0, r["key"]))
    if kind == "signal" and isinstance(raw.get("flags"), list):
        out["flags"] = [{"bit": f.get("bit"), "bit_length": f.get("bit_length"), "name": f.get("name"),
                         "description": _txt(f.get("description"), lang), "raw": f}
                        if isinstance(f, dict) else {"bit": None, "bit_length": None, "name": None,
                                                     "description": "", "raw": f}
                        for f in raw["flags"]]
    return out


def apply_ops(a: Analysis, ops: list[dict]) -> str:
    """Текст карты после операций веб-редактора (:mod:`mapcan.web.yamlops`): set, remove, insert,
    move, rename_key, set_layout. Нетронутые строки остаются как были. Ошибка операции —
    :class:`mapcan.web.yamlops.OpError`."""
    from ..web import yamlops as Y

    y = Y.make_yaml(a.text)
    doc = y.load(a.text)
    if doc is None:
        raise Y.OpError(_("в YAML синтаксическая ошибка"))
    canon_old = Y.dump(y, doc)
    Y.apply_ops(doc, ops)
    return Y.merge_text(a.text, canon_old, Y.dump(y, doc))


def set_field(a: Analysis, path: Path_, value) -> list[Edit]:
    """Записать поле узла (``path`` — путь поля): новое значение, ``None`` или "" — удалить ключ.

    Имя переименовывается вместе со ссылками на него; текст, записанный на нескольких языках,
    меняется только на языке документа.
    """
    if not path or not isinstance(path[-1], str):
        return []
    key = path[-1]
    if key == "type" and node_kind(path[:-1]) == "frame":
        return _set_frame_type(a, path, value)
    if not isinstance(raw_at(a, path[:-1]), dict):
        # Поле ещё не созданного вложенного словаря (value.name у SDO): словарь добавляется вместе с ним
        parent = path[:-1]
        if (value is None or value == "" or len(parent) < 2 or not isinstance(parent[-1], str)
                or raw_at(a, parent) is not None or not isinstance(raw_at(a, parent[:-1]), dict)):
            return []
        return _insert_field(a, parent[:-1], parent[-1], f"{{{key}: {format_value(key, value)}}}")
    current = raw_at(a, path)
    if value is None or value == "":
        if current is None or path not in a.nodes:
            return []
        if isinstance(current, dict) and key in TEXT_KEYS:
            lang = doc_language(a)
            return delete_key(a, path + (lang,)) if lang in current else []
        # Последнее поле вложенного словаря «key: {поле: …}» удаляется вместе с ним, а не оставляет «{}»
        parent, pn = path[:-1], a.nodes.get(path[:-1])
        if (len(parent) >= 2 and isinstance(parent[-1], str) and list(raw_at(a, parent)) == [key]
                and pn is not None and _is_flow(a, parent) and (close := a._closing(pn.start))
                and close[0] == pn.start[0]):
            return delete_key(a, parent)
        return delete_key(a, path)
    if key == "name" and current is not None:
        return rename_edits(a, path, str(value)) if value != current else []
    if isinstance(current, dict) and key in TEXT_KEYS:
        lang = doc_language(a)
        return set_value(a, path + (lang,), yaml_text(str(value))) if current.get(lang) != value else []
    if isinstance(value, list):
        text = "[" + ", ".join(format_value(key, v) for v in value) + "]"
        if isinstance(current, list):
            n = a.nodes.get(path)
            if n is None:
                return []
            if not _is_flow(a, path):
                # Блочный список — заменяется записью «[…]» после ключа
                kr, block = key_range(a, path), a.block(path)
                return [Edit(kr[1], block[1], f": {text}")] if kr and block else []
            close = a._closing(n.start)
            return [Edit(n.start, close, text)] if close else []
        return _insert_field(a, path[:-1], key, text)
    if isinstance(current, (dict, list)) or current == value and type(current) is type(value):
        return []
    if path not in a.nodes:
        return _insert_field(a, path[:-1], key, format_value(key, value))
    return set_value(a, path, format_value(key, value))


def _set_frame_type(a: Analysis, path: Path_, value) -> list[Edit]:
    """Тип кадра CANopen; записанный DLC, недопустимый для нового типа, убирается — берётся длина типа."""
    edits = _set_plain(a, path, value)
    allowed = CANOPEN_DLC.get(str(value or "raw"))
    dlc = raw_at(a, path[:-1] + ("dlc",))
    if edits and allowed and isinstance(dlc, int) and dlc not in allowed:
        edits += delete_key(a, path[:-1] + ("dlc",))
    return edits


def _set_plain(a: Analysis, path: Path_, value) -> list[Edit]:
    """Скалярное поле без особых правил: новое значение, ``None`` или "" — удалить ключ."""
    current = raw_at(a, path)
    if value is None or value == "":
        return delete_key(a, path) if current is not None and path in a.nodes else []
    if current == value:
        return []
    if path not in a.nodes:
        return _insert_field(a, path[:-1], path[-1], format_value(path[-1], value))
    return set_value(a, path, format_value(path[-1], value))


def minimal_edit(old: str, new: str) -> Edit:
    """Одна правка, заменяющая отличающиеся строки ``old`` на строки ``new``."""
    a, b = old.splitlines(keepends=True), new.splitlines(keepends=True)
    p = 0
    while p < min(len(a), len(b)) and a[p] == b[p]:
        p += 1
    s = 0
    while s < min(len(a), len(b)) - p and a[-1 - s] == b[-1 - s]:
        s += 1
    return Edit((p, 0), (len(a) - s, 0), "".join(b[p:len(b) - s]))
