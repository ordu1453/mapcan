"""Post-processing of the model: CAN IDs, references to parents, paths in the YAML, SDO layout."""

from __future__ import annotations

from . import od
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
        _resolve_objects(bus.objects, bus._path)
        for fi, frame in enumerate(bus.frames):
            _resolve_frame(frame, bus, None, bus._path + ("frames", fi))
        for di, dev in enumerate(bus.devices):
            dev._path = bus._path + ("devices", di)
            _resolve_objects(dev.objects, dev._path)
            for fi, frame in enumerate(dev.frames):
                _resolve_frame(frame, bus, dev, dev._path + ("frames", fi))
    _resolve_sources(cmap)


def _resolve_objects(objects, path) -> None:
    for oi, obj in enumerate(objects):
        obj._path = path + ("objects", oi)
        for ei, e in enumerate(obj.entries or []):
            e._path = obj._path + ("entries", ei)


def _resolve_sources(cmap: MapCan) -> None:
    """Values of signals with ``source``: the map version (None if it is not numeric) or the layout CRC."""
    signals = [s for bus in cmap.buses for f in bus.all_frames() for s in f.signals if s.source is not None]
    if not signals:
        return
    values = source_values(cmap)
    for s in signals:
        s._source_value = values.get(s.source)


def source_values(cmap: MapCan) -> dict[str, int]:
    """Values the map gives by ``source`` (of a signal or a dictionary object): the parts of the map version (none
    if it is not numeric) and the layout CRC."""
    from .layout import layout_crc32

    parts = cmap.document.version_parts
    values = {"layout_crc32": layout_crc32(cmap)}
    if parts is not None:
        values.update(zip(("map_version.major", "map_version.minor", "map_version.patch"), parts, strict=True))
    return values


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
    frame._direction_written = frame.direction is not None
    if frame.direction is None and dev is not None:
        frame.direction = derived_direction(frame.type, frame.sender, dev.name)
    frame._can_id, frame.extended = frame_id(bus, _source_device(frame, bus, dev), frame)
    # The device is not in the path: frame names are unique on the bus, wherever a frame is described
    frame._ref = f"{bus.name}.{frame.name}"
    for si, sig in enumerate(frame.signals):
        sig._path = path + ("signals", si)
        sig._ref = f"{frame._ref}.{sig.name}"
        for fi, fl in enumerate(sig.flags or []):
            fl._path = sig._path + ("flags", fi)
            fl._ref = f"{sig._ref}.{fl.name}"
    for i, ex in enumerate(frame.sdo or []):
        ex._path = path + ("sdo", i)
    # An SDO frame is laid out from its exchanges and the dictionary of the device (of the bus for a frame of the bus)
    if not frame.signals and (frame.sdo or (bus.protocol == "canopen" and frame.type in ("sdo_tx", "sdo_rx"))):
        frame._synthetic = sdo_layout(frame, od.dictionary(bus, dev) if bus.protocol == "canopen" else [])


def derived_direction(frame_type: str, sender: str | None, owner: str) -> str:
    """Direction of a frame of a device: from its CANopen function (PDO TX is sent, PDO RX received…); otherwise a
    frame whose sender is another device is received (rx), and the device sends the rest (tx)."""
    return default_direction(frame_type) or ("rx" if sender is not None and sender != owner else "tx")


def _source_device(frame: Frame, bus, dev):
    """The device whose address goes into a computed ID: on J1939 the source address of an RX frame is the
    sender's (None when the sender is unknown), otherwise the owner's."""
    if bus.protocol == "j1939" and dev is not None and frame.direction == "rx":
        return next((d for d in bus.devices if d.name == frame.sender), None)
    return dev


def sdo_object(index: int, subindex: int) -> int:
    """Raw value of bytes 1..3 of an SDO frame: the index (little-endian) and the subindex."""
    return index | subindex << 16


def sdo_layout(frame: Frame, objects: list | None = None) -> list[Signal]:
    """Layout of an expedited SDO frame: the command, the object (bytes 1..3, an enum of the objects of the
    dictionary and of those the exchanges address) and the value of each exchange, selected by the object."""
    exs = frame.sdo or []
    commands = sorted({e.command for e in exs})
    path = frame._path + ("sdo",)

    def mk(**kw) -> Signal:
        s = Signal(**kw)
        s._path = path
        return s

    # Objects of the dictionary: a variable at subindex 0, an array or a record by its entries
    values: dict[int, EnumValue] = {}
    for o in objects or []:
        if o.entries:
            for e in o.entries:
                values[sdo_object(o.index, e.subindex)] = EnumValue(
                    name=f"{o.name}_{e.name}".upper(), description=e.title or e.description)
        else:
            values[sdo_object(o.index, 0)] = EnumValue(name=o.name.upper(), description=o.title or o.description)
    for e in exs:
        values.setdefault(sdo_object(e.index, e.subindex), EnumValue(name=e.name.upper(), description=e.description))

    sigs = [
        mk(name="sdo_command", byte=0, byte_length=1, encoding="enum", value_format="hex",
           description={"ru": "Команда SDO", "en": "SDO command specifier"},
           values={c: EnumValue(name=SDO_COMMANDS.get(c, f"CMD_{c:02X}")) for c in commands} or None),
        mk(name="sdo_object", byte=1, byte_length=3, encoding="enum", value_format="hex",
           multiplexer=any(e.value for e in exs),
           description={"ru": "Объект словаря: индекс (байты 1–2) и субиндекс (байт 3)",
                        "en": "Dictionary object: index (bytes 1–2) and subindex (byte 3)"},
           values={k: values[k] for k in sorted(values)} or None),
    ]
    for e in exs:
        if e.value is None:
            continue
        v = e.value
        sigs.append(mk(
            name=v.name, start_bit=32, bit_length=v.bit_length, representation=v.representation,
            encoding=v.encoding,
            factor=v.factor, offset=v.offset, unit=v.unit, min=v.min, max=v.max,
            values=v.values, description=v.description or e.description, mux=sdo_object(e.index, e.subindex)))
    return sigs
