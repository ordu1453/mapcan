"""EDS or DCF import (CiA 306): a CANopen device, its PDOs and the dictionary objects mapped into them → a map.

The device gets its identity from ``[DeviceInfo]`` and its PDOs from the communication and mapping parameters
(1400/1600: RPDO, 1800/1A00: TPDO): COB-ID, transmission type, inhibit time and event timer; the mapped objects
become the PDO's signals with their ``index``/``subindex``, data type and limits. A producer heartbeat time (1017)
gives a heartbeat frame. A DCF gives the configured values (``ParameterValue``) and the node ID; for an EDS the
node ID comes from the caller. What the map cannot hold (dummy entries, objects mapped into no PDO, PDOs beyond
the fourth, synchronous transmission, types of the manufacturer) the import reports as warnings.
"""

from __future__ import annotations

import configparser
import io
import re
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarint import HexCapsInt

from ..canopen import FUNCTION_CODES
from ..export.eds import BOOLEAN, INTEGER, OCTET_STRING, REAL, UNSIGNED, VISIBLE_STRING
from ..fmt import FmtError, format_text
from ..i18n import _
from ..model import FORMAT_VERSION
from ..web.yamlops import layout_keys

DEFAULT_NODE_ID = 1
UNICODE_STRING = 0x000B
_UNSIGNED = {v: k for k, v in UNSIGNED.items()}
_INTEGER = {v: k for k, v in INTEGER.items()}
_REAL = {v: k for k, v in REAL.items()}
_SUB = re.compile(r"([0-9A-F]{4})SUB([0-9A-F]+)")
_NODEID = re.compile(r"\$NODEID", re.IGNORECASE)
_IDENT = re.compile(r"[^0-9A-Za-z]+")
# Bits of a PDO COB-ID (CiA 301): the PDO is not valid, the ID is 29 bits
COB_INVALID, COB_EXTENDED = 1 << 31, 1 << 29


def _ident(text: str, fallback: str) -> str:
    """A name as an identifier in snake case: "Velocity actual value" → velocity_actual_value."""
    s = _IDENT.sub("_", text.strip()).strip("_").lower()
    if not s:
        return fallback
    return f"{fallback}_{s}" if s[0].isdigit() else s


def _int(value: str | None, node_id: int) -> int | None:
    """An integer of CiA 306: decimal, 0x… or octal 0…, also with $NODEID (``$NODEID+0x180``); None if none."""
    if value is None:
        return None
    s = value.strip()
    has_node = bool(_NODEID.search(s))
    s = _NODEID.sub("", s).strip().strip("+").strip()
    try:
        n = 0 if not s else int(s, 16) if s.lower().startswith("0x") else int(s, 8) if len(s) > 1 and s[0] == "0" \
            else int(s)
    except ValueError:
        return None
    return n + node_id if has_node else n


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None and not _NODEID.search(value) else None
    except ValueError:
        return None


def _num(x: float):
    return int(x) if float(x).is_integer() else float(x)


def _flow(m: dict) -> CommentedMap:
    cm = CommentedMap(m)
    cm.fa.set_flow_style()
    return cm


class _File:
    """The objects of an EDS or DCF: (index, subindex) → their keys (lowercase); DeviceInfo and the like by name."""

    def __init__(self, text: str):
        cp = configparser.ConfigParser(interpolation=None, strict=False, comment_prefixes=(";", "#"),
                                       inline_comment_prefixes=None)
        cp.read_string(text)
        self.sections = {name.upper(): dict(cp[name]) for name in cp.sections()}
        self.objects: dict[tuple[int, int], dict] = {}
        for name, keys in self.sections.items():
            if m := _SUB.fullmatch(name):
                self.objects[(int(m[1], 16), int(m[2], 16))] = keys
            elif re.fullmatch(r"[0-9A-F]{4}", name) and _int(keys.get("objecttype"), 0) in (None, 0x7):
                self.objects[(int(name, 16), 0)] = keys
        self.dcf = "DEVICECOMISSIONING" in self.sections or any("parametervalue" in o for o in self.objects.values())

    def info(self, key: str) -> str | None:
        v = self.sections.get("DEVICEINFO", {}).get(key)
        return v.strip() if v and v.strip() else None

    def value(self, index: int, sub: int, node_id: int) -> int | None:
        """The object's value: the configured one of a DCF, else the default."""
        o = self.objects.get((index, sub))
        if o is None:
            return None
        return _int(o.get("parametervalue") or o.get("defaultvalue"), node_id)

    def indexes(self) -> set[int]:
        return {i for i, _s in self.objects}


