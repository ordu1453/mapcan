"""Экспорт DBC через cantools (CANalyzer, SavvyCAN, PCAN-View, Wireshark)."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import cantools
from cantools.database.can import Message, Node
from cantools.database.can import Signal as DbcSignal
from cantools.database.can.formats.dbc.dbc_loader import ATTRIBUTE_DEFINITION_VFRAMEFORMAT
from cantools.database.can.formats.dbc.dbc_specifics import DbcSpecifics
from cantools.database.conversion import BaseConversion

from .. import bits as B
from ..model import Bus, CanMap, Signal, enum_entries, text


def _signal(name: str, s: Signal, start: int, length: int, lang: str, comment: str = "",
            choices=None, mux_signal: str | None = None) -> DbcSignal:
    be = s.byte_order == "big_endian"
    dbc_start = B.msb_position(start, length, True) if be else start
    return DbcSignal(
        name=name,
        start=dbc_start,
        length=length,
        byte_order="big_endian" if be else "little_endian",
        is_signed=s.signed and s.kind != "float",
        conversion=BaseConversion.factory(scale=s.factor, offset=s.offset, choices=choices,
                                          is_float=s.kind == "float"),
        raw_initial=s.initial_raw,
        raw_invalid=s.invalid_values[0] if s.invalid_values else None,
        minimum=s.min,
        maximum=s.max,
        unit=s.unit,
        comment=comment or None,
        is_multiplexer=s.multiplexer and mux_signal is not None,
        multiplexer_ids=s.mux_values,
        multiplexer_signal=mux_signal if s.mux is not None else None,
    )


def bus_database(cmap: CanMap, bus: Bus, lang: str | None = None) -> cantools.database.Database:
    lang = lang or cmap.lang
    nodes = [Node(name=d.name, comment=text(d.title, lang) or None) for d in bus.devices]
    messages = []
    for f in bus.all_frames():
        if f.can_id is None:
            continue
        has_mux = any(s.mux is not None for s in f.layout)
        sel = next((s for s in f.layout if s.multiplexer), None) if has_mux else None
        sigs = []
        for s in f.layout:
            desc = text(s.description, lang)
            if s.kind == "bitfield" and s.flags:
                occ = B.occupied_bits(s.start_bit, s.bit_length, s.byte_order == "big_endian")
                for fl in s.flags:
                    if fl.bit + fl.bit_length > len(occ):
                        continue
                    choices = {v: ev.name for v, ev in enum_entries(fl.values)} or None
                    flag_sig = s.model_copy(update={"factor": 1.0, "offset": 0.0, "min": None,
                                                    "max": None, "unit": None, "signed": False})
                    flag_sig._path = s._path
                    sigs.append(_signal(
                        fl.name, flag_sig, occ[fl.bit], fl.bit_length, lang,
                        comment=text(fl.description, lang) or f"{s.name}, бит {fl.bit}",
                        choices=choices, mux_signal=sel.name if sel else None))
                continue
            choices = {v: ev.name for v, ev in enum_entries(s.values)} or None
            sigs.append(_signal(s.name, s, s.start_bit, s.bit_length, lang, desc, choices,
                                sel.name if sel else None))
        senders, receivers = [], list(f.receivers)
        if f.device is not None:
            if f.direction == "tx":
                senders.append(f.device.name)
            elif f.device.name not in receivers:
                receivers.append(f.device.name)
        for sg in sigs:
            sg.receivers = list(receivers)
        cycle = f.transmission.cycle_ms if f.transmission else None
        messages.append(Message(
            frame_id=f.can_id,
            name=f.name,
            length=f.dlc,
            signals=sigs,
            senders=senders,
            comment=text(f.description, lang) or None,
            cycle_time=cycle,
            is_extended_frame=f.extended,
            is_fd=bus.fd,
            protocol="j1939" if bus.protocol == "j1939" else None,
            strict=False,
        ))
    dbc_specifics = None
    if bus.protocol == "j1939":
        # Признак J1939 хранится в атрибуте VFrameFormat = J1939PG; без определения атрибута
        # cantools его не записывает.
        dbc_specifics = DbcSpecifics(attribute_definitions=OrderedDict(
            VFrameFormat=ATTRIBUTE_DEFINITION_VFRAMEFORMAT))
    return cantools.database.Database(messages=messages, nodes=nodes, version=cmap.document.version,
                                      dbc_specifics=dbc_specifics)


def export_dbc(cmap: CanMap, out: str | Path, bus_name: str | None = None) -> list[Path]:
    """Один DBC на шину. Если шина одна или указана, ``out`` — путь к файлу,
    иначе ``out`` трактуется как каталог (или шаблон имени) и создаётся <bus>.dbc."""
    out = Path(out)
    buses = [b for b in cmap.buses if bus_name in (None, b.name)]
    if not buses:
        raise ValueError(f"шина {bus_name!r} не найдена")
    written = []
    for b in buses:
        if len(buses) == 1 and out.suffix.lower() == ".dbc":
            path = out
        else:
            base = out if out.suffix == "" else out.parent
            path = base / f"{b.name}.dbc"
        path.parent.mkdir(parents=True, exist_ok=True)
        db = bus_database(cmap, b)
        path.write_text(db.as_dbc_string(), encoding="cp1251", errors="replace")
        written.append(path)
    return written
