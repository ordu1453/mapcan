"""Semantic checks of the map.

Every rule has a code (``Diagnostic.code``); style rules can be
turned off with ``lint.disable`` in the YAML or the ``--disable`` option of the CLI.
"""

from __future__ import annotations

import keyword
import re
from collections import defaultdict
from collections.abc import Iterable

from . import bits as B
from .canopen import CANOPEN_DLC, FUNCTION_CODES
from .diagnostics import Report
from .i18n import N_, _
from .loader import LoadResult, SourceMap, load, loads
from .model import LOGO_FORMATS, Frame, MapCan, Signal, enum_entries
from .protocols import j1939_is_pdu1

STYLE_RE = {
    "snake_case": re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"),
    "UPPER_SNAKE": re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$"),
    "camelCase": re.compile(r"^[a-z][a-zA-Z0-9]*$"),
    "PascalCase": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
}
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FD_DLC = {0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64}

# Keywords of C (C99…C23) and Python: signal names become fields of structs and classes.
C_KEYWORDS = frozenset("""
    auto break case char const continue default do double else enum extern float for goto if inline
    int long register restrict return short signed sizeof static struct switch typedef union unsigned
    void volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn
    _Static_assert _Thread_local alignas alignof bool constexpr false nullptr static_assert
    thread_local true typeof typeof_unqual
""".split())
PY_KEYWORDS = frozenset(keyword.kwlist)
# Members of the generated frame class in the Python module.
PY_FRAME_MEMBERS = frozenset({"ID", "LENGTH", "DLC", "IS_EXTENDED", "IS_FD", "BITRATE_SWITCH", "pack", "unpack"})
# Standard classic CAN bitrates, bit/s (33.3 and 83.3 kbit/s: GMLAN and low-speed buses).
STANDARD_BITRATES = frozenset({10_000, 20_000, 33_333, 50_000, 83_333, 100_000, 125_000, 250_000,
                               500_000, 800_000, 1_000_000})
BUS_LOAD_LIMIT = 70  # %, threshold of the bus load warning
# Data length of CANopen service frames by CiA 301. EMCY is not checked: CiA 301 requires 8 bytes,
# but many devices send a shorter frame, and that does not prevent receiving it.
# CANopen broadcast services: their receivers are not listed.
BROADCAST_TYPES = frozenset({"nmt", "sync", "time", "emcy", "heartbeat"})

