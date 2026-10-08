"""Модель данных карты сигналов (формат YAML v1).

Модель описывает *исходный* файл: здесь допускается синтаксический сахар
(``byte``/``bit``/``byte_length`` вместо ``start_bit``/``bit_length``,
короткая запись значений enum и т.п.). После валидации pydantic вызывается
:func:`mapcan.resolve.resolve`, который вычисляет CAN ID, позиции бит и
служебные ссылки (устройство кадра, путь в YAML для сообщений об ошибках).

Нумерация бит: ``lsb0``. Бит 0 — младший бит байта 0, бит 8 — младший бит
байта 1 и т.д. Нумерация байт начинается с 0.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from .i18n import N_

FORMAT_VERSION = 1

ByteOrder = Literal["little_endian", "big_endian"]
SignedCode = Literal["twos_complement", "ones_complement", "sign_magnitude"]
SignalEncoding = Literal["enum", "flag", "bitfield", "scaled", "raw", "bytes", "float"]
Direction = Literal["tx", "rx"]
TxMode = Literal["cyclic", "event", "on_request"]
# Наибольшая длина PGN, передаваемого транспортным протоколом J1939-21 (255 пакетов по 7 байт)
J1939_TP_MAX = 1785
Trigger = Literal["event", "on_request"]
Protocol = Literal["canopen", "j1939", "can"]
NameStyle = Literal["snake_case", "UPPER_SNAKE", "camelCase", "PascalCase", "any"]

FrameType = Literal[
    "nmt", "sync", "emcy", "time",
    "pdo_tx1", "pdo_rx1", "pdo_tx2", "pdo_rx2",
    "pdo_tx3", "pdo_rx3", "pdo_tx4", "pdo_rx4",
    "sdo_tx", "sdo_rx", "heartbeat", "raw",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    # Путь узла в исходном YAML, например ("buses", 0, "devices", 1).
    _path: tuple = PrivateAttr(default=())


class LocalizedText(_Base):
    """Text with translations: the key is an ISO 639-1 language code (ru, en, de…). A plain string instead
    of an object is text in the document language."""

    model_config = ConfigDict(extra="allow")
    ru: str | None = None
    en: str | None = None

    @model_validator(mode="after")
    def _language_keys(self) -> LocalizedText:
        for key in self.model_extra or {}:
            if not re.fullmatch(r"[a-z]{2}", key):
                raise ValueError(N_("a translation key must be an ISO 639-1 language code (de, fr…)"))
        return self


Text = Union[str, LocalizedText]


def text(value: Text | None, lang: str = "ru") -> str:
    """Вернуть текст на нужном языке; без перевода — английский, русский, затем любой доступный."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    data = value.model_dump(exclude_none=True)
    for key in (lang, "en", "ru"):
        if data.get(key):
            return data[key]
    for v in data.values():
        if v:
            return v
    return ""


# --------------------------------------------------------------------------- #
# Документ
# --------------------------------------------------------------------------- #


class HistoryEntry(_Base):
    version: str
    date: _dt.date | None = None
    author: str | None = None
    github: str | None = Field(
        None, pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$",
        description=N_("GitHub username of the change's author."),
    )
    changes: list[Text] = Field(default_factory=list)


class Person(_Base):
    """An official for the "APPROVED" / "AGREED" blocks."""

    position: str | None = None
    name: str = ""


class Signatures(_Base):
    """Signatures for the ESKD title block (GOST 2.104) and approval sheets."""

    developed: str | None = Field(None, description=N_("Developed by (Разраб.)"))
    checked: str | None = Field(None, description=N_("Checked by (Пров.)"))
    tech_control: str | None = Field(None, description=N_("Technical control (Т. контр.)"))
    norm_control: str | None = Field(None, description=N_("Standards control (Н. контр.)"))
    approved: str | None = Field(None, description=N_("Approved by (Утв.)"))


LOGO_FORMATS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")

