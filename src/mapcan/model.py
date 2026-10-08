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
    """Текст с переводами: ключ — код языка ISO 639-1 (ru, en, de…). Строка вместо объекта —
    текст на языке документа."""

    model_config = ConfigDict(extra="allow")
    ru: str | None = None
    en: str | None = None

    @model_validator(mode="after")
    def _language_keys(self) -> LocalizedText:
        for key in self.model_extra or {}:
            if not re.fullmatch(r"[a-z]{2}", key):
                raise ValueError(N_("ключ перевода должен быть кодом языка ISO 639-1 (de, fr…)"))
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
        description=N_("Имя пользователя GitHub автора изменения."),
    )
    changes: list[Text] = Field(default_factory=list)


class Person(_Base):
    """Должностное лицо для блоков «УТВЕРЖДАЮ» / «СОГЛАСОВАНО»."""

    position: str | None = None
    name: str = ""


class Signatures(_Base):
    """Подписи основной надписи ЕСКД (ГОСТ 2.104) и листов утверждения."""

    developed: str | None = Field(None, description=N_("Разраб."))
    checked: str | None = Field(None, description=N_("Пров."))
    tech_control: str | None = Field(None, description=N_("Т. контр."))
    norm_control: str | None = Field(None, description=N_("Н. контр."))
    approved: str | None = Field(None, description=N_("Утв."))


LOGO_FORMATS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")

# Текстовые поля значат одно и то же на всех уровнях карты
TITLE = N_("Название для людей, напр. «Состояния»: подпись в дереве карты и заголовок в документах.")
DESCRIPTION = N_("Что это и зачем: выводится в документах, комментариях сгенерированного кода и DBC.")
COMMENT = N_("Примечание или оговорка: в документах — «Примечание:», в DBC — после описания.")
SHORT = N_("Сокращение устройства, напр. «BMS»: в таблицах документов и в дереве перед названием.")
VALUES = N_("Таблица значений (значение → имя) или имя таблицы из value_tables.")


class Document(_Base):
    title: Text
    subtitle: Text | None = None
    version: str = "0.1"
    date: _dt.date | None = None
    author: str | None = None
    organization: str | None = None
    language: str = Field(pattern=r"^[a-z]{2}$",
                          description=N_("Язык документов по умолчанию: код ISO 639-1 (ru, en, de…)."))
    bit_numbering: Literal["lsb0"] = Field(
        "lsb0",
        description=N_("Нумерация бит: lsb0 — бит 0 это младший бит байта 0. "
        "Поле фиксирует соглашение явно и выводится во всех документах."),
    )
    # Оформление и реквизиты (шаблоны ГОСТ)
    logo: str | None = Field(
        None, description=N_("Логотип предприятия: путь к PNG/JPG/SVG относительно файла карты."))
    designation: str | None = Field(
        None, description=N_("Обозначение документа, напр. «АБВГ.468332.001 Д1» (ЕСКД)."))
    litera: str | None = Field(None, description=N_("Литера документа (ЕСКД), напр. «О1»."))
    city: str | None = Field(None, description=N_("Город для титульного листа."))
    signatures: Signatures | None = None
    approve: Person | None = Field(None, description=N_("Блок «УТВЕРЖДАЮ» титульного листа."))
    agree: list[Person] = Field(default_factory=list, description=N_("Блоки «СОГЛАСОВАНО»."))
    history: list[HistoryEntry] = Field(default_factory=list)