# Rules described in the documentation (for `mapcan rules`).
RULES = {
    "yaml": ("error", N_("YAML syntax error, duplicate key")),
    "schema": ("error", N_("Schema violation: wrong type, missing required field or invalid value")),
    "number-comma": ("error", N_("Number written with a decimal comma (0,1 instead of 0.1)")),
    "number-cyrillic-x": ("error", N_("Cyrillic “х” in a hexadecimal number")),
    "number-quoted": ("warning", N_("Number written as a quoted string")),
    "deprecated-key": ("warning", N_("Former name of a field: still read, mapcan migrate rewrites it")),
    "invalid-identifier": ("error", N_("Name cannot be used as a C/Python identifier")),
    "duplicate-device-name": ("error", N_("Duplicate device name on the bus")),
    "duplicate-node-id": ("error", N_("Duplicate node_id on the bus")),
    "node-id-range": ("error", N_("CANopen node_id outside 1..127")),
    "duplicate-frame-name": ("error", N_("Duplicate frame name on the bus")),
    "frame-id-missing": ("error", N_("Cannot determine the frame's CAN ID")),
    "duplicate-can-id": ("error", N_("Duplicate CAN ID on the bus")),
    "can-id-range": ("error", N_("CAN ID does not fit in 11 bits (needs extended: true)")),
    "dlc-range": ("error", N_("Frame length that no DLC can encode")),
    "dlc-missing": ("error", N_("Frame length is not set")),
    "include": ("error", N_("Included file is missing or has keys that cannot be included")),
    "value-table": ("error", N_("No value table with this name in value_tables")),
    "canopen-dlc": ("warning", N_("Length of a CANopen service frame does not match CiA 301")),
    "bitrate-nonstandard": ("warning", N_("Non-standard bus bit rate")),
    "brs-without-fd": ("warning", N_("brs is set on a bus that is not CAN FD and is not used")),
    "bus-load": ("warning", N_("Estimated bus load from cyclic frames above 70%")),
    "duplicate-signal-name": ("error", N_("Duplicate signal/flag name in the frame")),
    "reserved-identifier": ("error", N_("Name is a C/Python keyword or a member of the generated class")),
    "name-collision": ("error", N_("Names collide in generated code (differ only in case, or clash with a _phys "
                                   "property)")),
    "signal-out-of-frame": ("error", N_("Signal extends beyond the frame length")),
    "bit-overlap": ("error", N_("Overlapping signals (multiplexing-aware)")),
    "enum-overflow": ("error", N_("Enum value does not fit in the field width")),
    "duplicate-enum-name": ("warning", N_("Same name for different enum values")),
    "encoding-field": ("error", N_("Field does not apply to the signal encoding")),
    "flag-out-of-field": ("error", N_("Flag extends beyond the bit field")),
    "flag-overlap": ("error", N_("Flags overlap inside the bit field")),
    "flag-length": ("warning", N_("Flag signal longer than 1 bit")),
    "zero-factor": ("error", N_("Zero factor")),
    "range-overflow": ("warning", N_("min/max outside the range the field can represent")),
    "min-max": ("error", N_("min is greater than max")),
    "invalid-in-range": ("warning", N_("invalid value falls inside the min..max range")),
    "missing-unit": ("info", N_("Physical quantity without a unit")),
    "mux-no-selector": ("error", N_("Multiplexed signal in a frame without a selector")),
    "mux-multiple-selectors": ("error", N_("More than one selector in the frame")),
    "mux-value-overflow": ("error", N_("mux value does not fit in the selector")),
    "mux-value-unknown": ("warning", N_("mux value is not in the selector's value table")),
    "mux-selector-muxed": ("error", N_("Selector is itself multiplexed")),
    "cycle-unexpected": ("error", N_("cycle_ms is set together with trigger")),
    "direction-mismatch": ("warning", N_("Direction conflicts with the CANopen frame type")),
    "frame-type-protocol": ("warning", N_("CANopen frame type on a non-CANopen bus")),
    "sdo-frame-type": ("warning", N_("sdo description on a frame that is not sdo_tx/sdo_rx")),
    "sdo-duplicate": ("error", N_("Duplicate SDO exchange (command, index, subindex)")),
    "name-style": ("warning", N_("Name does not match the style rule (lint)")),
    "name-inconsistent": ("warning", N_("The same value name is spelled differently")),
    "j1939-address": ("error", N_("J1939 address outside 0..253 or repeated on the bus")),
    "j1939-pdu1-pgn": ("warning", N_("PDU1 PGN (PF < 240) with a non-zero low byte")),
    "j1939-destination": ("warning", N_("destination set for a PDU2 PGN (PF ≥ 240) and unused")),
    "j1939-field-protocol": ("warning", N_("pgn/priority/destination/address/spn on a non-J1939 bus")),
    "j1939-spn-duplicate": ("warning", N_("The same SPN on several signals of the bus")),
    "j1939-tp": ("info", N_("A PGN longer than 8 bytes is sent with the J1939-21 transport protocol")),
    "canopen-od": ("warning", N_(
        "CANopen dictionary object on a non-PDO signal, outside 0x2000..0x9FFF or big-endian")),
    "od-duplicate": ("warning", N_("The same dictionary object on several signals of a device")),
    "unknown-receiver": ("error", N_("Frame receiver is not defined on the bus")),
    "unknown-sender": ("error", N_("Frame sender is not defined on the bus")),
    "sender-mismatch": ("warning", N_("sender conflicts with the frame direction or matches a receiver")),
    "rx-duplicate": ("error", N_("RX frame duplicates another device's frame (describe the frame at its sender)")),
    "rx-no-sender": ("info", N_("RX frame without a sender")),
    "no-receivers": ("info", N_("Frame has no receivers on the bus")),
    "duplicate-short": ("warning", N_("Duplicate device short label on the bus")),
    "history-version": ("warning", N_("Document version differs from the latest revision history entry")),
    "float-length": ("error", N_("A float signal must be 32 or 64 bits")),
    "signal-length": ("error", N_("Signal longer than 64 bits that is not an aligned byte array")),
    "initial-range": ("warning", N_("Default value outside the signal's range")),
    "invalid-overflow": ("error", N_("invalid value does not fit in the signal width")),
    "logo-missing": ("warning", N_("Logo file not found")),
    "logo-format": ("error", N_("Unsupported logo format")),
    "signed-code": ("info", N_("Ones' complement or sign-magnitude signal: DBC stores two's complement only")),
    "missing-description": ("info", N_("Signal has no description")),
    "missing-title": ("info", N_("Bus or device has no full name")),
    "empty-frame": ("info", N_("Frame has no signals")),
}


class _Ctx:
    def __init__(self, cmap: MapCan, src: SourceMap, report: Report, disabled: set[str]):
        self.cmap, self.src, self.report, self.disabled = cmap, src, report, disabled

    def emit(self, code: str, message: str, path=(), level: str | None = None) -> None:
        if code in self.disabled:
            return
        lvl = level or RULES.get(code, ("error",))[0]
        self.report.add(self.src.diag(lvl, code, message, path))


def validate_map(cmap: MapCan, src: SourceMap, disable: Iterable[str] = ()) -> Report:
    report = Report()
    ctx = _Ctx(cmap, src, report, set(cmap.lint.disable) | set(disable))
    value_spellings: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    logo = cmap.logo_path
    if logo is not None:
        if logo.suffix.lower() not in LOGO_FORMATS:
            ctx.emit("logo-format", _("logo {logo!r}: supported formats are {formats}",
                                      logo=cmap.document.logo, formats=", ".join(LOGO_FORMATS)), ("document", "logo"))
        elif not logo.is_file():
            ctx.emit("logo-missing", _("logo file not found: {path}", path=logo), ("document", "logo"))

    hist = cmap.document.history
    if hist and hist[0].version != cmap.document.version:
        ctx.emit("history-version", _("document version is {version!r}, but the latest revision history entry is "
                                      "{latest!r}",
                                      version=cmap.document.version, latest=hist[0].version),
                 ("document", "version"))

    for bus in cmap.buses:
        _check_bus(ctx, bus)
        for frame in bus.all_frames():
            _check_frame(ctx, frame)
            for sig in frame.signals:
                for v, ev in enum_entries(sig.values):
                    value_spellings[_norm(ev.name)][ev.name].append(sig._path + ("values", v))
                for fl in sig.flags or []:
                    for v, ev in enum_entries(fl.values):
                        value_spellings[_norm(ev.name)][ev.name].append(fl._path + ("values", v))

    for spellings in value_spellings.values():
        if len(spellings) > 1:
            # The reference is a valid identifier, then the most frequent spelling.
            names = sorted(spellings, key=lambda n: (not IDENT_RE.match(n), -len(spellings[n])))
            main = names[0]
            for other in names[1:]:
                for p in spellings[other]:
                    ctx.emit("name-inconsistent",
                             _("value {name!r} is spelled differently from {main!r} elsewhere",
                               name=other, main=main), p)
    return report


