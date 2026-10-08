"""Анализ текста карты для языкового сервера: диагностика, структура, подсказки.

Модуль не зависит от pygls: позиции здесь 0-based (строка, колонка), как в LSP,
а преобразование в типы протокола делает :mod:`mapcan.lsp.server`.
"""

from __future__ import annotations

import re
import typing
from dataclasses import dataclass, field

from pydantic import BaseModel

from .. import model as M
from ..bits import msb_position, occupied_bits
from ..diagnostics import Diagnostic
from ..i18n import _
from ..loader import LoadResult, SourceMap, loads
from ..model import MapCan, enum_entries
from ..validate import check

Pos = tuple[int, int]          # 0-based (строка, колонка)
Path_ = tuple

_HEADER = re.compile(r"^(mapcan|canmap)\s*:", re.MULTILINE)
_WORD = r"[^\s,\[\]{}#:]+(?::[^\s,\[\]{}#:]+)*"
_TOKEN = re.compile(rf"""("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|{_WORD}(?:[ \t]+{_WORD})*)""")
_KEY = re.compile(r"([A-Za-z_][\w]*)\s*:(?=\s|$)")


def is_mapcan(text: str) -> bool:
    """Похож ли YAML на карту mapcan (ключ верхнего уровня ``mapcan:``)."""
    return _HEADER.search(text) is not None


# --------------------------------------------------------------------------- #
# Узлы и их области в тексте
# --------------------------------------------------------------------------- #


@dataclass
class Node:
    path: Path_
    start: Pos
    end: Pos = (0, 0)


def _is_prefix(a: Path_, b: Path_) -> bool:
    return len(a) < len(b) and b[: len(a)] == a


def node_ranges(src: SourceMap, lines: list[str]) -> dict[Path_, Node]:
    """Область каждого узла: от его начала до начала следующего узла вне его поддерева."""
    nodes = [Node(p, (ln - 1, col - 1)) for p, (ln, col) in src.positions.items()]
    nodes.sort(key=lambda n: (n.start, len(n.path)))
    doc_end = (len(lines), 0)
    stack: list[Node] = []
    for n in nodes:
        while stack and not _is_prefix(stack[-1].path, n.path):
            stack.pop().end = n.start
        stack.append(n)
    for n in stack:
        n.end = doc_end
    return {n.path: n for n in nodes}


@dataclass
class Analysis:
    text: str
    result: LoadResult
    diagnostics: list[Diagnostic]
    lines: list[str] = field(default_factory=list)
    nodes: dict[Path_, Node] = field(default_factory=dict)

    @property
    def map(self) -> MapCan | None:
        return self.result.map

    def token_end(self, start: Pos) -> Pos:
        """Конец скаляра (или первого слова), начинающегося в позиции ``start``."""
        line, col = start
        if line >= len(self.lines):
            return start
        m = _TOKEN.match(self.lines[line], col)
        return (line, m.end()) if m and m.end() > col else (line, min(col + 1, len(self.lines[line])))

    def block(self, path: Path_) -> tuple[Pos, Pos] | None:
        """Текст узла целиком: от его начала до конца последней строки с содержимым.

        Область узла (:func:`node_ranges`) кончается там, где начинается значение следующего узла,
        то есть захватывает его ключ или «- » и пустые строки и комментарии перед ним; здесь они
        отрезаются.
        """
        n = self.nodes.get(path)
        if n is None:
            return None
        (sl, sc), (el, ec) = n.start, n.end
        if sl < len(self.lines) and self.lines[sl][sc:sc + 1] in ("{", "["):
            end = self._closing(n.start)
            if end is not None:
                return n.start, end
        if el > sl:
            # Следующий узел на другой строке: узел кончается на последней строке перед ней, где есть
            # что-то кроме комментария и отступ не меньше, чем у начала узла (строка с меньшим
            # отступом — ключ родителя, например «sdo:» после последнего сигнала).
            last = el - 1
            while last > sl:
                text = self.lines[last]
                code = _strip_comment(text).rstrip()
                if code.strip() and len(text) - len(text.lstrip()) >= sc:
                    break
                last -= 1
            line = self.lines[last]
            return n.start, (last, len(_strip_comment(line).rstrip()))
        # Следующий узел на той же строке (поток «{…}» или «[…]»): до разделителя перед ним
        line = self.lines[sl] if sl < len(self.lines) else ""
        end = len(line) if el > sl else ec
        text = line[sc:end]
        m = re.search(r"\s*(?:,\s*)?(?:[A-Za-z_]\w*\s*:\s*|-\s+)?$", text)
        return n.start, (sl, sc + (m.start() if m else len(text)))

    def _closing(self, start: Pos) -> Pos | None:
        """Позиция после скобки, парной открывающей в ``start`` (с учётом кавычек и вложенности)."""
        depth, quote = 0, ""
        line, col = start
        while line < len(self.lines):
            text = self.lines[line]
            while col < len(text):
                ch = text[col]
                if quote:
                    if ch == "\\" and quote == '"':
                        col += 1
                    elif ch == quote:
                        quote = ""
                elif ch in "\"'":
                    quote = ch
                elif ch == "#" and (col == 0 or text[col - 1] in " \t"):
                    break
                elif ch in "{[":
                    depth += 1
                elif ch in "}]":
                    depth -= 1
                    if depth == 0:
                        return line, col + 1
                col += 1
            line, col = line + 1, 0
        return None

    def path_at(self, pos: Pos) -> Path_:
        """Самый глубокий узел, область которого содержит позицию."""
        best: Path_ = ()
        for n in self.nodes.values():
            if n.start <= pos < n.end and len(n.path) >= len(best):
                best = n.path
        return best