class LintRules(_Base):
    """Настраиваемые правила стиля (проверяются как warning)."""

    signal_name: NameStyle = "snake_case"
    frame_name: NameStyle = "snake_case"
    device_name: NameStyle = "snake_case"
    value_name: NameStyle = "UPPER_SNAKE"
    disable: list[str] = Field(
        default_factory=list, description=N_("Коды правил, которые нужно отключить.")
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
    """Флаг внутри битового поля. ``bit`` — смещение от младшего бита поля."""

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
        description=N_("Кодирование сигнала: enum, flag, bitfield, scaled, raw, float, bytes."))

    # Позиция: каноническая запись
    start_bit: int | None = Field(
        None, ge=0,
        description=N_("Позиция младшего бита (LSB) сигнала в нумерации lsb0."),
    )
    # Длиннее 64 бит — только массив байт (encoding: bytes) в кадре CAN FD или PGN по транспортному протоколу
    bit_length: int | None = Field(None, ge=1, le=J1939_TP_MAX * 8)
    # Позиция: синтаксический сахар
    byte: int | None = Field(None, ge=0, description=N_("Первый байт сигнала."))
    bit: int | None = Field(None, ge=0, le=7, description=N_("Смещение бита в байте."))
    byte_length: int | None = Field(None, ge=1, le=J1939_TP_MAX)

    byte_order: ByteOrder = "little_endian"
    signed: bool = False
    signed_code: SignedCode | None = Field(
        None, description=N_("Код знакового числа: twos_complement — дополнительный (по умолчанию), "
                             "ones_complement — обратный, sign_magnitude — прямой. Сгенерированный код C/Python "
                             "кодирует значение в заданном коде; DBC хранит только дополнительный."))

    values: ValueTableRef | None = Field(None, description=VALUES)
    flags: list[Flag] | None = None

    factor: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    min: float | None = None
    max: float | None = None

    value_format: Literal["dec", "hex"] = Field(
        "dec", description=N_("Как показывать значения enum в документах."))
    multiplexer: bool = Field(False, description=N_("Сигнал-селектор мультиплексора."))
    mux: int | list[int] | None = Field(
        None, description=N_("Значение(я) селектора, при которых сигнал присутствует.")
    )
    initial: float | None = Field(
        None, description=N_("Значение по умолчанию (в физических единицах)."))
    invalid: int | list[int] | None = Field(
        None, description=N_("Сырое значение (или значения), означающее «нет данных / недостоверно»."))
    comment: Text | None = Field(None, description=COMMENT)
    spn: int | None = Field(None, ge=0, le=0x7FFFF,
                            description=N_("J1939: номер параметра (SPN) по SAE J1939-71."))
    index: int | None = Field(None, ge=0, le=0xFFFF,
                              description=N_("CANopen: индекс объекта словаря, отображённого в PDO."))
    subindex: int | None = Field(None, ge=0, le=0xFF,
                                 description=N_("CANopen: субиндекс объекта словаря (по умолчанию 0)."))

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
            raise ValueError(N_("укажите либо start_bit, либо byte/bit, но не оба способа"))
        if self.bit_length is not None and self.byte_length is not None:
            raise ValueError(N_("укажите либо bit_length, либо byte_length"))

        if self.byte_length is not None:
            self.bit_length = self.byte_length * 8
        if self.bit_length is None:
            # Длину можно не указывать только там, где её задаёт кодирование
            if self.encoding == "float":
                self.bit_length = 32
            elif self.encoding == "flag":
                self.bit_length = 1
            else:
                raise ValueError(N_("не задана длина сигнала: bit_length или byte_length"))

        if self.start_bit is None:
            if self.byte is None:
                raise ValueError(N_("не задана позиция сигнала (start_bit или byte)"))
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
    encoding: Literal["enum", "scaled", "raw"] = Field(description=N_("Кодирование значения: enum, scaled, raw."))
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
    """Один SDO-обмен (expedited): команда, индекс, субиндекс, значение."""

    name: str
    description: Text | None = Field(None, description=DESCRIPTION)
    command: int = Field(ge=0, le=0xFF, description=N_("Байт команды (CCS/SCS), напр. 0x2B."))
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
        description=N_("Явный CAN ID. Для CANopen вычисляется из node_id, для J1939 — из PGN."),
    )
    extended: bool = False
    brs: bool | None = Field(None, description=N_(
        "CAN FD: переключение скорости (BRS) — данные на скорости фазы данных. Пусто — как у шины."))
    # J1939
    pgn: int | None = Field(None, ge=0, le=0x3FFFF, description=N_("J1939: номер группы параметров (PGN)."))
    priority: int | None = Field(None, ge=0, le=7, description=N_("J1939: приоритет 0..7 (по умолчанию 6)."))
    destination: int | None = Field(
        None, ge=0, le=0xFF, description=N_("J1939: адрес получателя для PDU1 (по умолчанию 0xFF — всем)."))
    receivers: list[str] = Field(
        default_factory=list, description=N_("Устройства шины, принимающие кадр (имена)."))
    sender: str | None = Field(
        None, description=N_("Устройство шины, передающее кадр, если это не его владелец: "
                             "для RX-кадров (напр. PDO RX узла от мастера) и кадров шины (NMT, SYNC)."))
    dlc: int | None = Field(
        None, ge=0, le=J1939_TP_MAX, description=N_(
            "Длина данных, байт. Обязательна, кроме служебных кадров CANopen (NMT, SYNC, TIME, Heartbeat, "
            "SDO): их длина задана CiA 301. На шине J1939 до 1785 байт — транспортным протоколом."))
    direction: Direction | None = None
    cycle_ms: int | None = Field(None, gt=0, description=N_("Период циклической передачи, мс."))
    trigger: Trigger | None = Field(
        None, description=N_("Нециклическая передача: event — по событию, on_request — по запросу."))
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
    node_id: int | None = Field(None, ge=0, le=0x7F, description=N_("CANopen: адрес узла 1..127."))
    address: int | None = Field(None, ge=0, le=0xFF, description=N_("J1939: адрес источника 0..253."))
    description: Text | None = Field(None, description=DESCRIPTION)
    frames: list[Frame] = Field(default_factory=list)


class Bus(_Base):
    name: str
    title: Text | None = Field(None, description=TITLE)
    interface: str | None = None
    bitrate: int | None = Field(None, gt=0)
    protocol: Protocol = Field(
        description=N_("Протокол: canopen — ID из типа кадра и node_id, j1939 — из PGN и адреса, can — явные ID."))
    fd: bool = False
    brs: bool | None = Field(None, description=N_(
        "CAN FD: переключение скорости (BRS) у кадров по умолчанию. Пусто — включено."))
    description: Text | None = Field(None, description=DESCRIPTION)
    frames: list[Frame] = Field(
        default_factory=list,
        description=N_("Широковещательные кадры без устройства-владельца (NMT, SYNC, TIME)."),
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
    mapcan: Literal[1] = Field(title="mapcan", description=N_("Версия формата файла."))
    include: list[str] = Field(
        default_factory=list,
        description=N_("Подключаемые файлы (пути от файла карты): их шины, устройства, кадры и value_tables "
                       "добавляются к карте."))
    document: Document
    lint: LintRules = Field(default_factory=LintRules)
    value_tables: dict[str, ValueTable] = Field(
        default_factory=dict, description=N_("Именованные таблицы значений: в сигнале — values: <имя>."))
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
