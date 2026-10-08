"""Пост-обработка модели: CAN ID, ссылки на родителей, пути в YAML, раскладка SDO."""

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
    frame._can_id, frame.extended = frame_id(bus, dev, frame)
    # Длина служебного кадра CANopen задана CiA 301 (NMT — 2, Heartbeat — 1…): dlc можно не писать
    if bus.protocol == "canopen" and "dlc" not in frame.model_fields_set and frame.type in CANOPEN_DLC:
        frame.dlc = min(CANOPEN_DLC[frame.type])
    if frame.direction is None and dev is not None:
        # Кадр без типа CANopen с чужим отправителем устройство принимает
        foreign = frame.sender is not None and frame.sender != dev.name
        frame.direction = default_direction(frame.type) or ("rx" if foreign else "tx")
    for si, sig in enumerate(frame.signals):
        sig._path = path + ("signals", si)
        for fi, fl in enumerate(sig.flags or []):
            fl._path = sig._path + ("flags", fi)
    if frame.sdo:
        for i, ex in enumerate(frame.sdo):
            ex._path = path + ("sdo", i)
        if not frame.signals:
            frame._synthetic = sdo_layout(frame)


def sdo_layout(frame: Frame) -> list[Signal]:
    """Раскладка expedited SDO-кадра по описанию обменов."""
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