# Текстовые поля значат одно и то же на всех уровнях карты
TITLE = N_("Name for people, e.g. \"States\": the label in the map tree and the heading in documents.")
DESCRIPTION = N_("What it is and what for: shown in documents, comments of generated code and DBC.")
COMMENT = N_("A note or caveat: \"Note:\" in documents, after the description in DBC.")
SHORT = N_("Device abbreviation, e.g. \"BMS\": in document tables and before the name in the tree.")
VALUES = N_("Value table (value → name) or the name of a table in value_tables.")


class Document(_Base):
    title: Text
    subtitle: Text | None = None
    version: str = "0.1"
    date: _dt.date | None = None
    author: str | None = None
    organization: str | None = None
    language: str = Field(pattern=r"^[a-z]{2}$",
                          description=N_("Default document language: ISO 639-1 code (ru, en, de…)."))
    bit_numbering: Literal["lsb0"] = Field(
        "lsb0",
        description=N_("Bit numbering: lsb0 — bit 0 is the least significant bit of byte 0. The field states the "
                       "convention explicitly and is shown in every document."),
    )
    # Оформление и реквизиты (шаблоны ГОСТ)
    logo: str | None = Field(
        None, description=N_("Company logo: path to a PNG/JPG/SVG relative to the map file."))
    designation: str | None = Field(
        None, description=N_("Document designation, e.g. \"АБВГ.468332.001 Д1\" (ESKD)."))
    litera: str | None = Field(None, description=N_("Document letter (ESKD), e.g. \"О1\"."))
    city: str | None = Field(None, description=N_("City for the title page."))
    signatures: Signatures | None = None
    approve: Person | None = Field(None, description=N_("The \"APPROVED\" block of the title page."))
    agree: list[Person] = Field(default_factory=list, description=N_("The \"AGREED\" blocks."))
    history: list[HistoryEntry] = Field(default_factory=list)


class LintRules(_Base):
    """Configurable style rules (checked as warnings)."""

    signal_name: NameStyle = "snake_case"
    frame_name: NameStyle = "snake_case"
    device_name: NameStyle = "snake_case"
    value_name: NameStyle = "UPPER_SNAKE"
    disable: list[str] = Field(
        default_factory=list, description=N_("Codes of the rules to disable.")
    )


# --------------------------------------------------------------------------- #
# Сигналы
# --------------------------------------------------------------------------- #


class EnumValue(_Base):
    name: str
    description: Text | None = Field(None, description=DESCRIPTION)


ValueTable = dict[int, Union[str, EnumValue]]
# В карте вместо таблицы можно указать имя таблицы из value_tables: загрузчик подставит её
ValueTableRef = Union[ValueTable, str]


def enum_entries(values: ValueTable | None) -> list[tuple[int, EnumValue]]:
    """Нормализовать таблицу значений к списку (значение, EnumValue)."""
    if not values:
        return []
    out = []
    for k, v in values.items():
        out.append((k, v if isinstance(v, EnumValue) else EnumValue(name=v)))
    return sorted(out, key=lambda kv: kv[0])


class Flag(_Base):
    """A flag inside a bit field. ``bit`` is the offset from the field's least significant bit."""

    name: str
    bit: int = Field(ge=0)
    bit_length: int = Field(1, ge=1)
    description: Text | None = Field(None, description=DESCRIPTION)
    values: ValueTableRef | None = Field(None, description=VALUES)