_COMMENT = re.compile(r"""^((?:[^#"']|"(?:[^"\\]|\\.)*"|'(?:[^']|'')*')*?)\s+#.*$""")


def _strip_comment(line: str) -> str:
    """Строка без комментария в конце (« # …» вне кавычек)."""
    if line.lstrip().startswith("#"):
        return ""
    m = _COMMENT.match(line)
    return m.group(1) if m else line


def analyze(text: str, filename: str | None = None) -> Analysis:
    result = loads(text, filename)
    report = check(result)
    lines = text.splitlines()
    return Analysis(text, result, report.sorted(), lines, node_ranges(result.source, lines))


def diagnostic_range(a: Analysis, d: Diagnostic) -> tuple[Pos, Pos]:
    if d.line is None:
        return (0, 0), (0, 0)
    start = (d.line - 1, (d.column or 1) - 1)
    return start, a.token_end(start)


# --------------------------------------------------------------------------- #
# Структура (Outline)
# --------------------------------------------------------------------------- #


@dataclass
class Symbol:
    name: str
    kind: str            # bus | device | frame | signal | flag
    detail: str
    range: tuple[Pos, Pos]
    selection: tuple[Pos, Pos]
    children: list[Symbol] = field(default_factory=list)


_CHILDREN = {"bus": (("frames", "frame"), ("devices", "device")),
             "device": (("frames", "frame"),),
             "frame": (("signals", "signal"),),
             "signal": (("flags", "flag"),)}


def symbols(a: Analysis) -> list[Symbol]:
    """Дерево шин, устройств, кадров и сигналов по сырому YAML (работает и при ошибках модели)."""
    raw = a.result.raw
    if not isinstance(raw, dict):
        return []

    def build(node, path: Path_, kind: str) -> Symbol | None:
        if not isinstance(node, dict) or path not in a.nodes:
            return None
        n = a.nodes[path]
        name_path = path + ("name",)
        sel_start = a.nodes[name_path].start if name_path in a.nodes else n.start
        sym = Symbol(str(node.get("name", "?")), kind, _detail(a, node, path, kind),
                     (n.start, n.end), (sel_start, a.token_end(sel_start)))
        for key, child_kind in _CHILDREN.get(kind, ()):
            items = node.get(key)
            if isinstance(items, list):
                for i, item in enumerate(items):
                    child = build(item, path + (key, i), child_kind)
                    if child:
                        sym.children.append(child)
        return sym

    buses = raw.get("buses")
    if not isinstance(buses, list):
        return []
    return [s for i, b in enumerate(buses) if (s := build(b, ("buses", i), "bus"))]


