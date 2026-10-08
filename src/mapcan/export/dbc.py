"""Экспорт DBC через cantools (CANalyzer, SavvyCAN, PCAN-View, Wireshark)."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

import cantools
from cantools.database.can import Bus as DbcBus
from cantools.database.can import Message, Node
from cantools.database.can import Signal as DbcSignal
from cantools.database.can.formats.dbc.dbc_attribute import DbcAttribute
from cantools.database.can.formats.dbc.dbc_attribute_definition import DbcAttributeDefinition
from cantools.database.can.formats.dbc.dbc_loader import ATTRIBUTE_DEFINITION_VFRAMEFORMAT
from cantools.database.can.formats.dbc.dbc_specifics import DbcSpecifics
from cantools.database.conversion import BaseConversion

from .. import bits as B
from ..i18n import _
from ..model import Bus, MapCan, Signal, enum_entries, text
from ..units import dbc_unit

DBC_ENCODING = "cp1251"

# Режим передачи кадра (GenMsgSendType, как в шаблонах Vector CANdb++). Кадры без режима
# получают значение по умолчанию NoMsgSendType.
SEND_TYPES = {"cyclic": "Cyclic", "event": "Spontaneous", "on_request": "OnRequest"}
ATTRIBUTE_DEFINITION_SENDTYPE = DbcAttributeDefinition(
    name="GenMsgSendType", default_value="NoMsgSendType", kind="BO_", type_name="ENUM",
    choices=[*SEND_TYPES.values(), "NoMsgSendType"])
# Тип шины: по "CAN FD" инструменты (и cantools) понимают, что кадры нужно помечать
# VFrameFormat = StandardCAN_FD / ExtendedCAN_FD.
ATTRIBUTE_DEFINITION_BUSTYPE = DbcAttributeDefinition(name="BusType", default_value="", type_name="STRING")


def _comment(*parts: str) -> str | None:
    return "\n".join(p for p in parts if p) or None


def _signal(name: str, s: Signal, start: int, length: int, lang: str, comment: str = "",
            choices=None, mux_signal: str | None = None) -> DbcSignal:
    be = s.byte_order == "big_endian"
    dbc_start = B.msb_position(start, length, True) if be else start
    return DbcSignal(
        name=name,
        start=dbc_start,
        length=length,
        byte_order="big_endian" if be else "little_endian",
        is_signed=s.signed and s.encoding != "float",
        conversion=BaseConversion.factory(scale=s.factor, offset=s.offset, choices=choices,
                                          is_float=s.encoding == "float"),
        raw_initial=s.initial_raw,
        raw_invalid=s.invalid_values[0] if s.invalid_values else None,
        minimum=s.min,
        maximum=s.max,
        unit=dbc_unit(s.unit),
        comment=comment or None,
        is_multiplexer=s.multiplexer and mux_signal is not None,
        multiplexer_ids=s.mux_values,
        multiplexer_signal=mux_signal if s.mux is not None else None,
    )


def bus_database(cmap: MapCan, bus: Bus, lang: str | None = None) -> cantools.database.Database:
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
            desc = _comment(text(s.description, lang) or text(s.title, lang), text(s.comment, lang))
            if s.encoding == "bitfield" and s.flags:
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
                        comment=text(fl.description, lang)
                        or f"{s.name}, {'бит' if lang == 'ru' else 'bit'} {fl.bit}",
                        choices=choices, mux_signal=sel.name if sel else None))
                continue
            choices = {v: ev.name for v, ev in enum_entries(s.values)} or None
            sigs.append(_signal(s.name, s, s.start_bit, s.bit_length, lang, desc, choices,
                                sel.name if sel else None))
        senders = [f.sender_name] if f.sender_name else []
        receivers = [r for r in f.receiver_names if r not in senders]
        for sg in sigs:
            sg.receivers = list(receivers)
        cycle = f.cycle_ms if f.mode == "cyclic" else None
        msg_specifics = None
        if f.mode is not None:
            msg_specifics = DbcSpecifics(attributes=OrderedDict(GenMsgSendType=DbcAttribute(
                value=ATTRIBUTE_DEFINITION_SENDTYPE.choices.index(SEND_TYPES[f.mode]),
                definition=ATTRIBUTE_DEFINITION_SENDTYPE)))
        messages.append(Message(
            frame_id=f.can_id,
            name=f.name,
            length=f.dlc,
            signals=sigs,
            senders=senders,
            comment=_comment(text(f.description, lang), text(f.comment, lang)),
            cycle_time=cycle,
            send_type=SEND_TYPES[f.mode] if f.mode else None,
            dbc_specifics=msg_specifics,
            is_extended_frame=f.extended,
            is_fd=bus.fd,
            protocol="j1939" if bus.protocol == "j1939" else None,
            strict=False,
        ))
    # Без dbc_specifics cantools не пишет ни одного атрибута (BA_): пропали бы период кадров,
    # стартовые значения сигналов и скорость шины.
    definitions = OrderedDict()
    attributes = OrderedDict()
    if bus.protocol == "j1939" or bus.fd:
        # Признак J1939 и FD-кадров хранится в атрибуте VFrameFormat (J1939PG, *_FD);
        # без определения атрибута cantools его не записывает.
        definitions["VFrameFormat"] = ATTRIBUTE_DEFINITION_VFRAMEFORMAT
    if bus.fd:
        definitions["BusType"] = ATTRIBUTE_DEFINITION_BUSTYPE
        attributes["BusType"] = DbcAttribute(value="CAN FD", definition=ATTRIBUTE_DEFINITION_BUSTYPE)
    if any(f.mode is not None for f in bus.all_frames() if f.can_id is not None):
        definitions["GenMsgSendType"] = ATTRIBUTE_DEFINITION_SENDTYPE
    return cantools.database.Database(
        messages=messages, nodes=nodes, version=cmap.document.version,
        buses=[DbcBus(name=bus.name, baudrate=bus.bitrate)],
        dbc_specifics=DbcSpecifics(attributes=attributes, attribute_definitions=definitions))


def unencodable(text_: str, encoding: str = DBC_ENCODING) -> str:
    """Символы, которых нет в кодировке DBC (будут записаны как «?»), без повторов."""
    return "".join(dict.fromkeys(ch for ch in text_ if not ch.encode(encoding, errors="ignore")))


def export_dbc(cmap: MapCan, out: str | Path, bus_name: str | None = None,
               warn: Callable[[str], None] | None = None) -> list[Path]:
    """Один DBC на шину. Если шина одна или указана, ``out`` — путь к файлу,
    иначе ``out`` трактуется как каталог (или шаблон имени) и создаётся <bus>.dbc.

    DBC пишется в cp1251 (её ожидают CANalyzer и другие инструменты под Windows); о символах,
    которых в ней нет, сообщает ``warn``."""
    out = Path(out)
    buses = [b for b in cmap.buses if bus_name in (None, b.name)]
    if not buses:
        raise ValueError(_("шина {name!r} не найдена", name=bus_name))
    written = []
    for b in buses:
        if len(buses) == 1 and out.suffix.lower() == ".dbc":
            path = out
        else:
            base = out if out.suffix == "" else out.parent
            path = base / f"{b.name}.dbc"
        path.parent.mkdir(parents=True, exist_ok=True)
        dbc = bus_database(cmap, b).as_dbc_string()
        if warn is not None and (lost := unencodable(dbc)):
            warn(_("{path}: символы {chars} не входят в кодировку {encoding} и записаны как «?»",
                   path=path, chars=" ".join(repr(c) for c in lost), encoding=DBC_ENCODING))
        path.write_text(dbc, encoding=DBC_ENCODING, errors="replace")
        written.append(path)
    return written