def _signal(f: _File, index: int, sub: int, start: int, length: int, node_id: int, names: set[str],
            warnings: list[str], where: str) -> CommentedMap:
    o = f.objects.get((index, sub))
    fallback = f"obj_{index:04x}" + (f"_{sub:02x}" if sub else "")
    title = (o or {}).get("parametername", "").strip()
    name = _ident(title, fallback) if title else fallback
    base, n = name, 2
    while name in names:            # names are unique in a frame; the same object may be in two PDOs
        name, n = f"{base}_{n}", n + 1
    names.add(name)
    if o is None:
        warnings.append(_("{where}: object 0x{index:04X}:{sub:02X} is not described in the file: imported as an "
                          "unsigned number", where=where, index=index, sub=sub))
    dtype = _int((o or {}).get("datatype"), 0)
    out: dict = {"name": name}
    if title and title != name:
        out["title"] = title
    if dtype == UNICODE_STRING:      # UTF-16 is not a charset of the format: its bytes
        warnings.append(_("{where}: UNICODE_STRING object 0x{index:04X}:{sub:02X} is imported as a byte array",
                          where=where, index=index, sub=sub))
    if dtype in (VISIBLE_STRING, OCTET_STRING, UNICODE_STRING):
        out["encoding"] = "bytes"
    else:
        out["encoding"] = "number"
    out.update(layout_keys(start, length, False))
    if dtype in _REAL:
        out["representation"] = "float"
    elif dtype in _INTEGER:
        out["representation"] = "twos_complement"
    elif dtype == VISIBLE_STRING:
        out["charset"] = "ascii"
    elif o is not None and dtype not in _UNSIGNED and dtype != BOOLEAN and dtype != OCTET_STRING:
        warnings.append(_("{where}: data type 0x{type:04X} of object 0x{index:04X}:{sub:02X} is not a standard one: "
                          "imported as an unsigned number", where=where, type=dtype or 0, index=index, sub=sub))
    if out["encoding"] == "number" and o is not None:
        parse = _float if dtype in _REAL else (lambda v: _int(v, node_id))
        for key, field in (("lowlimit", "min"), ("highlimit", "max")):
            if (v := parse(o.get(key))) is not None:
                out[field] = _num(v)
        init = parse(o.get("parametervalue") or o.get("defaultvalue"))
        if init:
            out["initial"] = _num(init)
    out["index"] = HexCapsInt(index, width=4)
    if sub:
        out["subindex"] = sub
    return CommentedMap(out)