def _detail(a: Analysis, node: dict, path: Path_, kind: str) -> str:
    """Подпись узла: по модели (вычисленный ID, биты), если карта разобрана, иначе по сырому YAML."""
    obj = _find(a.map, path) if a.map is not None and kind in ("frame", "signal") else None
    if isinstance(obj, M.Frame) and obj.can_id is not None:
        return _hex(obj.can_id, obj.extended)
    if isinstance(obj, M.Signal):
        return f"{obj.encoding} · {signal_bits(obj)}"
    if kind == "bus":
        return str(node.get("protocol", "canopen"))
    if kind == "frame":
        for key in ("id", "pgn"):
            if isinstance(node.get(key), int):
                return f"{key} 0x{node[key]:X}" if key == "pgn" else f"0x{node[key]:X}"
        return str(node.get("type", ""))
    if kind == "signal":
        return str(node.get("encoding", ""))
    return ""


# --------------------------------------------------------------------------- #
# Дерево карты (боковая панель) — те же узлы и подписи, что в дереве веб-редактора
# --------------------------------------------------------------------------- #


def _hexw(v, width: int) -> str:
    return f"0x{v:0{width}X}" if isinstance(v, int) else "—"


def _txt(value, lang: str) -> str:
    """Текст сырого YAML (строка или {ru, en}) на языке документа с откатом на любой доступный."""
    if isinstance(value, dict):
        return str(value.get(lang) or next((v for v in value.values() if v), "") or "")
    return "" if value is None else str(value)


def doc_language(a: Analysis) -> str:
    raw = a.result.raw
    doc = raw.get("document") if isinstance(raw, dict) else None
    lang = doc.get("language") if isinstance(doc, dict) else None
    return lang if lang in ("ru", "en") else "ru"


def display_name(d: dict, lang: str) -> str:
    """Подпись узла, как в веб-редакторе: название для людей, идентификатор — если названия нет;
    у устройства перед названием — сокращение."""
    title = _txt(d.get("title"), lang) or ("—" if d.get("name") is None else str(d["name"]))
    return f"{d['short']} · {title}" if d.get("short") else title


def device_label(d: dict, lang: str) -> str:
    """Короткая подпись устройства в ссылках на него: сокращение, иначе полное название."""
    return str(d["short"]) if d.get("short") else display_name(d, lang)


