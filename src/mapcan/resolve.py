"""Post-processing of the model: CAN IDs, references to parents, paths in the YAML, SDO layout."""

from __future__ import annotations

from .canopen import CANOPEN_DLC, default_direction
from .model import EnumValue, Frame, MapCan, Signal
from .protocols import frame_id

SDO_COMMANDS = {
    0x23: "WRITE_4_BYTES", 0x27: "WRITE_3_BYTES", 0x2B: "WRITE_2_BYTES", 0x2F: "WRITE_1_BYTE",
    0x40: "READ", 0x43: "READ_4_BYTES", 0x47: "READ_3_BYTES", 0x4B: "READ_2_BYTES",
    0x4F: "READ_1_BYTE", 0x60: "WRITE_OK", 0x80: "ABORT",
}


def resolve(cmap: MapCan) -> None:
    for bi, bus in enumerate(cmap.buses):
        bus._path = ("buses", bi)
        for fi, frame in enumerate(bus.frames):
            _resolve_frame(frame, bus, None, bus._path + ("frames", fi))
        for di, dev in enumerate(bus.devices):
            dev._path = bus._path + ("devices", di)
            for fi, frame in enumerate(dev.frames):
                _resolve_frame(frame, bus, dev, dev._path + ("frames", fi))


def _resolve_frame(frame: Frame, bus, dev, path) -> None:
    frame._path = path
    frame._bus = bus
    frame._device = dev
    # CiA 301 sets the length of CANopen service frames (NMT 2, Heartbeat 1…): it can be omitted.
    # Other frames require length; without it the error is dlc-missing, and 8 bytes are assumed from there on
    if frame.length is None:
        if bus.protocol == "canopen" and frame.type in CANOPEN_DLC:
            frame.length = min(CANOPEN_DLC[frame.type])
        else:
            frame.length, frame._length_missing = 8, True
    if frame.direction is None and dev is not None:
        # A frame without a CANopen type and with another sender is received by the device
        foreign = frame.sender is not None and frame.sender != dev.name
        frame.direction = default_direction(frame.type) or ("rx" if foreign else "tx")
    frame._can_id, frame.extended = frame_id(bus, _source_device(frame, bus, dev), frame)
    for si, sig in enumerate(frame.signals):
        sig._path = path + ("signals", si)
        for fi, fl in enumerate(sig.flags or []):
            fl._path = sig._path + ("flags", fi)
    if frame.sdo:
        for i, ex in enumerate(frame.sdo):
            ex._path = path + ("sdo", i)
        if not frame.signals:
            frame._synthetic = sdo_layout(frame)


def _source_device(frame: Frame, bus, dev):
    """The device whose address goes into a computed ID: on J1939 the source address of an RX frame is the
    sender's (None when the sender is unknown), otherwise the owner's."""
    if bus.protocol == "j1939" and dev is not None and frame.direction == "rx":
        return next((d for d in bus.devices if d.name == frame.sender), None)
    return dev


def sdo_layout(frame: Frame) -> list[Signal]:
    """Layout of an expedited SDO frame from the description of the exchanges."""
    exs = frame.sdo or []
    commands = sorted({e.command for e in exs})
    indices = sorted({e.index for e in exs})
    single_index = len(indices) == 1
    path = frame._path + ("sdo",)

    def mk(**kw) -> Signal:
        s = Signal(**kw)
        s._path = path
        return s

    sigs = [
        mk(name="sdo_command", byte=0, byte_length=1, encoding="enum", value_format="hex",
           description={"ru": "Команда SDO", "en": "SDO command specifier"},
           values={c: EnumValue(name=SDO_COMMANDS.get(c, f"CMD_{c:02X}")) for c in commands}),
        mk(name="sdo_index", byte=1, byte_length=2, encoding="enum" if single_index else "raw",
           value_format="hex",
           description={"ru": "Индекс объекта", "en": "Object index"},
           values={i: EnumValue(name=f"INDEX_{i:04X}") for i in indices} if single_index else None),
        mk(name="sdo_subindex", byte=3, byte_length=1, encoding="enum", value_format="hex",
           multiplexer=single_index and any(e.value for e in exs),
           description={"ru": "Субиндекс объекта", "en": "Object subindex"},
           values={e.subindex: EnumValue(name=e.name.upper(), description=e.description)
                   for e in exs}),
    ]
    if single_index:
        for e in exs:
            if e.value is None:
                continue
            v = e.value
            sigs.append(mk(
                name=v.name, start_bit=32, bit_length=v.bit_length, signed=v.signed,
                encoding=v.encoding,
                factor=v.factor, offset=v.offset, unit=v.unit, min=v.min, max=v.max,
                values=v.values, description=v.description or e.description, mux=e.subindex))
    elif any(e.value for e in exs):
        sigs.append(mk(name="sdo_data", byte=4, byte_length=4, encoding="raw",
                       description={"ru": "Данные", "en": "Data"}))
    return sigs