class Signal(_Base):
    name: str
    title: Text | None = Field(None, description=TITLE)
    description: Text | None = Field(None, description=DESCRIPTION)
    encoding: SignalEncoding = Field(
        description=N_("Signal encoding: enum, flag, bitfield, scaled, raw, float, bytes."))

    # Позиция: каноническая запись
    start_bit: int | None = Field(
        None, ge=0,
        description=N_("Position of the signal's least significant bit (LSB) in lsb0 numbering."),
    )
    # Длиннее 64 бит — только массив байт (encoding: bytes) в кадре CAN FD или PGN по транспортному протоколу
    bit_length: int | None = Field(None, ge=1, le=J1939_TP_MAX * 8)
    # Позиция: синтаксический сахар
    byte: int | None = Field(None, ge=0, description=N_("First byte of the signal."))
    bit: int | None = Field(None, ge=0, le=7, description=N_("Bit offset within the byte."))
    byte_length: int | None = Field(None, ge=1, le=J1939_TP_MAX)

    byte_order: ByteOrder = "little_endian"
    signed: bool = False
    signed_code: SignedCode | None = Field(
        None, description=N_("Signed number encoding: twos_complement (default), ones_complement, sign_magnitude. "
                             "Generated C/Python code encodes the value in this code; DBC stores two's complement "
                             "only."))

    values: ValueTableRef | None = Field(None, description=VALUES)
    flags: list[Flag] | None = None

    factor: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    min: float | None = None
    max: float | None = None

    value_format: Literal["dec", "hex"] = Field(
        "dec", description=N_("How enum values are shown in documents."))
    multiplexer: bool = Field(False, description=N_("Multiplexer selector signal."))
    mux: int | list[int] | None = Field(
        None, description=N_("Selector value(s) for which the signal is present.")
    )
    initial: float | None = Field(
        None, description=N_("Default value (in physical units)."))
    invalid: int | list[int] | None = Field(
        None, description=N_("Raw value (or values) meaning \"no data / invalid\"."))
    comment: Text | None = Field(None, description=COMMENT)
    spn: int | None = Field(None, ge=0, le=0x7FFFF,
                            description=N_("J1939: suspect parameter number (SPN) per SAE J1939-71."))
    index: int | None = Field(None, ge=0, le=0xFFFF,
                              description=N_("CANopen: index of the dictionary object mapped into the PDO."))
    subindex: int | None = Field(None, ge=0, le=0xFF,
                                 description=N_("CANopen: subindex of the dictionary object (0 by default)."))

    @property
    def invalid_values(self) -> list[int]:
        if self.invalid is None:
            return []
        return [self.invalid] if isinstance(self.invalid, int) else list(self.invalid)

    @property
    def initial_raw(self) -> int | float | None:
        """Сырое значение по умолчанию (для float — само значение)."""
        if self.initial is None or self.factor == 0:
            return None
        raw = (self.initial - self.offset) / self.factor
        return raw if self.encoding == "float" else round(raw)

    @model_validator(mode="after")
    def _resolve_layout(self) -> Signal:
        sugar = self.byte is not None or self.bit is not None or self.byte_length is not None
        if self.start_bit is not None and sugar:
            raise ValueError(N_("specify either start_bit or byte/bit, not both"))
        if self.bit_length is not None and self.byte_length is not None:
            raise ValueError(N_("specify either bit_length or byte_length"))

        if self.byte_length is not None:
            self.bit_length = self.byte_length * 8
        if self.bit_length is None:
            # Длину можно не указывать только там, где её задаёт кодирование
            if self.encoding == "float":
                self.bit_length = 32
            elif self.encoding == "flag":
                self.bit_length = 1
            else:
                raise ValueError(N_("signal length is not set: bit_length or byte_length"))

        if self.start_bit is None:
            if self.byte is None:
                raise ValueError(N_("signal position is not set (start_bit or byte)"))
            bit = self.bit or 0
            if self.byte_order == "little_endian":
                self.start_bit = self.byte * 8 + bit
            else:
                # Для big-endian «byte» — байт со старшей частью, LSB лежит
                # в последнем байте поля (цепочка Motorola).
                nbytes = (bit + self.bit_length + 7) // 8
                self.start_bit = (self.byte + nbytes - 1) * 8 + bit
        return self

    @property
    def mux_values(self) -> list[int] | None:
        if self.mux is None:
            return None
        return [self.mux] if isinstance(self.mux, int) else list(self.mux)


