"""Правка YAML-документа операциями над путями с сохранением комментариев и форматирования.

Документ хранится как ruamel round-trip дерево. Операции меняют только адресованные
узлы. При сериализации изменения переносятся на *исходный* текст построчно
(:func:`merge_text`), поэтому нетронутые фрагменты, включая ручные переносы строк
во flow-словарях, остаются байт-в-байт прежними.
"""

from __future__ import annotations

import datetime as _dt
import difflib
import io
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarint import HexCapsInt, HexInt
from ruamel.yaml.util import load_yaml_guess_indent

from ..i18n import _
from ..model import Signal

# Ключи, числа в которых принято писать в hex.
HEX_KEYS = {"id", "node_id", "address", "pgn", "destination", "command", "index", "subindex"}
LAYOUT_KEYS = ("start_bit", "bit_length", "byte", "bit", "byte_length")
MAX_FRAME_BITS = 64 * 8     # кадр CAN FD — до 64 байт


class OpError(ValueError):
    """Операцию нельзя применить (неверный путь, тип и т.п.)."""


# --------------------------------------------------------------------------- YAML I/O


def make_yaml(text: str = "") -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    ind, bsi = 4, 2
    if text.strip():
        try:
            _, ind, bsi = load_yaml_guess_indent(text)
        except Exception:  # noqa: BLE001 — оставим отступы по умолчанию
            pass
    if bsi is None:
        # В тексте нет списков: ind — отступ словаря; списки — в принятом стиле «  - »
        mapping = ind or 2
        y.indent(mapping=mapping, sequence=mapping + 2, offset=mapping)
    else:
        # bsi — отступ «-» (0 — списки без отступа), ind — отступ содержимого элемента
        y.indent(mapping=bsi or ind or 2, sequence=ind or 4, offset=bsi)
    return y


def dump(y: YAML, doc) -> str:
    buf = io.StringIO()
    y.dump(doc, buf)
    return buf.getvalue()


