"""DBC import: bus, devices (DBC nodes), frames and signals → a mapcan YAML map.

DBC lacks part of what a map has (descriptions in several languages, the CANopen frame type, flags
of bit fields), so the map becomes a ``can`` bus (or ``j1939`` if the frames are marked
VFrameFormat = J1939PG) with explicit IDs. What cannot be carried over, the import reports as warnings.
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

# GenMsgSendType (Vector templates) → transmission mode of the map
SEND_TYPES = {"spontaneous": "event", "onchange": "event", "onwrite": "event", "ifactive": "event",
              "onrequest": "on_request"}
J1939_FRAME_FORMAT = "J1939PG"
_IDENT = re.compile(r"[^0-9A-Za-z_]+")


def _attr(obj, name: str):
    """Value of a DBC attribute (for an ENUM, the text of the option) or None."""
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
    """Name of an enum value as an identifier: "Not available" → NOT_AVAILABLE."""
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
        encoding = "bytes"            # longer than 64 bits: only a byte array (DBC has no such kind)
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
        out.pop("bit_length", None)       # a flag is always 1 bit long
    if big:
        out["byte_order"] = "big_endian"
    if s.is_signed and encoding in ("raw", "scaled", "enum"):
        out["representation"] = "twos_complement"
    if encoding in ("scaled", "float") and scaled:
        if s.scale != 1:
            out["factor"] = _num(s.scale)
        if s.offset != 0:
            out["offset"] = _num(s.offset)
    elif encoding == "enum" and scaled:
        warnings.append(_("{where}: the scale and offset of a signal with a value table are not imported", where=where))
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
        # initial in the map is a physical value (for a signal with a table cantools gives the value's name)
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
    """J1939 CAN ID → (PGN, priority, destination address for PDU1 or None, source address)."""
    priority = (frame_id >> 26) & 0x7
    pgn = (frame_id >> 8) & 0x3FFFF
    pf, ps, sa = (frame_id >> 16) & 0xFF, (frame_id >> 8) & 0xFF, frame_id & 0xFF
    if pf < 240:
        return pgn & 0x3FF00, priority, ps, sa
    return pgn, priority, None, sa


def import_dbc(path: str | Path, title: str | None = None, lang: str = "en") -> tuple[str, list[str]]:
    """DBC file → (text of the YAML map, warnings)."""
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
        data_bitrate = db.buses[0].fd_baudrate if db.buses else None
        if data_bitrate:
            bus["data_bitrate"] = int(data_bitrate)
    no_brs = {m.name for m in db.messages if m.is_fd and not _brs(db, m)}
    # BRS off on every CAN FD frame: once on the bus instead of on each frame
    bus_no_brs = bool(no_brs) and all(m.name in no_brs for m in db.messages if m.is_fd)
    if bus_no_brs:
        bus["brs"] = False

    # Address of a J1939 device: the source address of its frames
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
            warnings.append(_("{frame}: the frame has several senders, the first is used", frame=m.name))
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
        f["length"] = m.length
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
            warnings.append(_("{frame}: sender {name!r} is not a DBC node", frame=m.name,
                              name=m.senders[0]))
        signals = CommentedSeq()
        for s in m.signals:
            if s.multiplexer_signal is not None and any(x.name == s.multiplexer_signal and x.multiplexer_ids
                                                         for x in m.signals):
                warnings.append(_("{frame}.{signal}: nested multiplexing is imported as one level",
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
    # Names in DBC come in any style: the name style check is disabled
    doc["lint"] = _flow({"signal_name": "any", "frame_name": "any", "device_name": "any", "value_name": "any"})
    doc["buses"] = CommentedSeq([bus])

    y = YAML()
    y.width = 120
    y.indent(mapping=2, sequence=4, offset=2)
    buf = io.StringIO()
    y.dump(doc, buf)
    # ruamel leaves a trailing space when it wraps a long flow sequence
    return "\n".join(line.rstrip() for line in buf.getvalue().split("\n")), warnings


def _flow_list(items: list) -> CommentedSeq:
    seq = CommentedSeq(items)
    seq.fa.set_flow_style()
    return seq