def map_tree(a: Analysis) -> list[dict]:
    """Узлы: kind, label, ident, description, dir (кадры), from (принимаемые кадры), range, selection, children.

    Подписи — как в дереве веб-редактора: названия (title) на языке документа, идентификатор (``ident``)
    только если названия нет. Строится по сырому YAML, вычисленные ID и биты — из модели, если карта разобрана.
    """
    raw = a.result.raw
    buses = raw.get("buses") if isinstance(raw, dict) else None
    if not isinstance(buses, list):
        return []
    lang = doc_language(a)

    def rng(path: Path_) -> dict | None:
        block = a.block(path)
        if block is None:
            return None
        (sl, sc), end = block
        # Курсор на отступе или «- » перед узлом тоже относится к нему
        own_line = re.fullmatch(r"\s*(?:-\s+)*", a.lines[sl][:sc]) is not None
        name = a.nodes.get(path + ("name",))
        return {"range": [sl, 0 if own_line else sc, *end], "selection": [sl, sc, *end], "path": list(path),
                "name": list(name.start) if name else None}

    def name_of(d: dict) -> str:
        return "—" if d.get("name") is None else str(d["name"])

    def model(path: Path_):
        return _find(a.map, path) if a.map is not None else None

    def frame_node(f: dict, path: Path_) -> dict | None:
        loc = rng(path)
        if loc is None:
            return None
        rf = model(path)
        sub = ""
        if isinstance(f.get("pgn"), int):
            sub = f"PGN {_hexw(f['pgn'], 4)}"
        elif isinstance(rf, M.Frame) and rf.can_id is not None:
            sub = _hex(rf.can_id, rf.extended)
        node = {"kind": "frame", "label": display_name(f, lang), "ident": name_of(f), "description": sub,
                "dir": rf.direction if isinstance(rf, M.Frame) and rf.device is not None else None,
                "children": [], **loc}
        for si, s in enumerate(_items(f.get("signals"))):
            sp = path + ("signals", si)
            if (sl := rng(sp)) is None:
                continue
            rs = model(sp)
            sub = ""
            if isinstance(rs, M.Signal):
                bits = occupied_bits(rs.start_bit or 0, rs.bit_length or 1, rs.byte_order == "big_endian")
                lo, hi = min(bits), max(bits)
                sub = str(lo) if lo == hi else f"{lo}–{hi}"
            snode = {"kind": "signal", "label": display_name(s, lang), "ident": name_of(s), "description": sub,
                     "children": [], **sl}
            for fi, fl in enumerate(_items(s.get("flags"))):
                if (fll := rng(sp + ("flags", fi))) is not None:
                    snode["children"].append({"kind": "flag", "label": name_of(fl), "ident": name_of(fl),
                                              "description": _("бит {bit}", bit=fl.get("bit")),
                                              "children": [], **fll})
            node["children"].append(snode)
        for ei, e in enumerate(_items(f.get("sdo"))):
            if (el := rng(path + ("sdo", ei))) is not None:
                node["children"].append({"kind": "sdo", "label": name_of(e), "ident": name_of(e),
                                         "description": f"{_hexw(e.get('index'), 4)}:{e.get('subindex', 0)}",
                                         "children": [], **el})
        return node

    out = []
    for bi, bus in enumerate(_items(buses)):
        bp = ("buses", bi)
        if (bl := rng(bp)) is None:
            continue
        bnode = {"kind": "bus", "label": display_name(bus, lang), "ident": name_of(bus), "description": "",
                 "children": [], **bl}
        for fi, f in enumerate(_items(bus.get("frames"))):
            if (fn := frame_node(f, bp + ("frames", fi))) is not None:
                bnode["children"].append(fn)
        mbus = model(bp)
        devices = _items(bus.get("devices"))
        for di, d in enumerate(devices):
            dp = bp + ("devices", di)
            if (dl := rng(dp)) is None:
                continue
            sub = (_hexw(d["node_id"], 2) if isinstance(d.get("node_id"), int)
                   else f"SA {_hexw(d['address'], 2)}" if isinstance(d.get("address"), int) else "")
            dnode = {"kind": "device", "label": display_name(d, lang), "ident": name_of(d), "description": sub,
                     "children": [], **dl}
            for fi, f in enumerate(_items(d.get("frames"))):
                if (fn := frame_node(f, dp + ("frames", fi))) is not None:
                    dnode["children"].append(fn)
            # Чужие кадры, которые устройство принимает, — ссылками после своих; название кадра может
            # не говорить, чей он, — в подписи ссылки указываем отправителя
            for rf in mbus.all_frames() if isinstance(mbus, M.Bus) else []:
                own = rf.device is not None and rf.device.name == d.get("name")
                if own or d.get("name") not in rf.receivers or (loc := rng(rf._path)) is None:
                    continue
                sender = next((x for x in devices if x.get("name") == rf.sender_name), None)
                sender_label = device_label(sender, lang) if sender else ""
                frame = raw_at_path(raw, rf._path)
                title = display_name(frame if isinstance(frame, dict) else {"name": rf.name}, lang)
                dnode["children"].append({
                    "kind": "frame", "label": f"{sender_label} · {title}" if sender_label else title,
                    "ident": rf.name, "dir": "rx", "from": sender_label or rf.sender_name or "",
                    "description": _hex(rf.can_id, rf.extended) if rf.can_id is not None else "",
                    "children": [], **loc})
            bnode["children"].append(dnode)
        out.append(bnode)
    return out


def raw_at_path(raw, path: Path_):
    for el in path:
        try:
            raw = raw[el]
        except (KeyError, IndexError, TypeError):
            return None
    return raw


def _items(v) -> list[dict]:
    return [x if isinstance(x, dict) else {} for x in v] if isinstance(v, list) else []


# --------------------------------------------------------------------------- #
# Поиск модели по пути
# --------------------------------------------------------------------------- #