def merge_text(orig: str, canon_old: str, canon_new: str) -> str:
    """Перенести изменения canon_old → canon_new на исходный текст ``orig``.

    ``canon_old`` — сериализация документа до правки (может отличаться от ``orig``
    переносами строк). Фрагменты ``orig``, которым соответствуют неизменённые строки,
    копируются как есть; изменённые — берутся из ``canon_new``.
    """
    if canon_old == canon_new:
        return orig
    o = orig.splitlines(keepends=True)
    a = canon_old.splitlines(keepends=True)
    b = canon_new.splitlines(keepends=True)

    # 1. Атомы: группы строк canon_old с соответствующими строками orig.
    atom_of = [0] * len(a)          # индекс атома для строки canon_old
    atoms: list[tuple[int, int, list[str]]] = []   # (первая строка a, число строк a, строки orig)
    pending: list[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, o, a, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                atoms.append((j1 + k, 1, pending + [o[i1 + k]]))
                pending = []
                atom_of[j1 + k] = len(atoms) - 1
        elif tag == "delete":
            pending += o[i1:i2]      # строки только в orig — приклеим к следующему атому
        else:  # replace / insert
            atoms.append((j1, j2 - j1, pending + o[i1:i2]))
            pending = []
            for k in range(j1, j2):
                atom_of[k] = len(atoms) - 1

    # 2. Какие строки canon_old остались без изменений и куда перешли.
    new_of = [-1] * len(a)
    for tag, i1, i2, j1, _j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                new_of[i1 + k] = j1 + k

    def clean(idx: int) -> bool:
        start, n, _ = atoms[idx]
        first = new_of[start]
        return first >= 0 and all(new_of[start + k] == first + k for k in range(n))

    old_at = {j: i for i, j in enumerate(new_of) if j >= 0}
    out: list[str] = []
    fresh: list[bool] = []            # строка взята из canon_new (новая/изменённая)
    j = 0
    while j < len(b):
        i = old_at.get(j)
        if i is not None:
            idx = atom_of[i]
            start, n, orig_lines = atoms[idx]
            if i == start and clean(idx):
                out += orig_lines
                fresh += [False] * len(orig_lines)
                j += n
                continue
        out.append(b[j])
        fresh.append(True)
        j += 1
    out += pending
    fresh += [False] * len(pending)
    return "".join(_blank_before_insert(out, fresh))


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _blank_before_insert(lines: list[str], fresh: list[bool]) -> list[str]:
    """ruamel относит пустые строки-разделители к концу предыдущего элемента списка
    (или последнего ключа словаря), поэтому вставленный в конец элемент оказывается
    *после* разделителя. Переносим разделитель за вставленный блок, если тот начинается
    с «- » или это ключ, дописанный в конец вложенного словаря."""
    out = list(lines)
    i = 0
    while i < len(out):
        if fresh[i] and out[i].strip() and i > 0 and not out[i - 1].strip() and not fresh[i - 1]:
            j = i
            while j < len(out) and fresh[j] and out[j].strip():
                j += 1
            item = out[i].lstrip().startswith("- ")
            tail = j < len(out) and _indent(out[j]) < _indent(out[i])
            if j < len(out) and out[j].strip() and (item or tail):
                k = i
                while k > 0 and not out[k - 1].strip() and not fresh[k - 1]:
                    k -= 1
                blanks = out[k:i]
                out[k:j] = out[i:j] + blanks
                fresh[k:j] = fresh[i:j] + [False] * len(blanks)
                i = j
                continue
        i += 1
    return out


# --------------------------------------------------------------------------- значения


def _key(k: Any) -> Any:
    """Ключи таблиц значений приходят из JSON строками."""
    if isinstance(k, str):
        s = k.strip()
        try:
            return int(s, 16) if s.lower().startswith(("0x", "-0x")) else int(s)
        except ValueError:
            return k
    return k


def to_node(value: Any, key: Any = None, old: Any = None) -> Any:
    """JSON-значение → узел ruamel."""
    if isinstance(value, dict):
        m = CommentedMap()
        for k, v in value.items():
            kk = _key(k) if key in ("values",) else k
            m[kk] = to_node(v, k)
        return m
    if isinstance(value, list):
        s = CommentedSeq()
        for v in value:
            s.append(to_node(v, key))
        return s
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        if isinstance(old, (HexInt, HexCapsInt)) and value >= 0:
            cls = type(old)                                 # сохранить регистр и ширину записи
            return cls(value, width=getattr(old, "_width", None))
        if key in HEX_KEYS and value >= 0:
            return HexCapsInt(value, width=4 if key == "pgn" else (2 if value <= 0xFF else None))
        return value
    if isinstance(value, float) and value.is_integer() and isinstance(old, int) and not isinstance(old, bool):
        return int(value)
    if key == "date" and isinstance(value, str):
        try:
            return _dt.date.fromisoformat(value)
        except ValueError:
            return value
    return value


def plain(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [plain(v) for v in node]
    if isinstance(node, bool):
        return bool(node)
    if isinstance(node, int):
        return int(node)
    if isinstance(node, float):
        return float(node)
    return node


# --------------------------------------------------------------------------- навигация


def _get(doc, path: list) -> Any:
    node = doc
    for el in path:
        try:
            if isinstance(node, list):
                node = node[int(el)]
            elif isinstance(node, dict):
                node = node[_find_key(node, el)]
            else:
                raise KeyError(el)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise OpError(_("путь не найден: {path}", path=path)) from e
    return node


def _find_key(m: dict, key: Any) -> Any:
    if key in m:
        return key
    k2 = _key(key)
    if k2 in m:
        return k2
    raise KeyError(key)


def _parent(doc, path: list) -> tuple[Any, Any]:
    if not path:
        raise OpError(_("пустой путь"))
    return _get(doc, path[:-1]), path[-1]


# --------------------------------------------------------------------------- операции


def _ensure_parent(doc, path: list) -> None:
    """Создать недостающие промежуточные словари (например, ``value`` у SDO-обмена)."""
    node = doc
    for el in path[:-1]:
        if isinstance(node, dict) and el not in node and _key(el) not in node:
            node[el] = CommentedMap()
        node = node[int(el)] if isinstance(node, list) else node[_find_key(node, el)]


def op_set(doc, path: list, value: Any) -> None:
    """Установить значение. ``None`` удаляет ключ словаря."""
    if value is not None and value != "":
        try:
            _ensure_parent(doc, path)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise OpError(_("путь не найден: {path}", path=path)) from e
    parent, last = _parent(doc, path)
    if isinstance(parent, list):
        idx = int(last)
        if not 0 <= idx < len(parent):
            raise OpError(_("индекс вне списка: {path}", path=path))
        parent[idx] = to_node(value, None, parent[idx])
        return
    if not isinstance(parent, dict):
        raise OpError(_("родитель не словарь: {path}", path=path))
    if last in parent or _key(last) in parent:
        key = _find_key(parent, last)
    else:
        # Новая строка таблицы значений: ключ из JSON — число, а не строка «'99'»
        key = _key(last) if len(path) >= 2 and path[-2] == "values" else last
    if value is None or value == "":
        if key in parent:
            del parent[key]
        return
    parent[key] = to_node(value, key, parent.get(key))


def op_remove(doc, path: list) -> None:
    parent, last = _parent(doc, path)
    if isinstance(parent, list):
        idx = int(last)
        if not 0 <= idx < len(parent):
            raise OpError(_("индекс вне списка: {path}", path=path))
        del parent[idx]
    elif isinstance(parent, dict):
        try:
            del parent[_find_key(parent, last)]
        except KeyError as e:
            raise OpError(_("ключ не найден: {path}", path=path)) from e
    else:
        raise OpError(_("нельзя удалить: {path}", path=path))


def op_insert(doc, path: list, value: Any, index: int | None = None) -> None:
    """Вставить элемент в список по пути ``path`` (список создаётся, если его нет)."""
    parent, last = _parent(doc, path)
    if isinstance(parent, dict) and (last not in parent or parent[last] is None):
        parent[last] = CommentedSeq()
    seq = _get(doc, path)
    if not isinstance(seq, list):
        raise OpError(_("не список: {path}", path=path))
    node = to_node(value, path[-1] if path else None)
    if index is None or index >= len(seq):
        seq.append(node)
    else:
        seq.insert(max(0, int(index)), node)


def op_move(doc, path: list, to: int) -> None:
    parent, last = _parent(doc, path)
    if not isinstance(parent, list):
        raise OpError(_("перемещать можно только элементы списка: {path}", path=path))
    idx, to = int(last), int(to)
    if not (0 <= idx < len(parent) and 0 <= to < len(parent)):
        raise OpError(_("индекс вне списка"))
    item = parent.pop(idx)
    parent.insert(to, item)


def op_rename_key(doc, path: list, new_key: Any) -> None:
    """Переименовать ключ словаря, сохранив позицию (например, число в таблице значений)."""
    parent, last = _parent(doc, path)
    if not isinstance(parent, CommentedMap):
        raise OpError(_("не словарь: {path}", path=path))
    old = _find_key(parent, last)
    new = _key(new_key) if isinstance(old, int) or path[-2:-1] == ["values"] else new_key
    if new == old:
        return
    if new in parent:
        raise OpError(_("ключ {key!r} уже существует", key=new))
    pos = list(parent.keys()).index(old)
    value = parent.pop(old)
    parent.insert(pos, new, value)


def layout_keys(start: int, length: int, big_endian: bool, encoding: str | None) -> dict:
    """Самая читаемая запись позиции, которая разбирается обратно в те же start/length."""
    candidates: list[dict] = []
    byte, bit = divmod(start, 8)
    if big_endian:
        if bit == 0 and length % 8 == 0:
            nbytes = length // 8
            first = byte - nbytes + 1
            if first >= 0:
                candidates.append({"byte": first, "byte_length": nbytes})
    else:
        if bit == 0 and length % 8 == 0:
            candidates.append({"byte": byte, "byte_length": length // 8})
        if length == 1 and encoding == "flag":
            candidates.append({"byte": byte, "bit": bit})
        if bit + length <= 8:
            candidates.append({"byte": byte, "bit": bit, "bit_length": length})
    candidates.append({"start_bit": start, "bit_length": length})
    for c in candidates:
        try:
            s = Signal(name="x", encoding=encoding or "raw",
                       byte_order="big_endian" if big_endian else "little_endian", **c)
        except ValueError:
            continue
        if (s.start_bit, s.bit_length) == (start, length):
            return c
    return candidates[-1]


def op_set_layout(doc, path: list, start_bit: int, bit_length: int) -> None:
    sig = _get(doc, path)
    if not isinstance(sig, CommentedMap):
        raise OpError(_("не сигнал: {path}", path=path))
    if (not all(isinstance(v, int) and not isinstance(v, bool) for v in (start_bit, bit_length))
            or not 0 <= start_bit < MAX_FRAME_BITS or not 1 <= bit_length <= 64):
        raise OpError(_("недопустимая позиция"))
    big = sig.get("byte_order") == "big_endian"
    used_canonical = "start_bit" in sig and not any(k in sig for k in ("byte", "bit", "byte_length"))
    keys = list(sig.keys())
    pos = min((keys.index(k) for k in LAYOUT_KEYS if k in sig), default=None)
    if pos is None:
        pos = max((keys.index(k) for k in ("name", "encoding", "description") if k in sig), default=-1) + 1
    for k in LAYOUT_KEYS:
        if k in sig:
            del sig[k]
    if used_canonical:
        new = {"start_bit": start_bit, "bit_length": bit_length}
    else:
        new = layout_keys(start_bit, bit_length, big, sig.get("encoding"))
    for i, (k, v) in enumerate(new.items()):
        sig.insert(pos + i, k, v)


OPS = {
    "set": lambda d, o: op_set(d, o["path"], o.get("value")),
    "remove": lambda d, o: op_remove(d, o["path"]),
    "insert": lambda d, o: op_insert(d, o["path"], o.get("value"), o.get("index")),
    "move": lambda d, o: op_move(d, o["path"], o["to"]),
    "rename_key": lambda d, o: op_rename_key(d, o["path"], o["new_key"]),
    "set_layout": lambda d, o: op_set_layout(d, o["path"], o["start_bit"], o["bit_length"]),
}


def apply_ops(doc, ops: list[dict]) -> None:
    for o in ops:
        kind = o.get("op")
        if kind not in OPS:
            raise OpError(_("неизвестная операция: {op!r}", op=kind))
        if not isinstance(o.get("path"), list):
            raise OpError(_("path должен быть списком"))
        try:
            OPS[kind](doc, o)
        except OpError:
            raise
        except (KeyError, TypeError, ValueError) as e:
            raise OpError(f"{kind}: {e}") from e


# ---------------------------------------------------------------- переименование устройств

def _names(items: Any) -> list:
    return [d.get("name") if isinstance(d, dict) else None for d in items] if isinstance(items, list) else []


def _bus_frames(bus: dict, bp: list) -> list[tuple[list, dict]]:
    """Все кадры шины с путями: общие и кадры устройств."""
    out = []
    frames = bus.get("frames")
    if isinstance(frames, list):
        out += [([*bp, "frames", i], f) for i, f in enumerate(frames)]
    devices = bus.get("devices")
    if isinstance(devices, list):
        for di, d in enumerate(devices):
            frames = d.get("frames") if isinstance(d, dict) else None
            if isinstance(frames, list):
                out += [([*bp, "devices", di, "frames", i], f) for i, f in enumerate(frames)]
    return [(p, f) for p, f in out if isinstance(f, dict)]


def device_rename_ops(old: Any, new: Any) -> list[dict]:
    """Операции, переносящие переименование устройств (правкой текста) в sender/receivers кадров.

    Переименование узнаём по месту: у устройства на той же позиции той же шины другое имя,
    причём старого имени среди устройств шины больше нет, а нового раньше не было.
    Меняются только ссылки, всё ещё указывающие на старое имя. `old`, `new` — простые данные (plain).
    """
    ops: list[dict] = []
    old_buses = old.get("buses") if isinstance(old, dict) else None
    new_buses = new.get("buses") if isinstance(new, dict) else None
    if not isinstance(old_buses, list) or not isinstance(new_buses, list):
        return ops
    for bi, (ob, nb) in enumerate(zip(old_buses, new_buses, strict=False)):
        if not isinstance(ob, dict) or not isinstance(nb, dict):
            continue
        od, nd = _names(ob.get("devices")), _names(nb.get("devices"))
        renames = {a: b for a, b in zip(od, nd, strict=False)
                   if isinstance(a, str) and isinstance(b, str) and a and b and a != b
                   and a not in nd and b not in od}
        if not renames:
            continue
        for fp, f in _bus_frames(nb, ["buses", bi]):
            sender = f.get("sender")
            if isinstance(sender, str) and sender in renames:
                ops.append({"op": "set", "path": [*fp, "sender"], "value": renames[sender]})
            rec = f.get("receivers")
            if isinstance(rec, list) and any(isinstance(r, str) and r in renames for r in rec):
                ops.append({"op": "set", "path": [*fp, "receivers"],
                            "value": [renames.get(r, r) if isinstance(r, str) else r for r in rec]})
    return ops