# --------------------------------------------------------------------------- #
# SDO
# --------------------------------------------------------------------------- #


class SdoValue(_Base):
    name: str
    encoding: Literal["enum", "scaled", "raw"] = Field(description=N_("Value encoding: enum, scaled, raw."))
    description: Text | None = Field(None, description=DESCRIPTION)
    bit_length: Literal[8, 16, 24, 32]
    signed: bool = False
    factor: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    min: float | None = None
    max: float | None = None
    values: ValueTableRef | None = Field(None, description=VALUES)


class SdoExchange(_Base):
    """One SDO transfer (expedited): command, index, subindex, value."""

    name: str
    description: Text | None = Field(None, description=DESCRIPTION)
    command: int = Field(ge=0, le=0xFF, description=N_("Command byte (CCS/SCS), e.g. 0x2B."))
    index: int = Field(ge=0, le=0xFFFF)
    subindex: int = Field(0, ge=0, le=0xFF)
    value: SdoValue | None = None


# --------------------------------------------------------------------------- #
# Кадры, устройства, шины
# --------------------------------------------------------------------------- #


class Frame(_Base):
    name: str
    title: Text | None = Field(None, description=TITLE)
    description: Text | None = Field(None, description=DESCRIPTION)
    type: FrameType = "raw"
    id: int | None = Field(
        None, ge=0, le=0x1FFFFFFF,
        description=N_("Explicit CAN ID. For CANopen it is computed from node_id, for J1939 from the PGN."),
    )
    extended: bool = False
    brs: bool | None = Field(None, description=N_(
        "CAN FD: bit rate switch (BRS), the data phase is sent at the data bit rate. Empty: as set on the bus."))
    # J1939
    pgn: int | None = Field(None, ge=0, le=0x3FFFF, description=N_("J1939: parameter group number (PGN)."))
    priority: int | None = Field(None, ge=0, le=7, description=N_("J1939: priority 0..7 (6 by default)."))
    destination: int | None = Field(
        None, ge=0, le=0xFF, description=N_("J1939: destination address for PDU1 (0xFF, global, by default)."))
    receivers: list[str] = Field(
        default_factory=list, description=N_("Bus devices that receive the frame (names)."))
    sender: str | None = Field(
        None, description=N_("Bus device that transmits the frame when it is not the frame's owner: for RX frames "
                             "(e.g. a node's RPDO sent by the master) and bus frames (NMT, SYNC)."))
    dlc: int | None = Field(
        None, ge=0, le=J1939_TP_MAX, description=N_(
            "Data length, bytes. Required except for CANopen service frames (NMT, SYNC, TIME, Heartbeat, SDO), whose "
            "length is set by CiA 301. Up to 1785 bytes on a J1939 bus, with the transport protocol."))
    direction: Direction | None = None
    cycle_ms: int | None = Field(None, gt=0, description=N_("Cyclic transmission period, ms."))
    trigger: Trigger | None = Field(
        None, description=N_("Non-cyclic transmission: event — on event, on_request — on request."))
    signals: list[Signal] = Field(default_factory=list)
    sdo: list[SdoExchange] | None = None
    comment: Text | None = Field(None, description=COMMENT)

    _can_id: int | None = PrivateAttr(default=None)
    _device: Any = PrivateAttr(default=None)
    _bus: Any = PrivateAttr(default=None)
    _synthetic: list | None = PrivateAttr(default=None)
    _dlc_missing: bool = PrivateAttr(default=False)

    @property
    def layout(self) -> list[Signal]:
        """Сигналы для раскладки: явные или построенные из описания SDO."""
        return self.signals if self.signals or self._synthetic is None else self._synthetic

    @property
    def can_id(self) -> int | None:
        return self._can_id

    @property
    def device(self) -> Device | None:
        return self._device

    @property
    def bus(self) -> Bus:
        return self._bus

    @property
    def bit_rate_switch(self) -> bool | None:
        """BRS flag of a CAN FD frame: its own, else the bus default, else on (None: not a CAN FD bus)."""
        if not self._bus.fd:
            return None
        return next((v for v in (self.brs, self._bus.brs) if v is not None), True)

    @property
    def mode(self) -> TxMode | None:
        """Режим передачи: cyclic, если задан период, иначе trigger (None — не указан)."""
        return "cyclic" if self.cycle_ms is not None else self.trigger

    @property
    def sender_name(self) -> str | None:
        """Передающее устройство: владелец TX-кадра, иначе явный sender (None — отправитель вне карты)."""
        if self._device is not None and self.direction == "tx":
            return self._device.name
        return self.sender

    @property
    def receiver_names(self) -> list[str]:
        """Принимающие устройства: явные receivers и владелец RX-кадра."""
        out = list(self.receivers)
        if self._device is not None and self.direction == "rx" and self._device.name not in out:
            out.append(self._device.name)
        return out