def _pdo(f: _File, tx: bool, number: int, node_id: int,
         warnings: list[str]) -> tuple[CommentedMap, set[tuple[int, int]]] | None:
    """The PDO number 1… of the file (``tx``: TPDO) and the objects it maps, or None if the file has no such PDO
    with mapped objects."""
    comm = (0x1800 if tx else 0x1400) + number - 1
    mapping = (0x1A00 if tx else 0x1600) + number - 1
    count = f.value(mapping, 0, node_id)
    entries = [f.value(mapping, i, node_id) for i in range(1, (count or 0) + 1)]
    entries = [e for e in entries if e]
    if not entries:
        return None
    kind = "pdo_tx" if tx else "pdo_rx"
    name = f"{'tpdo' if tx else 'rpdo'}{number}"
    if number > 4:
        warnings.append(_("{frame}: the map has the first four PDOs of each direction, this one is not imported",
                          frame=name))
        return None
    ftype = f"{kind}{number}"
    frame = CommentedMap(name=name)
    frame["canopen"] = ftype
    cob = f.value(comm, 1, node_id)
    if cob is not None:
        if cob & COB_INVALID:
            warnings.append(_("{frame}: the PDO is disabled in the file (bit 31 of its COB-ID), imported as enabled",
                              frame=name))
        can_id = cob & (0x1FFFFFFF if cob & COB_EXTENDED else 0x7FF)
        if can_id != FUNCTION_CODES[ftype].base + node_id or cob & COB_EXTENDED:
            frame["id"] = HexCapsInt(can_id, width=8 if cob & COB_EXTENDED else 3)
            if cob & COB_EXTENDED:
                frame["extended"] = True

    signals, names, pos, dummies = CommentedSeq(), set(), 0, 0
    for e in entries:
        index, sub, length = e >> 16, (e >> 8) & 0xFF, e & 0xFF
        if index < 0x1000:          # a dummy entry (a data type): the bits stay free
            dummies += 1
        else:
            signals.append(_signal(f, index, sub, pos, length, node_id, names, warnings, name))
        pos += length
    if pos > 64:
        warnings.append(_("{frame}: the mapped objects take {bits} bits, more than the 64 of a CAN frame",
                          frame=name, bits=pos))
    frame["length"] = min(8, (pos + 7) // 8) or 1
    if dummies:
        warnings.append(_("{frame}: {count} dummy entries of the mapping are left as free bits",
                          frame=name, count=dummies))

    ttype = f.value(comm, 2, node_id)
    timer = f.value(comm, 5, node_id)
    inhibit = f.value(comm, 3, node_id)
    if tx and timer:
        frame["cycle_ms"] = timer
    if ttype in (252, 253):
        frame["trigger"] = "on_request"
    elif ttype is not None and ttype <= 240 and tx:
        warnings.append(_("{frame}: synchronous transmission (type {type}) is not in the format: imported without it",
                          frame=name, type=ttype))
    elif tx and not timer:
        frame["trigger"] = "event"
    if tx and inhibit:
        frame["inhibit_ms"] = _num(inhibit / 10)       # in 100 µs
    if not tx and timer:
        frame["timeout_ms"] = timer                     # of an RPDO the event timer is the deadline
    frame["signals"] = signals
    return frame, {(e >> 16, (e >> 8) & 0xFF) for e in entries}


def import_eds(path: str | Path, node_id: int | None = None, title: str | None = None,
               lang: str = "en") -> tuple[str, list[str]]:
    """EDS or DCF file → (text of the YAML map, warnings)."""
    path = Path(path)
    f = _File(path.read_text(encoding="utf-8", errors="replace"))
    warnings: list[str] = []
    if node_id is None:
        written = _int(f.sections.get("DEVICECOMISSIONING", {}).get("nodeid"), 0)
        if written is not None and 1 <= written <= 0x7F:
            node_id = written
        else:
            node_id = DEFAULT_NODE_ID
            warnings.append(_("the file gives no node ID: {node_id} is used (--node-id sets another)",
                              node_id=node_id))

    product = f.info("productname") or path.stem
    device = CommentedMap(name=_ident(product, "device"))
    if product != device["name"]:
        device["title"] = product
    device["node_id"] = HexCapsInt(node_id, width=2)
    frames = CommentedSeq()
    mapped: set[tuple[int, int]] = set()
    for tx in (True, False):
        for number in range(1, 513):
            if (pdo := _pdo(f, tx, number, node_id, warnings)) is not None:
                frames.append(pdo[0])
                mapped |= pdo[1]
    heartbeat = f.value(0x1017, 0, node_id)
    if heartbeat:
        frames.append(CommentedMap(name="heartbeat", canopen="heartbeat", cycle_ms=heartbeat))
    device["frames"] = frames

    # Objects of the profile and of the manufacturer that no PDO carries: the map knows the mapped ones only
    left = sorted(i for i in f.indexes() - {i for i, _s in mapped} if i >= 0x2000)
    if left:
        shown = ", ".join(f"0x{i:04X}" for i in left[:8]) + (", …" if len(left) > 8 else "")
        warnings.append(_("{count} dictionary objects are mapped into no PDO and are not imported: {objects}",
                          count=len(left), objects=shown))

    bus = CommentedMap(name="canopen", title="CANopen")
    bus["protocol"] = "canopen"
    rates = [r for r in (10, 20, 50, 125, 250, 500, 800, 1000) if f.info(f"baudrate_{r}") == "1"]
    configured = _int(f.sections.get("DEVICECOMISSIONING", {}).get("baudrate"), 0)
    if configured:
        bus["bitrate"] = configured * 1000
    elif len(rates) == 1:
        bus["bitrate"] = rates[0] * 1000
    bus["devices"] = CommentedSeq([device])

    doc = CommentedMap()
    doc["mapcan"] = FORMAT_VERSION
    document = CommentedMap(title=title or product, language=lang)
    if vendor := f.info("vendorname"):
        document["organization"] = vendor
    doc["document"] = document
    # Object names of a vendor's file come in any style: the name style check is disabled
    doc["lint"] = _flow({"signal_name": "any", "frame_name": "any", "device_name": "any"})
    doc["buses"] = CommentedSeq([bus])

    y = YAML()
    y.width = 120
    y.indent(mapping=2, sequence=4, offset=2)
    buf = io.StringIO()
    y.dump(doc, buf)
    text = "\n".join(line.rstrip() for line in buf.getvalue().split("\n"))
    try:
        return format_text(text), warnings       # the keys in the canonical order, as mapcan fmt writes them
    except FmtError:
        return text, warnings
