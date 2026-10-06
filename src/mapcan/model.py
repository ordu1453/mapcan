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
from pathlib import Path
from typing import Any, Literal, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from .i18n import N_

FORMAT_VERSION = 1

ByteOrder = Literal["little_endian", "big_endian"]
SignalKind = Literal["enum", "flag", "bitfield", "metric", "raw", "bytes", "float"]
Direction = Literal["tx", "rx"]
TxMode = Literal["cyclic", "event", "on_request"]
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
    """Текст с переводами. Строка вместо объекта трактуется как язык документа."""

    model_config = ConfigDict(extra="allow")
    ru: str | None = None
    en: str | None = None


Text = Union[str, LocalizedText]


def text(value: Text | None, lang: str = "ru") -> str:
    """Вернуть текст на нужном языке с откатом на любой доступный."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    data = value.model_dump(exclude_none=True)
    if lang in data:
        return data[lang]
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
        description="Имя пользователя GitHub автора изменения.",
    )
    changes: list[Text] = Field(default_factory=list)


class Person(_Base):
    """Должностное лицо для блоков «УТВЕРЖДАЮ» / «СОГЛАСОВАНО»."""

    position: str | None = None
    name: str = ""


class Signatures(_Base):
    """Подписи основной надписи ЕСКД (ГОСТ 2.104) и листов утверждения."""

    developed: str | None = Field(None, description="Разраб.")
    checked: str | None = Field(None, description="Пров.")
    tech_control: str | None = Field(None, description="Т. контр.")
    norm_control: str | None = Field(None, description="Н. контр.")
    approved: str | None = Field(None, description="Утв.")


LOGO_FORMATS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


class Document(_Base):
    title: Text
    subtitle: Text | None = None
    version: str = "0.1"
    date: _dt.date | None = None
    author: str | None = None
    organization: str | None = None
    language: Literal["ru", "en"] = "ru"
    bit_numbering: Literal["lsb0"] = Field(
        "lsb0",
        description="Нумерация бит: lsb0 — бит 0 это младший бит байта 0. "
        "Поле фиксирует соглашение явно и выводится во всех документах.",
    )
    # Оформление и реквизиты (шаблоны ГОСТ)
    logo: str | None = Field(
        None, description="Логотип предприятия: путь к PNG/JPG/SVG относительно файла карты.")
    designation: str | None = Field(
        None, description="Обозначение документа, напр. «АБВГ.468332.001 Д1» (ЕСКД) или «RU.12345678.00001-01» (ЕСПД).")
    litera: str | None = Field(None, description="Литера документа (ЕСКД), напр. «О1».")
    city: str | None = Field(None, description="Город для титульного листа.")
    signatures: Signatures | None = None
    approve: Person | None = Field(None, description="Блок «УТВЕРЖДАЮ» титульного листа.")
    agree: list[Person] = Field(default_factory=list, description="Блоки «СОГЛАСОВАНО».")
    history: list[HistoryEntry] = Field(default_factory=list)


class LintRules(_Base):
    """Настраиваемые правила стиля (проверяются как warning)."""

    signal_name: NameStyle = "snake_case"
    frame_name: NameStyle = "snake_case"
    device_name: NameStyle = "snake_case"
    value_name: NameStyle = "UPPER_SNAKE"
    disable: list[str] = Field(
        default_factory=list, description="Коды правил, которые нужно отключить."
    )


# --------------------------------------------------------------------------- #
# Сигналы
# --------------------------------------------------------------------------- #


class EnumValue(_Base):
    name: str
    description: Text | None = None


ValueTable = dict[int, Union[str, EnumValue]]


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
    description: Text | None = None
    values: ValueTable | None = None


class Signal(_Base):
    name: str
    description: Text | None = None
    kind: SignalKind | None = Field(
        None,
        description="Тип сигнала. Если не задан: values → enum, flags → bitfield, "
        "factor/unit → metric, иначе raw.",
    )

    # Позиция: каноническая запись
    start_bit: int | None = Field(
        None, ge=0,
        description="Позиция младшего бита (LSB) сигнала в нумерации lsb0.",
    )
    bit_length: int | None = Field(None, ge=1, le=64)
    # Позиция: синтаксический сахар
    byte: int | None = Field(None, ge=0, description="Первый байт сигнала.")
    bit: int | None = Field(None, ge=0, le=7, description="Смещение бита в байте.")
    byte_length: int | None = Field(None, ge=1, le=8)

    byte_order: ByteOrder = "little_endian"
    signed: bool = False

    values: ValueTable | None = None
    flags: list[Flag] | None = None

    factor: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    min: float | None = None
    max: float | None = None

    value_format: Literal["dec", "hex"] = Field(
        "dec", description="Как показывать значения enum в документах.")
    multiplexer: bool = Field(False, description="Сигнал-селектор мультиплексора.")
    mux: int | list[int] | None = Field(
        None, description="Значение(я) селектора, при которых сигнал присутствует."
    )
    initial: float | None = Field(
        None, description="Значение по умолчанию (в физических единицах).")
    invalid: int | list[int] | None = Field(
        None, description="Сырое значение (или значения), означающее «нет данных / недостоверно».")
    comment: Text | None = None

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
        return raw if self.kind == "float" else round(raw)

    @model_validator(mode="after")
    def _resolve_layout(self) -> Signal:
        if self.kind is None:
            if self.flags:
                self.kind = "bitfield"
            elif self.values:
                self.kind = "enum"
            elif self.unit is not None or self.factor != 1 or self.offset != 0:
                self.kind = "metric"
            else:
                self.kind = "raw"

        sugar = self.byte is not None or self.bit is not None or self.byte_length is not None
        if self.start_bit is not None and sugar:
            raise ValueError(N_("укажите либо start_bit, либо byte/bit, но не оба способа"))
        if self.bit_length is not None and self.byte_length is not None:
            raise ValueError(N_("укажите либо bit_length, либо byte_length"))

        if self.byte_length is not None:
            self.bit_length = self.byte_length * 8
        if self.bit_length is None:
            if self.kind == "float":
                self.bit_length = 32
            elif self.kind == "flag" or (self.bit is not None and self.byte_length is None):
                self.bit_length = 1
            else:
                self.bit_length = 8

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
    description: Text | None = None
    bit_length: Literal[8, 16, 24, 32] = 32
    signed: bool = False
    factor: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    min: float | None = None
    max: float | None = None
    values: ValueTable | None = None


class SdoExchange(_Base):
    """Один SDO-обмен (expedited): команда, индекс, субиндекс, значение."""

    name: str
    description: Text | None = None
    command: int = Field(ge=0, le=0xFF, description="Байт команды (CCS/SCS), напр. 0x2B.")
    index: int = Field(ge=0, le=0xFFFF)
    subindex: int = Field(0, ge=0, le=0xFF)
    value: SdoValue | None = None


# --------------------------------------------------------------------------- #
# Кадры, устройства, шины
# --------------------------------------------------------------------------- #


class Transmission(_Base):
    mode: TxMode = "cyclic"
    cycle_ms: int | None = Field(None, gt=0)


class Frame(_Base):
    name: str
    title: Text | None = Field(None, description="Короткий заголовок, напр. «СОСТОЯНИЯ».")
    description: Text | None = None
    type: FrameType = "raw"
    id: int | None = Field(
        None, ge=0, le=0x1FFFFFFF,
        description="Явный CAN ID. Для CANopen вычисляется из node_id, для J1939 — из PGN.",
    )
    extended: bool = False
    # J1939
    pgn: int | None = Field(None, ge=0, le=0x3FFFF, description="J1939: номер группы параметров (PGN).")
    priority: int | None = Field(None, ge=0, le=7, description="J1939: приоритет 0..7 (по умолчанию 6).")
    destination: int | None = Field(
        None, ge=0, le=0xFF, description="J1939: адрес получателя для PDU1 (по умолчанию 0xFF — всем).")
    receivers: list[str] = Field(
        default_factory=list, description="Устройства шины, принимающие кадр (имена).")
    dlc: int = Field(8, ge=0, le=64)
    direction: Direction | None = None
    transmission: Transmission | None = None
    cycle_ms: int | None = Field(None, gt=0, description="Сокращение для transmission: cyclic.")
    signals: list[Signal] = Field(default_factory=list)
    sdo: list[SdoExchange] | None = None
    comment: Text | None = None

    _can_id: int | None = PrivateAttr(default=None)
    _device: Any = PrivateAttr(default=None)
    _bus: Any = PrivateAttr(default=None)
    _synthetic: list | None = PrivateAttr(default=None)

    @property
    def layout(self) -> list[Signal]:
        """Сигналы для раскладки: явные или построенные из описания SDO."""
        return self.signals if self.signals or self._synthetic is None else self._synthetic

    @model_validator(mode="after")
    def _normalize(self) -> Frame:
        if self.cycle_ms is not None:
            if self.transmission is not None:
                raise ValueError(N_("cycle_ms задан и на уровне кадра, и в transmission"))
            self.transmission = Transmission(mode="cyclic", cycle_ms=self.cycle_ms)
            self.cycle_ms = None
        return self

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
    def mode(self) -> TxMode | None:
        return self.transmission.mode if self.transmission else None


class Device(_Base):
    name: str
    short: str | None = Field(None, description="Короткое обозначение, напр. «BMS».")
    title: Text | None = None
    node_id: int | None = Field(None, ge=0, le=0x7F, description="CANopen: адрес узла 1..127.")
    address: int | None = Field(None, ge=0, le=0xFF, description="J1939: адрес источника 0..253.")
    description: Text | None = None
    frames: list[Frame] = Field(default_factory=list)


class Bus(_Base):
    name: str
    title: Text | None = None
    interface: str | None = None
    bitrate: int | None = Field(None, gt=0)
    protocol: Protocol = "canopen"
    fd: bool = False
    description: Text | None = None
    frames: list[Frame] = Field(
        default_factory=list,
        description="Широковещательные кадры без устройства-владельца (NMT, SYNC, TIME).",
    )
    devices: list[Device] = Field(default_factory=list)

    def all_frames(self) -> list[Frame]:
        out = list(self.frames)
        for d in self.devices:
            out.extend(d.frames)
        return out


class MapCan(_Base):
    # Ключ до переименования canmap → mapcan тоже принимается: старые карты открываются без правки.
    mapcan: Literal[1] = Field(FORMAT_VERSION, validation_alias=AliasChoices("mapcan", "canmap"),
                               title="mapcan", description="Версия формата файла.")
    document: Document
    lint: LintRules = Field(default_factory=LintRules)
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