class Device(_Base):
    name: str
    short: str | None = Field(None, description=SHORT)
    title: Text | None = Field(None, description=TITLE)
    node_id: int | None = Field(None, ge=0, le=0x7F, description=N_("CANopen: node address 1..127."))
    address: int | None = Field(None, ge=0, le=0xFF, description=N_("J1939: source address 0..253."))
    description: Text | None = Field(None, description=DESCRIPTION)
    frames: list[Frame] = Field(default_factory=list)


class Bus(_Base):
    name: str
    title: Text | None = Field(None, description=TITLE)
    interface: str | None = None
    bitrate: int | None = Field(None, gt=0)
    protocol: Protocol = Field(
        description=N_("Protocol: canopen — IDs from the frame type and node_id, j1939 — from the PGN and address, can "
                       "— explicit IDs."))
    fd: bool = False
    brs: bool | None = Field(None, description=N_(
        "CAN FD: bit rate switch (BRS) of the frames by default. Empty: on."))
    description: Text | None = Field(None, description=DESCRIPTION)
    frames: list[Frame] = Field(
        default_factory=list,
        description=N_("Broadcast frames without an owning device (NMT, SYNC, TIME)."),
    )
    devices: list[Device] = Field(default_factory=list)

    def all_frames(self) -> list[Frame]:
        out = list(self.frames)
        for d in self.devices:
            out.extend(d.frames)
        return out

    def received_by(self, device: str) -> list[Frame]:
        """Кадры шины, которые принимает устройство: свои RX и чужие, где оно среди receivers."""
        return [f for f in self.all_frames() if device in f.receiver_names]

    def sent_by(self, device: str) -> list[Frame]:
        """Кадры шины, которые передаёт устройство: свои TX и чужие с sender = device."""
        return [f for f in self.all_frames() if f.sender_name == device]


class MapCan(_Base):
    mapcan: Literal[1] = Field(title="mapcan", description=N_("File format version."))
    include: list[str] = Field(
        default_factory=list,
        description=N_("Included files (paths relative to the map file): their buses, devices, frames and value_tables "
                       "are added to the map."))
    document: Document
    lint: LintRules = Field(default_factory=LintRules)
    value_tables: dict[str, ValueTable] = Field(
        default_factory=dict, description=N_("Named value tables: in a signal, values: <name>."))
    buses: list[Bus] = Field(min_length=1)

    _source: str | None = PrivateAttr(default=None)
    _base_dir: Path | None = PrivateAttr(default=None)   # каталог файла карты (для логотипа)

    @property
    def lang(self) -> str:
        return self.document.language

    @property
    def logo_path(self) -> Path | None:
        """Абсолютный путь логотипа (относительный — от каталога карты)."""
        if not self.document.logo:
            return None
        p = Path(self.document.logo).expanduser()
        if not p.is_absolute():
            p = (self._base_dir or Path.cwd()) / p
        return p
