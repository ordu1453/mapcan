"""Импорт DBC: шина, устройства (узлы DBC), кадры и сигналы → YAML-карта mapcan.

DBC не знает части того, что есть в карте (описания на нескольких языках, тип кадра CANopen, флаги
битовых полей), поэтому карта получается как шина ``can`` (или ``j1939``, если кадры помечены
VFrameFormat = J1939PG) с явными ID. Чего перенести нельзя, импорт сообщает предупреждениями.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import cantools
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarint import HexCapsInt

from .. import bits as B
from ..i18n import _
from ..web.yamlops import layout_keys

# GenMsgSendType (шаблоны Vector) → режим передачи карты
SEND_TYPES = {"spontaneous": "event", "onchange": "event", "onwrite": "event", "ifactive": "event",
              "onrequest": "on_request"}
J1939_FRAME_FORMAT = "J1939PG"
_IDENT = re.compile(r"[^0-9A-Za-z_]+")


def _attr(obj, name: str):
    """Значение атрибута DBC (для ENUM — строка варианта) или None."""
    attrs = getattr(getattr(obj, "dbc", None), "attributes", None) or {}
    a = attrs.get(name)
    if a is None:
        return None
    choices = getattr(a.definition, "choices", None)
    if choices and isinstance(a.value, int) and 0 <= a.value < len(choices):
        return choices[a.value]
    return a.value


def _brs(db, m) -> bool:
    """BRS of a CAN FD frame: the CANFD_BRS attribute or its default ("1" without a definition)."""
    v = _attr(m, "CANFD_BRS")
    if v is None:
        definition = (getattr(getattr(db, "dbc", None), "attribute_definitions", None) or {}).get("CANFD_BRS")
        v = definition.default_value if definition is not None else "1"
    return str(v).strip('"') != "0"


def _ident(name: str) -> str:
    """Имя значения enum как идентификатор: «Not available» → NOT_AVAILABLE."""
    s = _IDENT.sub("_", name.strip()).strip("_").upper() or "VALUE"
    return "V_" + s if s[0].isdigit() else s


def _text(v) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def _flow(m: dict) -> CommentedMap:
    cm = CommentedMap(m)
    cm.fa.set_flow_style()
    return cm


def _num(x: float):
    return int(x) if float(x).is_integer() else float(x)


def _signal(s, warnings: list[str], where: str) -> CommentedMap:
    choices = dict(s.choices or {})
    scaled = s.scale != 1 or s.offset != 0
    if s.length > 64:
        encoding = "bytes"            # длиннее 64 бит — только массив байт (DBC такого вида не знает)
    elif s.is_float:
        encoding = "float"
    elif choices:
        encoding = "enum"
    elif scaled:
        encoding = "scaled"
    elif s.length == 1 and not s.is_signed:
        encoding = "flag"
    else:
        encoding = "raw"
    big = s.byte_order == "big_endian"
    start = B.lsb_from_msb(s.start, s.length) if big else s.start
    out: dict = {"name": s.name, "encoding": encoding}
    if _text(s.comment):
        out["description"] = _text(s.comment)
    out.update(layout_keys(start, s.length, big, encoding))
    if encoding == "flag":
        out.pop("bit_length", None)       # у флага длина всегда 1 бит
    if big:
        out["byte_order"] = "big_endian"
    if s.is_signed and encoding in ("raw", "scaled", "enum"):
        out["signed"] = True
    if encoding in ("scaled", "float") and scaled:
        if s.scale != 1:
            out["factor"] = _num(s.scale)
        if s.offset != 0:
            out["offset"] = _num(s.offset)
    elif encoding == "enum" and scaled:
        warnings.append(_("{where}: у сигнала с таблицей значений масштаб и смещение не переносятся", where=where))
    if s.unit and encoding in ("raw", "scaled", "float"):
        out["unit"] = s.unit
    if encoding in ("raw", "scaled", "float") and not (s.minimum in (None, 0) and s.maximum in (None, 0)):
        if s.minimum is not None:
            out["min"] = _num(s.minimum)
        if s.maximum is not None:
            out["max"] = _num(s.maximum)
    if choices:
        values = CommentedMap()
        for k, v in sorted(choices.items()):
            name = str(getattr(v, "name", v))
            ident = _ident(name)
            values[int(k)] = ident if ident == name else _flow({"name": ident, "description": name})
        out["values"] = values
    if s.raw_initial is not None and encoding != "bytes":
        # initial в карте — физическое значение (у сигнала с таблицей cantools отдаёт имя значения)
        raw = float(s.raw_initial)
        out["initial"] = _num(raw if encoding in ("enum", "flag", "raw") else raw * s.scale + s.offset)
    spn = _attr(s, "SPN")
    if spn:
        out["spn"] = int(spn)
    if s.is_multiplexer:
        out["multiplexer"] = True
    if s.multiplexer_ids:
        ids = list(s.multiplexer_ids)
        out["mux"] = ids[0] if len(ids) == 1 else ids
    return _flow(out)


def _j1939(frame_id: int) -> tuple[int, int, int | None, int]:
    """CAN ID J1939 → (PGN, приоритет, адрес получателя для PDU1 или None, адрес отправителя)."""
    priority = (frame_id >> 26) & 0x7
    pgn = (frame_id >> 8) & 0x3FFFF
    pf, ps, sa = (frame_id >> 16) & 0xFF, (frame_id >> 8) & 0xFF, frame_id & 0xFF
    if pf < 240:
        return pgn & 0x3FF00, priority, ps, sa
    return pgn, priority, None, sa


def import_dbc(path: str | Path, title: str | None = None, lang: str = "en") -> tuple[str, list[str]]:
    """DBC-файл → (текст YAML-карты, предупреждения)."""
    path = Path(path)
    db = cantools.database.load_file(str(path), strict=False)
    warnings: list[str] = []
    j1939 = (str(_attr(db, "ProtocolType") or "").upper() == "J1939"
             or any(_attr(m, "VFrameFormat") == J1939_FRAME_FORMAT for m in db.messages))
    fd = any(m.is_fd for m in db.messages)
    nodes = [n.name for n in db.nodes]

    bus = CommentedMap(name=_IDENT.sub("_", path.stem).strip("_").lower() or "bus")
    bus["protocol"] = "j1939" if j1939 else "can"
    bitrate = (db.buses[0].baudrate if db.buses else None) or _attr(db, "Baudrate")
    if bitrate:
        bus["bitrate"] = int(bitrate)
    if fd:
        bus["fd"] = True
    no_brs = {m.name for m in db.messages if m.is_fd and not _brs(db, m)}
    # BRS off on every CAN FD frame: once on the bus instead of on each frame
    bus_no_brs = bool(no_brs) and all(m.name in no_brs for m in db.messages if m.is_fd)
    if bus_no_brs:
        bus["brs"] = False

    # Адрес устройства J1939 — адрес отправителя его кадров
    addresses: dict[str, int] = {}
    if j1939:
        for m in db.messages:
            if m.senders and m.senders[0] in nodes and m.is_extended_frame:
                addresses.setdefault(m.senders[0], m.frame_id & 0xFF)

    devices = {name: CommentedMap(name=name) for name in nodes}
    for n in db.nodes:
        if _text(n.comment):
            devices[n.name]["title"] = _text(n.comment)
        if n.name in addresses:
            devices[n.name]["address"] = HexCapsInt(addresses[n.name], width=2)
        devices[n.name]["frames"] = CommentedSeq()
    bus_frames = CommentedSeq()

    for m in db.messages:
        owner = m.senders[0] if m.senders and m.senders[0] in devices else None
        if m.senders and len(m.senders) > 1:
            warnings.append(_("{frame}: у кадра несколько отправителей, взят первый", frame=m.name))
        f = CommentedMap(name=m.name)
        if _text(m.comment):
            f["description"] = _text(m.comment)
        explicit = True
        if j1939 and m.is_extended_frame and owner is not None:
            pgn, prio, dest, sa = _j1939(m.frame_id)
            f["pgn"] = HexCapsInt(pgn, width=4)
            f["priority"] = prio
            if dest is not None and dest != 0xFF:
                f["destination"] = HexCapsInt(dest, width=2)
            explicit = sa != addresses.get(owner)
        if explicit:
            f["id"] = HexCapsInt(m.frame_id, width=8 if m.is_extended_frame else 3)
            if m.is_extended_frame and not j1939:
                f["extended"] = True
        if m.name in no_brs and not bus_no_brs:
            f["brs"] = False
        f["dlc"] = m.length
        send = str(_attr(m, "GenMsgSendType") or "").replace(" ", "").lower()
        if m.cycle_time:
            f["cycle_ms"] = m.cycle_time
        elif send in SEND_TYPES:
            f["trigger"] = SEND_TYPES[send]
        receivers = []
        for s in m.signals:
            for r in s.receivers:
                if r in devices and r != owner and r not in receivers:
                    receivers.append(r)
        if receivers:
            f["receivers"] = _flow_list(receivers)
        if owner is None and m.senders and m.senders[0] not in devices:
            warnings.append(_("{frame}: отправитель {name!r} не описан как узел DBC", frame=m.name,
                              name=m.senders[0]))
        signals = CommentedSeq()
        for s in m.signals:
            if s.multiplexer_signal is not None and any(x.name == s.multiplexer_signal and x.multiplexer_ids
                                                         for x in m.signals):
                warnings.append(_("{frame}.{signal}: вложенное мультиплексирование перенесено одним уровнем",
                                  frame=m.name, signal=s.name))
            signals.append(_signal(s, warnings, f"{m.name}.{s.name}"))
        f["signals"] = signals
        (devices[owner]["frames"] if owner else bus_frames).append(f)

    if bus_frames:
        bus["frames"] = bus_frames
    bus["devices"] = CommentedSeq(devices.values())

    doc = CommentedMap()
    doc["mapcan"] = 1
    doc["document"] = CommentedMap(title=title or path.stem, language=lang)
    # Имена в DBC бывают в любом стиле: проверка стиля имён отключена
    doc["lint"] = _flow({"signal_name": "any", "frame_name": "any", "device_name": "any", "value_name": "any"})
    doc["buses"] = CommentedSeq([bus])

    y = YAML()
    y.width = 120
    y.indent(mapping=2, sequence=4, offset=2)
    buf = io.StringIO()
    y.dump(doc, buf)
    # ruamel оставляет пробел в конце строки, перенося длинную flow-запись
    return "\n".join(line.rstrip() for line in buf.getvalue().split("\n")), warnings


def _flow_list(items: list) -> CommentedSeq:
    seq = CommentedSeq(items)
    seq.fa.set_flow_style()
    return seq