def _norm(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def _ident(ctx: _Ctx, name: str, what: str, path, style: str | None) -> None:
    if not IDENT_RE.match(name):
        ctx.emit("invalid-identifier", _("{what} {name!r}: only Latin letters, digits and _ are allowed",
                                         what=what, name=name), path)
        return
    if style and style != "any" and not STYLE_RE[style].match(name):
        ctx.emit("name-style", _("{what} {name!r} is not in {style} style", what=what, name=name, style=style), path)


def _check_bus(ctx: _Ctx, bus) -> None:
    lint = ctx.cmap.lint
    if bus.bitrate is not None and bus.bitrate not in STANDARD_BITRATES:
        ctx.emit("bitrate-nonstandard", _("bit rate {bitrate} bit/s is not a standard value (125000, 250000, 500000, "
                                          "1000000…)", bitrate=bus.bitrate),
                 bus._path + ("bitrate",))
    if bus.brs is not None and not bus.fd:
        ctx.emit("brs-without-fd", _("brs on a bus without fd: true is not used"), bus._path + ("brs",))
    if bus.title is None:
        ctx.emit("missing-title", _("bus {name!r} has no name (title)", name=bus.name), bus._path + ("title",))
    names, nodes, addrs, shorts = {}, {}, {}, {}
    for dev in bus.devices:
        if dev.title is None:
            ctx.emit("missing-title", _("device {name!r} has no full name (title)", name=dev.name),
                     dev._path + ("title",))
        if dev.short:
            if dev.short in shorts:
                ctx.emit("duplicate-short", _("short label {short!r} is already used by device {other!r}",
                                              short=dev.short, other=shorts[dev.short]), dev._path + ("short",))
            shorts.setdefault(dev.short, dev.name)
        if dev.address is not None:
            if bus.protocol != "j1939":
                ctx.emit("j1939-field-protocol",
                         _("address set on a device on a {protocol} bus", protocol=bus.protocol),
                         dev._path + ("address",))
            elif dev.address > 253:
                ctx.emit("j1939-address", _("address {address:#04x} outside 0..253 (254, 255 are reserved)",
                                            address=dev.address),
                         dev._path + ("address",))
            if dev.address in addrs:
                ctx.emit("j1939-address",
                         _("address {address:#04x} is already used by device {other!r}",
                           address=dev.address, other=addrs[dev.address].name),
                         dev._path + ("address",))
            addrs[dev.address] = dev
        _ident(ctx, dev.name, _("device name"), dev._path + ("name",), lint.device_name)
        if dev.name in names:
            ctx.emit("duplicate-device-name", _("device {name!r} is already defined", name=dev.name),
                     dev._path + ("name",))
        names[dev.name] = dev
        if dev.node_id is not None:
            if bus.protocol == "canopen" and not 1 <= dev.node_id <= 127:
                ctx.emit("node-id-range", _("node_id {node_id:#x} outside 1..127", node_id=dev.node_id),
                         dev._path + ("node_id",))
            if dev.node_id in nodes:
                ctx.emit("duplicate-node-id",
                         _("node_id {node_id:#04x} is already used by device {other!r}",
                           node_id=dev.node_id, other=nodes[dev.node_id].name),
                         dev._path + ("node_id",))
            nodes[dev.node_id] = dev

    frame_names, ids, upper = {}, {}, {}
    for frame in bus.all_frames():
        p = frame._path
        if frame.name in frame_names:
            ctx.emit("duplicate-frame-name", _(
                "frame {name!r} is already defined on the bus", name=frame.name), p + ("name",))
        elif frame.name.upper() in upper:
            ctx.emit("name-collision", _("frame {name!r} differs from {other!r} only in case: their C macros will "
                                         "collide", name=frame.name,
                                         other=upper[frame.name.upper()]), p + ("name",))
        frame_names[frame.name] = frame
        upper.setdefault(frame.name.upper(), frame.name)
        if frame.can_id is None:
            if bus.protocol == "j1939":
                # The message goes on the field to fill in (the editor highlights it)
                if frame.pgn is None:
                    ctx.emit("frame-id-missing", _("frame {name!r}: {why}", name=frame.name,
                                                   why=_("pgn (or id) is required")), p + ("pgn",))
                elif frame.device is not None and frame.direction == "rx" and frame.sender is None:
                    ctx.emit("frame-id-missing", _("frame {name!r}: {why}", name=frame.name,
                                                   why=_("the source address of an RX frame is unknown: set "
                                                         "sender to the sending device or give id")),
                             p + ("sender",))
                elif frame.device is not None and frame.direction == "rx":
                    ctx.emit("frame-id-missing", _("frame {name!r}: {why}", name=frame.name,
                                                   why=_("the sender has no address")), p + ("sender",))
                else:
                    ctx.emit("frame-id-missing", _("frame {name!r}: {why}", name=frame.name,
                                                   why=_("the device has no address")), p)
            elif frame.type == "raw" or bus.protocol != "canopen":
                ctx.emit("frame-id-missing", _("frame {name!r}: type {type} needs an explicit id",
                                               name=frame.name, type=frame.type), p + ("id",))
            else:
                ctx.emit("frame-id-missing",
                         _("frame {name!r}: the device has no node_id to compute the {type} ID",
                           name=frame.name, type=frame.type), p)
            continue
        key = (frame.extended, frame.can_id)   # an 11-bit and a 29-bit ID with the same number differ
        if key in ids:
            other = ids[key]
            twin = _rx_twin(frame, other)
            if twin is not None:
                rx, tx = twin
                ctx.emit("rx-duplicate",
                         _("RX frame {name!r} of device {device!r} duplicates frame {other!r} of sender {sender!r} "
                           "(CAN ID {can_id:#05x}): describe the frame once at the sender and add {device!r} to "
                           "receivers", name=rx.name, device=rx.device.name, other=tx.name,
                           sender=tx.sender_name, can_id=frame.can_id), rx._path)
            else:
                ctx.emit("duplicate-can-id",
                         _("CAN ID {can_id:#05x} of frame {name!r} matches frame {other!r}",
                           can_id=frame.can_id, name=frame.name, other=other.name),
                         p + (("id",) if frame.id is not None else ("canopen",)))
        else:
            ids[key] = frame
        if frame.can_id > 0x7FF and not frame.extended:
            ctx.emit("can-id-range", _("CAN ID {can_id:#x} > 0x7FF", can_id=frame.can_id), p + ("id",))
    _check_spn(ctx, bus)
    _check_od(ctx, bus)
    _check_bus_load(ctx, bus)


def _check_od(ctx: _Ctx, bus) -> None:
    """CANopen dictionary objects mapped into PDOs: index/subindex of the signals."""
    for frame in bus.all_frames():
        pdo = bus.protocol == "canopen" and frame.device is not None and frame.type.startswith("pdo_")
        for s in frame.signals:
            if s.index is None and s.subindex is None:
                continue
            p = s._path + (("index",) if s.index is not None else ("subindex",))
            if not pdo:
                ctx.emit("canopen-od", _("{name!r}: a dictionary object is set only on PDO signals of a device on a "
                                         "CANopen bus", name=s.name), p)
            elif s.index is None:
                ctx.emit("canopen-od", _("{name!r}: subindex without index", name=s.name), p)
            elif not 0x2000 <= s.index <= 0x9FFF:
                ctx.emit("canopen-od", _("{name!r}: index {index:#06x} is outside the manufacturer and profile areas "
                                         "(0x2000..0x9FFF)", name=s.name, index=s.index), p)
            elif s.byte_order == "big_endian":
                ctx.emit("canopen-od", _("{name!r}: CANopen PDOs carry little-endian data", name=s.name),
                         s._path + ("byte_order",))
    for dev in bus.devices:
        seen: dict[tuple[int, int], str] = {}
        for frame in dev.frames:
            for s in frame.signals:
                if s.index is None:
                    continue
                key = (s.index, s.subindex or 0)
                if key in seen:
                    ctx.emit("od-duplicate", _("object {index:04X}:{sub:02X} is already mapped by {other}",
                                               index=key[0], sub=key[1], other=seen[key]), s._path + ("index",))
                else:
                    seen[key] = f"{frame.name}.{s.name}"


def _check_spn(ctx: _Ctx, bus) -> None:
    seen: dict[int, str] = {}
    for frame in bus.all_frames():
        for s in frame.layout:
            if s.spn is None:
                continue
            if bus.protocol != "j1939":
                ctx.emit("j1939-field-protocol", _("spn on a signal of a {protocol} bus", protocol=bus.protocol),
                         s._path + ("spn",))
            elif s.spn in seen:
                ctx.emit("j1939-spn-duplicate",
                         _("SPN {spn} is already used by signal {other}", spn=s.spn, other=seen[s.spn]),
                         s._path + ("spn",))
            else:
                seen[s.spn] = f"{frame.name}.{s.name}"


def _is_tp(frame: Frame) -> bool:
    """A PGN sent with the J1939-21 transport protocol: longer than one frame of the bus."""
    return frame.bus.protocol == "j1939" and frame.length > (64 if frame.bus.fd else 8)


def _tp_mode(frame: Frame) -> str:
    """BAM to all (PDU2 or PDU1 with address 0xFF), RTS/CTS to one receiver."""
    dest = frame.destination if frame.destination is not None else 0xFF
    return "RTS/CTS" if frame.pgn is not None and j1939_is_pdu1(frame.pgn) and dest != 0xFF else "BAM"


def _tp_bits(frame: Frame) -> int:
    """Bits on the bus of a PGN with the transport protocol: TP.DT packets of 7 bytes and the TP.CM frames."""
    packets = -(-frame.length // 7)
    control = 1 if _tp_mode(frame) == "BAM" else 3      # BAM; RTS, CTS, EndOfMsgAck
    return (packets + control) * _frame_bits(8, True)


def _frame_bits(dlc: int, extended: bool) -> int:
    """Length of a classic CAN frame in bits with worst-case bit stuffing (Davis et al., 2007)."""
    n = 8 * dlc
    return n + 67 + (54 + n - 1) // 4 if extended else n + 47 + (34 + n - 1) // 4


def _check_bus_load(ctx: _Ctx, bus) -> None:
    # In CAN FD the data phase runs at another bitrate, which the map does not have: the estimate would be wrong.
    if bus.fd or not bus.bitrate:
        return
    cyclic = [f for f in bus.all_frames()
              if f.can_id is not None and f.cycle_ms and f.trigger is None]
    bits_per_s = sum((_tp_bits(f) if _is_tp(f) else _frame_bits(f.length, f.extended)) * 1000 / f.cycle_ms
                     for f in cyclic)
    load = 100 * bits_per_s / bus.bitrate
    if load > BUS_LOAD_LIMIT:
        ctx.emit("bus-load", _("estimated load of bus {bus!r} is {load:.0f}% (cyclic frames: {count}, {bitrate} "
                               "bit/s); keep it at or below {limit}%",
                               bus=bus.name, load=load, count=len(cyclic), bitrate=bus.bitrate,
                               limit=BUS_LOAD_LIMIT), bus._path + ("bitrate",))


def _rx_twin(a: Frame, b: Frame) -> tuple[Frame, Frame] | None:
    """A pair (RX frame of a device, the same frame at its sender): one frame described twice."""
    for rx, tx in ((a, b), (b, a)):
        if (rx.device is not None and rx.direction == "rx"
                and tx.sender_name is not None and tx.sender_name != rx.device.name):
            return rx, tx
    return None


def _check_frame(ctx: _Ctx, frame: Frame) -> None:
    p = frame._path
    bus = frame.bus
    _ident(ctx, frame.name, _("frame name"), p + ("name",), ctx.cmap.lint.frame_name)

    if frame._length_missing:
        ctx.emit("dlc-missing", _("frame {name!r}: length (data length, bytes) is not set", name=frame.name), p)
    if _is_tp(frame):
        ctx.emit("j1939-tp", _("{length}-byte PGN: sent with the J1939-21 transport protocol ({mode})",
                               length=frame.length, mode=_tp_mode(frame)), p + ("length",))
    elif bus.fd:
        if frame.length not in FD_DLC:
            ctx.emit("dlc-range", _("length {length} is not a CAN FD frame length (0..8, 12, 16, 20, 24, 32, 48, 64)",
                                    length=frame.length), p + ("length",))
    elif frame.length > 8:
        ctx.emit("dlc-range", _("length {length} > 8 (for CAN FD set fd: true on the bus)", length=frame.length),
                 p + ("length",))
    if frame.brs is not None and not bus.fd:
        ctx.emit("brs-without-fd", _("brs of a frame on a bus without fd: true is not used"), p + ("brs",))

    fc = FUNCTION_CODES.get(frame.type)
    allowed = CANOPEN_DLC.get(frame.type)
    if bus.protocol == "canopen" and allowed and frame.length not in allowed:
        ctx.emit("canopen-dlc", _("a {type} frame is {expected} bytes long under CiA 301, but {length} is set",
                                  type=frame.type, expected=" / ".join(map(str, sorted(allowed))), length=frame.length),
                 p + ("length",))
    devices = {d.name for d in bus.devices}
    for i, r in enumerate(frame.receivers):
        if r not in devices:
            ctx.emit("unknown-receiver", _("receiver {name!r} is not defined on bus {bus!r}", name=r, bus=bus.name),
                     p + ("receivers", i))
    dev = frame.device
    if frame.sender is not None:
        if frame.sender not in devices:
            ctx.emit("unknown-sender", _("sender {name!r} is not defined on bus {bus!r}",
                                         name=frame.sender, bus=bus.name), p + ("sender",))
        elif dev is not None and frame.direction == "tx" and frame.sender != dev.name:
            ctx.emit("sender-mismatch", _("frame {name!r} is transmitted by device {device!r} itself (TX); sender "
                                          "{sender!r} conflicts with the direction",
                                          name=frame.name, device=dev.name, sender=frame.sender), p + ("sender",))
        elif dev is not None and frame.direction == "rx" and frame.sender == dev.name:
            ctx.emit("sender-mismatch", _("device {device!r} receives frame {name!r} (RX) and cannot be its sender",
                                          name=frame.name, device=dev.name), p + ("sender",))
    snd = frame.sender_name
    for i, r in enumerate(frame.receivers):
        if r == snd:
            ctx.emit("sender-mismatch", _("sender {name!r} is listed among the frame receivers", name=r),
                     p + ("receivers", i))
    if (dev is not None and snd is not None and not frame.receiver_names and len(devices) > 1
            and frame.type not in BROADCAST_TYPES):
        ctx.emit("no-receivers", _("nobody receives frame {name!r}: list the receiving devices in receivers",
                                   name=frame.name), p + ("receivers",))
    if dev is not None and frame.direction == "rx" and frame.sender is None and fc is None and len(devices) > 1:
        ctx.emit("rx-no-sender", _("RX frame {name!r} has no sender: if the sender is on the bus, set sender or move "
                                   "the frame to the sender and add {device!r} to receivers",
                                   name=frame.name, device=dev.name), p + ("sender",))
    j1939_fields = [k for k in ("pgn", "priority", "destination") if getattr(frame, k) is not None]
    if j1939_fields and bus.protocol != "j1939":
        ctx.emit("j1939-field-protocol", _("{fields} set on a frame on a {protocol} bus",
                                           fields=", ".join(j1939_fields), protocol=bus.protocol),
                 p + (j1939_fields[0],))
    if bus.protocol == "j1939" and frame.pgn is not None:
        if j1939_is_pdu1(frame.pgn) and frame.pgn & 0xFF:
            ctx.emit("j1939-pdu1-pgn", _("PGN {pgn:#06x} is PDU1: the low byte must be 0 (the destination address is "
                                         "set by destination)", pgn=frame.pgn), p + ("pgn",))
        if not j1939_is_pdu1(frame.pgn) and frame.destination is not None:
            ctx.emit("j1939-destination", _(
                "PGN {pgn:#06x} is PDU2 (broadcast), destination is not used", pgn=frame.pgn), p + ("destination",))
    if bus.protocol != "canopen" and frame.type != "raw":
        ctx.emit("frame-type-protocol", _("type {type} on a bus with protocol {protocol}",
                                          type=frame.type, protocol=bus.protocol), p + ("canopen",))
    if fc and fc.direction and frame.direction and frame.direction != fc.direction and frame.device:
        ctx.emit("direction-mismatch",
                 _("a {type} frame is usually {expected} for the device, but {actual} is set", type=frame.type,
                   expected=fc.direction.upper(), actual=frame.direction.upper()), p + ("direction",))

    if frame.cycle_ms is not None and frame.trigger is not None:
        ctx.emit("cycle-unexpected", _("cycle_ms is set on a frame with trigger: {trigger}", trigger=frame.trigger),
                 p + ("cycle_ms",))

    if frame.sdo:
        if frame.type not in ("sdo_tx", "sdo_rx"):
            ctx.emit("sdo-frame-type", _("sdo set on a frame of type {type}", type=frame.type), p + ("sdo",))
        seen = {}
        for ex in frame.sdo:
            key = (ex.command, ex.index, ex.subindex)
            if key in seen:
                ctx.emit("sdo-duplicate",
                         _("exchange {name!r} duplicates {other!r} (0x{command:02X}, 0x{index:04X}:{subindex})",
                           name=ex.name, other=seen[key], command=ex.command, index=ex.index,
                           subindex=ex.subindex), ex._path)
            seen[key] = ex.name

    if not frame.layout:
        if frame.length > 0:
            ctx.emit("empty-frame", _("frame {name!r} has no signals", name=frame.name), p)
        return

    _check_signals(ctx, frame)


def _check_signals(ctx: _Ctx, frame: Frame) -> None:
    lint = ctx.cmap.lint
    sigs = frame.layout
    nbits = frame.length * 8

    # Names
    names: dict[str, tuple] = {}
    upper: dict[str, str] = {}
    phys = {s.name + "_phys": s.name for s in sigs if s.factor != 1 or s.offset != 0 or s.encoding == "scaled"}
    for s in sigs:
        if s.name in C_KEYWORDS or s.name in PY_KEYWORDS:
            ctx.emit("reserved-identifier", _("signal name {name!r} is a C/Python keyword: the generated code will not "
                                              "compile", name=s.name),
                     s._path + ("name",))
        elif s.name in PY_FRAME_MEMBERS:
            ctx.emit("reserved-identifier", _("signal name {name!r} clashes with a frame class member in the Python "
                                              "module ({members})", name=s.name,
                                              members=", ".join(sorted(PY_FRAME_MEMBERS))),
                     s._path + ("name",))
        if s.name in phys:
            ctx.emit("name-collision", _("signal {name!r} clashes with the physical value property of signal {other!r} "
                                         "in the Python module", name=s.name, other=phys[s.name]),
                     s._path + ("name",))
        entries = [(s.name, s._path + ("name",), False)]
        entries += [(f.name, f._path + ("name",), True) for f in s.flags or []]
        for name, path, is_flag in entries:
            _ident(ctx, name, _("flag name") if is_flag else _("signal name"), path, lint.signal_name)
            if name in names:
                other = _("flag") if names[name][1] else _("signal")
                msg = (_("flag {name!r} already exists in frame {frame!r} ({other})") if is_flag
                       else _("signal {name!r} already exists in frame {frame!r} ({other})"))
                ctx.emit("duplicate-signal-name", msg.format(name=name, frame=frame.name, other=other), path)
            else:
                names[name] = (path, is_flag)
                if name.upper() in upper:
                    ctx.emit("name-collision", _("{name!r} differs from {other!r} only in case: their C macros will "
                                                 "collide", name=name,
                                                 other=upper[name.upper()]), path)
                upper.setdefault(name.upper(), name)

    # Multiplexing
    selectors = [s for s in sigs if s.multiplexer]
    selector = selectors[0] if selectors else None
    for extra in selectors[1:]:
        ctx.emit("mux-multiple-selectors", _("second selector {name!r}", name=extra.name),
                 extra._path + ("multiplexer",))
    for sel in selectors:
        if sel.mux is not None:
            ctx.emit("mux-selector-muxed", _("selector {name!r} cannot have mux", name=sel.name),
                     sel._path + ("mux",))

    for s in sigs:
        sp = s._path
        be = s.byte_order == "big_endian"
        occ = B.occupied_bits(s.start_bit, s.bit_length, be)
        if min(occ) < 0 or max(occ) >= nbits:
            first, last = B.byte_span(s.start_bit, s.bit_length, be)
            ctx.emit("signal-out-of-frame",
                     _("signal {name!r} occupies bytes {first}..{last}, but the frame is {length} bytes long",
                       name=s.name, first=first, last=last, length=frame.length), sp)

        lo, hi = B.raw_range(s.bit_length, s.signed, s.signed_code)
        for v, ev in enum_entries(s.values):
            _ident(ctx, ev.name, _("value name"), sp + ("values", v), lint.value_name)
            if not lo <= v <= hi:
                msg = (_("value {value} ({name}) does not fit in {bits} bits (signed: {lo}..{hi})") if s.signed
                       else _("value {value} ({name}) does not fit in {bits} bits (unsigned: {lo}..{hi})"))
                ctx.emit("enum-overflow", msg.format(value=v, name=ev.name, bits=s.bit_length, lo=lo, hi=hi),
                         sp + ("values", v))
        _dup_enum_names(ctx, s.values, sp)

        for key in _misplaced_fields(s):
            ctx.emit("encoding-field", _("{key} does not apply to encoding: {encoding}", key=key, encoding=s.encoding),
                     sp + (key,))
        if s.encoding == "flag" and s.bit_length != 1:
            ctx.emit("flag-length", _("flag signal {name!r} is {bits} bits long", name=s.name, bits=s.bit_length),
                     sp + ("bit_length",))
        _check_flags(ctx, s)

        if s.factor == 0:
            ctx.emit("zero-factor", "factor = 0", sp + ("factor",))
        elif s.encoding == "scaled":
            phys = sorted((lo * s.factor + s.offset, hi * s.factor + s.offset))
            if s.min is not None and s.max is not None and s.min > s.max:
                ctx.emit("min-max", _("min {min} > max {max}", min=s.min, max=s.max), sp + ("min",))
            for k in ("min", "max"):
                val = getattr(s, k)
                if val is not None and not phys[0] - 1e-9 <= val <= phys[1] + 1e-9:
                    ctx.emit("range-overflow",
                             _("{key} = {value:g} is outside the representable range {lo:g}..{hi:g} {unit}",
                               key=k, value=val, lo=phys[0], hi=phys[1], unit=s.unit or "").rstrip(), sp + (k,))

        if s.bit_length > 64 and not (s.encoding == "bytes" and s.start_bit % 8 == 0 and s.bit_length % 8 == 0
                                      and s.byte_order == "little_endian"):
            ctx.emit("signal-length", _("signal {name!r} is {bits} bits long: only a byte array (encoding: bytes, "
                                        "little-endian, starting at a byte boundary) can be longer than 64 bits",
                                        name=s.name, bits=s.bit_length), sp + ("bit_length",))
        if s.encoding == "float" and s.bit_length not in (32, 64):
            ctx.emit("float-length", _("signal {name!r}: float must be 32 or 64 bits, got {bits}",
                                       name=s.name, bits=s.bit_length), sp + ("bit_length",))
        if s.encoding == "scaled" and not s.unit and (s.factor != 1 or s.offset != 0):
            ctx.emit("missing-unit", _("physical quantity {name!r} has no unit", name=s.name),
                     sp + ("unit",))
        raw_lo, raw_hi = (lo, hi) if s.encoding != "float" else (None, None)
        for v in s.invalid_values:
            if raw_lo is not None and not raw_lo <= v <= raw_hi:
                ctx.emit("invalid-overflow", _("invalid = {value} does not fit in {bits} bits ({lo}..{hi})",
                                               value=v, bits=s.bit_length, lo=raw_lo, hi=raw_hi), sp + ("invalid",))
            elif raw_lo is not None and s.min is not None and s.max is not None and s.factor != 0:
                pv = v * s.factor + s.offset
                if s.min - 1e-9 <= pv <= s.max + 1e-9:
                    ctx.emit("invalid-in-range",
                             _("invalid = {value} maps to {phys:g}, inside min..max: a receiver cannot tell \"not "
                               "available\" from a real value",
                               value=v, phys=pv), sp + ("invalid",))
        if s.initial is not None and s.factor != 0:
            raw = s.initial_raw
            if raw_lo is not None and not raw_lo <= raw <= raw_hi:
                ctx.emit("initial-range", _("initial = {value:g} → raw {raw} outside {lo}..{hi}",
                                            value=s.initial, raw=raw, lo=raw_lo, hi=raw_hi),
                         sp + ("initial",))
            elif (s.min is not None and s.initial < s.min) or (s.max is not None and s.initial > s.max):
                ctx.emit("initial-range", _("initial = {value:g} outside min/max", value=s.initial), sp + ("initial",))

        if s.description is None and not s._path[-1:] == ("sdo",):
            ctx.emit("missing-description", _("signal {name!r} has no description", name=s.name), sp + ("description",))

        if s.representation in ("ones_complement", "sign_magnitude"):
            ctx.emit("signed-code", _("{name!r}: DBC stores signed values in two's complement only, so the DBC file "
                                      "reads this signal differently", name=s.name), sp + ("representation",))

        if s.mux is not None:
            if selector is None:
                ctx.emit("mux-no-selector", _("signal {name!r} has mux, but the frame has no multiplexer", name=s.name),
                         sp + ("mux",))
            else:
                slo, shi = B.raw_range(selector.bit_length, selector.signed, selector.signed_code)
                known = {v for v, _ in enum_entries(selector.values)}
                for mv in s.mux_values:
                    if not slo <= mv <= shi:
                        ctx.emit("mux-value-overflow",
                                 _("mux {value} does not fit in selector {name!r}", value=mv, name=selector.name),
                                 sp + ("mux",))
                    elif known and mv not in known:
                        ctx.emit("mux-value-unknown",
                                 _("mux {value} is missing from the values of selector {name!r}", value=mv,
                                   name=selector.name), sp + ("mux",))

    _check_overlap(ctx, frame, sigs, selector)


def _dup_enum_names(ctx: _Ctx, values, path) -> None:
    seen, upper = {}, {}
    for v, ev in enum_entries(values):
        if ev.name in PY_KEYWORDS:
            ctx.emit("reserved-identifier", _("value name {name!r} is a Python keyword: the generated module will not "
                                              "import", name=ev.name),
                     path + ("values", v))
        if ev.name in seen:
            ctx.emit("duplicate-enum-name",
                     _("name {name!r} is used for values {a} and {b}", name=ev.name, a=seen[ev.name], b=v),
                     path + ("values", v))
        elif ev.name.upper() in upper:
            ctx.emit("name-collision", _("value {name!r} differs from {other!r} only in case: their C macros will "
                                         "collide", name=ev.name, other=upper[ev.name.upper()]),
                     path + ("values", v))
        seen[ev.name] = v
        upper.setdefault(ev.name.upper(), ev.name)


# Encodings a signal field applies to (a field is set if it differs from its default)
ENCODING_FIELDS = {
    "factor": ("scaled", "float"),
    "offset": ("scaled", "float"),
    "unit": ("raw", "scaled", "float"),
    "min": ("raw", "scaled", "float"),
    "max": ("raw", "scaled", "float"),
    "values": ("enum", "flag"),
    "flags": ("bitfield",),
    "representation": ("raw", "scaled", "enum"),
    "invalid": ("raw", "scaled", "enum"),
    "initial": ("raw", "scaled", "enum", "flag", "float"),
}


def _misplaced_fields(s: Signal) -> list[str]:
    """Fields of a signal that are set but do not apply to its encoding."""
    defaults = {k: Signal.model_fields[k].default for k in ENCODING_FIELDS}
    return [k for k, allowed in ENCODING_FIELDS.items()
            if s.encoding not in allowed and getattr(s, k) not in (defaults[k], None, [], {})]


def _check_flags(ctx: _Ctx, s: Signal) -> None:
    if not s.flags:
        return
    used: dict[int, str] = {}
    for fl in s.flags:
        if fl.bit + fl.bit_length > s.bit_length:
            ctx.emit("flag-out-of-field",
                     _("flag {name!r} (bits {first}..{last}) is outside the {bits}-bit field", name=fl.name,
                       first=fl.bit, last=fl.bit + fl.bit_length - 1, bits=s.bit_length), fl._path + ("bit",))
        for b in range(fl.bit, fl.bit + fl.bit_length):
            if b in used:
                ctx.emit("flag-overlap", _("flag {name!r} overlaps {other!r} at bit {bit}",
                                           name=fl.name, other=used[b], bit=b),
                         fl._path + ("bit",))
                break
            used[b] = fl.name
        lo, hi = B.raw_range(fl.bit_length, False)
        for v, ev in enum_entries(fl.values):
            _ident(ctx, ev.name, _("value name"), fl._path + ("values", v), ctx.cmap.lint.value_name)
            if not lo <= v <= hi:
                ctx.emit("enum-overflow", _("value {value} does not fit in flag {name!r}", value=v, name=fl.name),
                         fl._path + ("values", v))


def _check_overlap(ctx: _Ctx, frame: Frame, sigs: list[Signal], selector) -> None:
    def coexist(a: Signal, b: Signal) -> bool:
        if a.mux is None or b.mux is None:
            return True
        return bool(set(a.mux_values) & set(b.mux_values))

    occ = [set(B.occupied_bits(s.start_bit, s.bit_length, s.byte_order == "big_endian")) for s in sigs]
    for i, a in enumerate(sigs):
        for j in range(i):
            b = sigs[j]
            common = occ[i] & occ[j]
            if common and coexist(a, b):
                lo, hi = min(common), max(common)
                rng = _("bit {bit}", bit=lo) if lo == hi else _("bits {first}..{last}", first=lo, last=hi)
                byte = str(lo // 8) if lo // 8 == hi // 8 else f"{lo // 8}..{hi // 8}"
                ctx.emit("bit-overlap",
                         _("signal {name!r} overlaps {other!r}: {bits} (byte {byte})",
                           name=a.name, other=b.name, bits=rng, byte=byte),
                         a._path)


# --------------------------------------------------------------------------- #


def check(result: LoadResult, disable: Iterable[str] = ()) -> Report:
    """Merge the errors of loading and of the semantic checks."""
    report = Report()
    disabled = set(disable)
    report.extend(d for d in result.report.diagnostics if d.code not in disabled)
    if result.map is not None:
        report.extend(validate_map(result.map, result.source, disabled).diagnostics)
    return report


def validate_file(path, disable: Iterable[str] = ()) -> tuple[LoadResult, Report]:
    res = load(path)
    return res, check(res, disable)


def validate_text(text: str, filename: str = "<text>", disable: Iterable[str] = ()):
    res = loads(text, filename)
    return res, check(res, disable)