def _model_of(annotation) -> type[BaseModel] | None:
    """Класс модели внутри аннотации вида ``X | None``, ``list[X]``, ``dict[int, X]``."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in typing.get_args(annotation):
        found = _model_of(arg)
        if found is not None:
            return found
    return None


def model_for(path: Path_) -> type[BaseModel] | None:
    """Класс модели узла по пути в YAML (индексы списков пропускаются)."""
    cls: type[BaseModel] | None = MapCan
    for el in path:
        if isinstance(el, int):
            continue
        if cls is None or el not in cls.model_fields:
            return None
        cls = _model_of(cls.model_fields[el].annotation)
    return cls


def _literals(annotation) -> list:
    if typing.get_origin(annotation) is typing.Literal:
        return list(typing.get_args(annotation))
    out = []
    for arg in typing.get_args(annotation):
        out.extend(v for v in _literals(arg) if v not in out)
    return out


def enum_choices() -> dict[str, list[str]]:
    """Ключ YAML → допустимые строковые значения (по аннотациям Literal всех моделей)."""
    out: dict[str, list[str]] = {}
    for obj in vars(M).values():
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == M.__name__:
            for name, f in obj.model_fields.items():
                vals = [v for v in _literals(f.annotation) if isinstance(v, str)]
                if vals:
                    out.setdefault(name, [])
                    out[name].extend(v for v in vals if v not in out[name])
    return out


# --------------------------------------------------------------------------- #
# Hover
# --------------------------------------------------------------------------- #


def _key_at(line: str, col: int) -> tuple[str, int] | None:
    for m in _KEY.finditer(line):
        if m.start(1) <= col <= m.end(1):
            return m.group(1), m.end()
    return None


def _owner(path: Path_, kind: str) -> Path_ | None:
    """Ближайший предок-элемент списка ``signals``/``frames``."""
    for i in range(len(path) - 1, 0, -1):
        if path[i - 1] == kind and isinstance(path[i], int):
            return path[: i + 1]
    return None


def _find(cmap: MapCan, path: Path_):
    obj = cmap
    for el in path:
        obj = obj[el] if isinstance(el, int) else getattr(obj, el, None)
        if obj is None:
            return None
    return obj


def hover(a: Analysis, pos: Pos) -> str | None:
    line, col = pos
    if line >= len(a.lines):
        return None
    key = _key_at(a.lines[line], col)
    if key:
        doc = _field_doc(a, key[0], (line, key[1]))
        if doc:
            return doc
    if a.map is None:
        return None
    path = a.path_at(pos)
    sig_path, frame_path = _owner(path, "signals"), _owner(path, "frames")
    frame = _find(a.map, frame_path) if frame_path else None
    if sig_path:
        sig = _find(a.map, sig_path)
        if sig is not None:
            return signal_markdown(sig)
    if frame is not None:
        return frame_markdown(frame)
    return None


def _field_doc(a: Analysis, key: str, after: Pos) -> str | None:
    """Описание поля модели для ключа, значение которого начинается после ``after``."""
    best = None
    for p, n in a.nodes.items():
        if p and p[-1] == key and n.start >= after and (best is None or n.start < a.nodes[best].start):
            best = p
    if best is None:
        return None
    cls = model_for(best[:-1])
    if cls is None or key not in cls.model_fields:
        return None
    desc = cls.model_fields[key].description
    return f"**{key}** — {_(desc)}" if desc else None


def _hex(v: int, extended: bool) -> str:
    return f"0x{v:08X}" if extended else f"0x{v:03X}"


def signal_bits(sig: M.Signal) -> str:
    start, length = sig.start_bit or 0, sig.bit_length or 1
    if sig.byte_order == "big_endian":
        return _("биты {msb}…{lsb} (BE)", msb=msb_position(start, length, True), lsb=start)
    if length == 1:
        return _("бит {bit}", bit=start)
    return _("биты {lo}–{hi}", lo=start, hi=start + length - 1)


def signal_markdown(sig: M.Signal) -> str:
    out = [f"**{sig.name}** · `{sig.encoding}` · {signal_bits(sig)} · {sig.bit_length} bit"]
    desc = M.text(sig.description, "en")
    if desc:
        out.append(desc)
    facts = []
    if sig.signed:
        facts.append("signed")
    if sig.factor != 1 or sig.offset != 0:
        facts.append(f"phys = raw × {sig.factor:g} + {sig.offset:g}")
    if sig.unit:
        facts.append(_("единица: {unit}", unit=sig.unit))
    if sig.min is not None or sig.max is not None:
        lo = "…" if sig.min is None else f"{sig.min:g}"
        hi = "…" if sig.max is None else f"{sig.max:g}"
        facts.append(_("диапазон: {lo} … {hi}", lo=lo, hi=hi))
    if sig.mux_values is not None:
        facts.append("mux = " + ", ".join(str(v) for v in sig.mux_values))
    if facts:
        out.append(" · ".join(facts))
    values = enum_entries(sig.values)
    if values:
        fmt = (lambda v: f"0x{v:X}") if sig.value_format == "hex" else str
        out.append("| " + _("Значение") + " | " + _("Имя") + " |\n|---:|---|\n"
                   + "\n".join(f"| {fmt(k)} | {v.name} |" for k, v in values))
    if sig.flags:
        out.append("| " + _("Бит") + " | " + _("Флаг") + " |\n|---:|---|\n"
                   + "\n".join(f"| {f.bit if f.bit_length == 1 else f'{f.bit}–{f.bit + f.bit_length - 1}'} "
                               f"| {f.name} |" for f in sig.flags))
    return "\n\n".join(out)


def frame_markdown(frame: M.Frame) -> str:
    head = f"**{frame.name}**"
    if frame.can_id is not None:
        head += f" · `{_hex(frame.can_id, frame.extended)}`" + (" ext" if frame.extended else "")
    head += f" · DLC {frame.dlc}"
    out = [head]
    facts = []
    if frame.transmission and frame.transmission.cycle_ms:
        facts.append(_("цикл {ms} мс", ms=frame.transmission.cycle_ms))
    if frame.sender_name or frame.receiver_names:
        facts.append(f"{frame.sender_name or '—'} → {', '.join(frame.receiver_names) or '—'}")
    if facts:
        out.append(" · ".join(facts))
    layout = frame_layout(frame)
    if layout:
        out.append(layout)
    return "\n\n".join(out)


def frame_layout(frame: M.Frame) -> str:
    """Битовая карта кадра markdown-таблицей: строки — байты, столбцы — биты 7…0."""
    sigs = frame.layout
    if not sigs or frame.dlc == 0:
        return ""
    cells: dict[int, list[int]] = {}
    for i, s in enumerate(sigs, 1):
        for b in occupied_bits(s.start_bit or 0, s.bit_length or 1, s.byte_order == "big_endian"):
            cells.setdefault(b, []).append(i)
    rows = ["| " + _("Байт") + " | " + " | ".join(str(b) for b in range(7, -1, -1)) + " |",
            "|---:|" + ":-:|" * 8]
    for byte in range(frame.dlc):
        row = [",".join(map(str, cells.get(byte * 8 + bit, []))) or "·" for bit in range(7, -1, -1)]
        rows.append(f"| {byte} | " + " | ".join(row) + " |")
    legend = "\n".join(f"{i}. `{s.name}` — {signal_bits(s)}" for i, s in enumerate(sigs, 1))
    return "\n".join(rows) + "\n\n" + legend


# --------------------------------------------------------------------------- #
# Inlay hints
# --------------------------------------------------------------------------- #


@dataclass
class Hint:
    pos: Pos
    label: str


def inlay_hints(a: Analysis) -> list[Hint]:
    """Вычисленные значения рядом с именами: ID кадров без явного ``id`` и биты сигналов."""
    if a.map is None:
        return []
    hints: list[Hint] = []

    def after_name(path: Path_) -> Pos | None:
        n = a.nodes.get(path + ("name",))
        return a.token_end(n.start) if n else None

    for bus in a.map.buses:
        for frame in bus.all_frames():
            if frame.id is None and frame.can_id is not None and (pos := after_name(frame._path)):
                hints.append(Hint(pos, f"→ {_hex(frame.can_id, frame.extended)}"))
            for sig in frame.signals:
                if pos := after_name(sig._path):
                    hints.append(Hint(pos, signal_bits(sig)))
    return hints


# --------------------------------------------------------------------------- #
# Автодополнение значений
# --------------------------------------------------------------------------- #

# Заготовки (snippet) элементов списков: метка, описание, текст с отступами относительно «-».
SNIPPET_CTX = re.compile(r"^\s*(-\s+)([A-Za-z_]*)$")
SNIPPETS = [
    ("device", "mapcan device",
     "- name: ${1:device}\n  node_id: ${2:0x01}\n  frames:\n    - name: ${3:frame}\n      type: ${4:pdo_tx1}\n"
     "      cycle_ms: ${5:100}\n      signals: []"),
    ("frame", "mapcan frame",
     "- name: ${1:frame}\n  id: ${2:0x100}\n  cycle_ms: ${3:100}\n  receivers: [$4]\n  signals:\n"
     "    - name: ${5:signal}\n      byte: ${6:0}"),
    ("signal", "mapcan signal",
     "- name: ${1:signal}\n  description: ${2:Description}\n  byte: ${3:0}"),
    ("signal enum", "mapcan signal with a value table",
     "- name: ${1:state}\n  description: ${2:State}\n  byte: ${3:0}\n  values:\n    0: ${4:OFF}\n    1: ${5:ON}"),
    ("signal quantity", "mapcan physical quantity",
     "- name: ${1:value}\n  description: ${2:Value}\n  byte: ${3:0}\n  byte_length: ${4:2}\n"
     "  factor: ${5:0.1}\n  unit: ${6:V}\n  min: ${7:0}\n  max: ${8:100}"),
    ("signal flags", "mapcan bit field",
     "- name: ${1:status}\n  description: ${2:Status}\n  byte: ${3:0}\n  flags:\n"
     "    - {bit: 0, name: ${4:ready}}\n    - {bit: 1, name: ${5:fault}}"),
]

_VALUE_CTX = re.compile(r"(?:^|[\s{,])([A-Za-z_]\w*)\s*:\s*([^\s,{}\[\]]*)$")
_LIST_CTX = re.compile(r"(?:^|[\s{,])(receivers)\s*:\s*\[[^\]]*?([^\s,\[]*)$")
_ITEM_CTX = re.compile(r"^\s*-\s+([^\s,]*)$")
DEVICE_KEYS = ("sender", "receivers")


def device_names(a: Analysis | None) -> list[str]:
    """Имена устройств всех шин из сырого YAML последнего анализа."""
    out: list[str] = []
    raw = a.result.raw if a else None
    buses = raw.get("buses") if isinstance(raw, dict) else None
    for bus in buses if isinstance(buses, list) else []:
        devices = bus.get("devices") if isinstance(bus, dict) else None
        for dev in devices if isinstance(devices, list) else []:
            name = dev.get("name") if isinstance(dev, dict) else None
            if isinstance(name, str) and name not in out:
                out.append(name)
    return out


def completions(text: str, pos: Pos, last: Analysis | None) -> tuple[str, list[str]] | None:
    """(ключ, варианты) для значения под курсором или None.

    ``last`` — последний анализ документа: имена устройств берутся из него, даже если
    текущий текст ещё не разбирается.
    """
    lines = text.splitlines()
    line, col = pos
    if line >= len(lines) + 1:
        return None
    before = (lines[line] if line < len(lines) else "")[:col]
    if m := _LIST_CTX.search(before):
        return m.group(1), device_names(last)
    if m := _VALUE_CTX.search(before):
        key = m.group(1)
        if key in DEVICE_KEYS:
            return key, device_names(last)
        choices = enum_choices().get(key)
        return (key, choices) if choices else None
    if _ITEM_CTX.match(before):
        # Элемент блочного списка «receivers:» на одной из строк выше
        for prev in reversed(lines[:line]):
            stripped = prev.strip()
            if stripped.startswith("- "):
                continue
            if re.match(r"^receivers\s*:\s*$", stripped):
                return "receivers", device_names(last)
            break
    return None
