"""Data model of the signal map (YAML format v1).

The model describes the *source* file: syntactic sugar is allowed here
(``byte``/``bit``/``byte_length`` instead of ``start_bit``/``bit_length``,
the short form of enum values etc.). After pydantic validation,
:func:`mapcan.resolve.resolve` computes the CAN IDs, bit positions and
internal references (the frame's device, the path in the YAML for error messages).

Bit numbering: ``lsb0``. Bit 0 is the least significant bit of byte 0, bit 8 the least significant bit
of byte 1 and so on. Bytes are numbered from 0.
"""

from __future__ import annotations

import copy
import datetime as _dt
import re
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, create_model, model_validator

from .i18n import N_

# Version 1 is still read: the loader converts it (upgrade.upgrade_v1)
FORMAT_VERSION = 2

ByteOrder = Literal["little_endian", "big_endian"]
Representation = Literal["unsigned", "twos_complement", "ones_complement", "sign_magnitude", "float"]
SignalEncoding = Literal["number", "enum", "bitfield", "bytes"]
Charset = Literal["ascii", "utf-8", "latin-1"]
# A value the map gives a signal (see Signal.source); the bits each one needs
SignalSource = Literal["map_version.major", "map_version.minor", "map_version.patch", "layout_crc32"]
VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")
Direction = Literal["tx", "rx"]
# cyclic_event: every cycle_ms and at once on an event (cycle_ms with trigger: event)
TxMode = Literal["cyclic", "cyclic_event", "event", "on_request"]
# Largest PGN sent with the J1939-21 transport protocol (255 packets of 7 bytes)
J1939_TP_MAX = 1785
Trigger = Literal["event", "on_request"]
Protocol = Literal["canopen", "j1939", "can"]
NameStyle = Literal["snake_case", "UPPER_SNAKE", "camelCase", "PascalCase", "any"]

# CANopen function of a frame (CiA 301); a frame without one has an explicit ID ("raw" in derived data)
CanopenFunction = Literal[
    "nmt", "sync", "emcy", "time",
    "pdo_tx1", "pdo_rx1", "pdo_tx2", "pdo_rx2",
    "pdo_tx3", "pdo_rx3", "pdo_tx4", "pdo_rx4",
    "sdo_tx", "sdo_rx", "heartbeat",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    # Path of the node in the source YAML, e.g. ("buses", 0, "devices", 1).
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


def text(value: Text | None, lang: str, fallback: str | None = None) -> str:
    """The text in the given language; without a translation, the fallback (the document language),
    English, then any available."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    data = value.model_dump(exclude_none=True)
    for key in (lang, fallback, "en"):
        if key and data.get(key):
            return data[key]
    for v in data.values():
        if v:
            return v
    return ""


# --------------------------------------------------------------------------- #
# Document
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

# Text fields mean the same on all levels of the map
TITLE = N_("Name for people, e.g. \"States\": the label in the map tree and the heading in documents.")
DESCRIPTION = N_("What it is and what for: shown in documents, comments of generated code and DBC.")
COMMENT = N_("A note or caveat: \"Note:\" in documents, after the description in DBC.")
SHORT = N_("Device abbreviation, e.g. \"BMS\": in document tables and before the name in the tree.")
VALUES = N_("Value table (value → name) or the name of a table in value_tables.")


class Print(_Base):
    """Details that PDF templates print on the title page and in the title block: not part of the network."""

    logo: str | None = Field(
        None, description=N_("Company logo: path to a PNG/JPG/SVG relative to the map file."))
    designation: str | None = Field(
        None, description=N_("Document designation, e.g. \"АБВГ.468332.001 Д1\" (ESKD)."))
    litera: str | None = Field(None, description=N_("Document letter (ESKD), e.g. \"О1\"."))
    city: str | None = Field(None, description=N_("City for the title page."))
    signatures: Signatures | None = None
    approve: Person | None = Field(None, description=N_("The \"APPROVED\" block of the title page."))
    agree: list[Person] = Field(default_factory=list, description=N_("The \"AGREED\" blocks."))


class Document(_Base):
    title: Text
    subtitle: Text | None = None
    # With a history both come from its latest entry and need not be written (resolved in _from_history)
    version: str | None = Field(
        None,
        description=N_("Map version: MAJOR.MINOR or MAJOR.MINOR.PATCH, numbers only (1.4.0). With a revision history "
                       "it is the version of its latest entry and is not written. A device can send it in a frame "
                       "(signal source map_version.*)."))
    date: _dt.date | None = Field(
        None, description=N_("Release date. With a revision history it is the date of its latest entry and is not "
                             "written."))
    author: str | None = None
    organization: str | None = None
    language: str = Field(pattern=r"^[a-z]{2}$",
                          description=N_("Default document language: ISO 639-1 code (ru, en, de…)."))
    bit_numbering: Literal["lsb0"] = Field(
        "lsb0",
        description=N_("Bit numbering: lsb0 — bit 0 is the least significant bit of byte 0. The field states the "
                       "convention explicitly and is shown in every document."),
    )
    print: Print = Field(
        default_factory=Print,
        description=N_("Print details of the title page and the title block (logo, designation, signatures…), "
                       "read by the PDF templates."))
    history: list[HistoryEntry] = Field(default_factory=list)

    # version and date are in the map, not taken from the history
    _version_written: bool = PrivateAttr(default=False)
    _date_written: bool = PrivateAttr(default=False)

    @model_validator(mode="after")
    def _from_history(self) -> Document:
        self._version_written, self._date_written = self.version is not None, self.date is not None
        latest = self.history[0] if self.history else None
        if self.version is None:
            self.version = latest.version if latest else "0.1"
        if self.date is None and latest is not None:
            self.date = latest.date
        return self

    @property
    def version_parts(self) -> tuple[int, int, int] | None:
        """(major, minor, patch) of the version; None when it is not MAJOR.MINOR[.PATCH]."""
        m = VERSION_RE.match(self.version.strip())
        return (int(m[1]), int(m[2]), int(m[3] or 0)) if m else None


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
# Signals
# --------------------------------------------------------------------------- #


class EnumValue(_Base):
    name: str
    description: Text | None = Field(None, description=DESCRIPTION)


ValueTable = dict[int, Union[str, EnumValue]]
# Instead of a table the map can name a table of value_tables: the loader substitutes it
ValueTableRef = Union[ValueTable, str]


def enum_entries(values: ValueTable | None) -> list[tuple[int, EnumValue]]:
    """Normalize a value table to a list of (value, EnumValue)."""
    if not values:
        return []
    out = []
    for k, v in values.items():
        out.append((k, v if isinstance(v, EnumValue) else EnumValue(name=v)))
    return sorted(out, key=lambda kv: kv[0])


_RANGE = re.compile(r"^\s*([+-]?(?:0[xX][0-9a-fA-F]+|\d+))\s*\.\.\s*([+-]?(?:0[xX][0-9a-fA-F]+|\d+))\s*$")
# Raw values: one value, or a list of values and ranges "lo..hi"
RawSet = Union[int, list[Union[int, str]]]


def parse_range(text: str) -> tuple[int, int] | None:
    """ "0xFF00..0xFFFF" → (0xFF00, 0xFFFF); None if it is not a range."""
    m = _RANGE.match(text)
    return (int(m.group(1), 0), int(m.group(2), 0)) if m else None


def raw_set_ranges(s: RawSet | None) -> list[tuple[int, int]]:
    """A set of raw values as ranges (a single value v is v..v)."""
    if s is None:
        return []
    out = []
    for item in s if isinstance(s, list) else [s]:
        r = (item, item) if isinstance(item, int) else parse_range(item)
        if r is not None:
            out.append(r)
    return out


def _check_raw_set(s: RawSet | None) -> None:
    for item in s if isinstance(s, list) else [s] if s is not None else []:
        if isinstance(item, str):
            r = parse_range(item)
            if r is None:
                raise ValueError(N_("a raw value is a number or a range \"lo..hi\", e.g. 0xFF00..0xFFFF"))
            if r[0] > r[1]:
                raise ValueError(N_("a range of raw values must go from the lower bound to the upper one"))


class InvalidRaw(_Base):
    """Raw values without a value, by meaning (J1939-71: "not available" and "error indicator")."""

    not_available: RawSet | None = Field(
        None, description=N_("Raw values meaning “not available”: the sender has no value (e.g. 0xFF)."))
    error: RawSet | None = Field(
        None, description=N_("Raw values meaning “error”: the sender has a fault in this value (e.g. 0xFE)."))

    @model_validator(mode="after")
    def _ranges(self) -> InvalidRaw:
        _check_raw_set(self.not_available)
        _check_raw_set(self.error)
        return self


class Flag(_Base):
    """A flag inside a bit field. ``bit`` is the offset from the field's least significant bit."""

    name: str = Field(
        description=N_("Flag identifier: Latin letters, digits and _. Used in generated code and DBC. Required, "
                       "unique within the frame."))
    bit: int = Field(
        ge=0,
        description=N_("Flag offset from the least significant bit of the bit field: 0 is the field's LSB."))
    bit_length: int = Field(
        1, ge=1,
        description=N_("Flag width in bits, 1 by default. A width above 1 makes a multi-bit value inside the field."))
    description: Text | None = Field(None, description=DESCRIPTION)
    values: ValueTableRef | None = Field(None, description=VALUES)


class Signal(_Base):
    name: str = Field(
        description=N_("Signal identifier: Latin letters, digits and _. Used in generated code and DBC. Required, "
                       "unique within the frame."))
    title: Text | None = Field(
        None,
        description=N_("Human-readable signal name, e.g. “Battery voltage”: its label in the map tree. Optional; "
                       "without it, the tree shows the identifier."))
    description: Text | None = Field(None, description=DESCRIPTION)
    encoding: SignalEncoding = Field(
        description=N_("How the value is interpreted. number — a number: the integer as is, or raw × factor + offset "
                       "with factor and offset, or IEEE 754 with representation: float; enum — a value table; "
                       "bitfield — a set of flags; bytes — a byte array, or text (VIN, software version) with a "
                       "charset."))
    charset: Charset | None = Field(
        None,
        description=N_("Bytes: the field holds text in this character encoding, ascii, utf-8 or latin-1. Without "
                       "it the field is a byte array."))
    terminator: int | str | None = Field(
        None,
        description=N_("Text: the byte that ends a shorter text and fills the rest of the field, e.g. 0x00 or "
                       "\"*\" (as in J1939 text parameters). Without it the text fills the field and unused bytes "
                       "are 0x00."))

    # Position: the canonical form
    start_bit: int | None = Field(
        None, ge=0,
        description=N_("Position of the signal's least significant bit (LSB) in the frame, counting from 0. Bit N "
                       "is in byte N div 8 at position N mod 8."))
    # Longer than 64 bits: only bytes (a byte array or text) in a CAN FD frame or a PGN with the transport protocol
    bit_length: int | None = Field(
        None, ge=1, le=J1939_TP_MAX * 8,
        description=N_("Signal width in bits: 1..64; longer only for encoding: bytes."))
    # Position: syntactic sugar
    byte: int | None = Field(None, ge=0, description=N_("First byte of the signal."))
    bit: int | None = Field(None, ge=0, le=7, description=N_("Bit offset within the byte."))
    byte_length: int | None = Field(
        None, ge=1, le=J1939_TP_MAX,
        description=N_("Signal length in bytes, instead of bit_length."))

    byte_order: ByteOrder = Field(
        "little_endian",
        description=N_("Byte order of a multi-byte signal. little-endian (Intel): least significant byte first, "
                       "typical for CANopen and J1939. big-endian (Motorola): most significant byte first."))
    representation: Representation = Field(
        "unsigned",
        description=N_("How the raw value is read as a number. unsigned — no negative values (default). "
                       "twos_complement — the usual signed integer (−1 = all ones). ones_complement — a negative "
                       "value is its magnitude with all bits inverted (−1 = 1…10). sign_magnitude — the top bit is "
                       "the sign, the rest the magnitude (−1 = 10…01). float — IEEE 754 floating point, 32 bits "
                       "(default) or 64. Generated C and Python code use this representation; DBC stores two's "
                       "complement only, so the export warns about ones' complement and sign-magnitude. "
                       "Formerly signed and signed_code."))

    values: ValueTableRef | None = Field(None, description=VALUES)
    flags: list[Flag] | None = None

    factor: float = Field(
        1.0,
        description=N_("Multiplier: physical value = raw × factor + offset. E.g. 0.1 for voltage in 0.1 V steps."))
    offset: float = Field(
        0.0,
        description=N_("Offset: physical value = raw × factor + offset. E.g. −40 for temperature."))
    unit: str | None = Field(
        None,
        description=N_("Unit of the physical quantity: a standard unit or your own text. Standard units appear in "
                       "documents in the document language (V ↔ В)."))
    min: float | None = Field(
        None,
        description=N_("Allowed minimum in physical units. Leave empty to use the limit of the signal width."))
    max: float | None = Field(
        None,
        description=N_("Allowed maximum in physical units. Leave empty to use the limit of the signal width."))

    value_format: Literal["dec", "hex"] = Field(
        "dec",
        description=N_("How enum table values are shown in documents: decimal or hex."))
    multiplexer: bool = Field(
        False,
        description=N_("Multiplexer selector signal. Multiplexing lets one frame carry different sets of signals: "
                       "the selector value tells which signals the frame currently contains. A frame can have only "
                       "one selector."))
    mux: int | list[int] | None = Field(
        None,
        description=N_("Selector values for which this signal is in the frame, e.g. 0 or 1, 2. Leave empty if the "
                       "signal is always present. Requires a selector signal in the frame."))
    initial: float | None = Field(
        None,
        description=N_("Value after power-up or before the first message is received, in physical units. In C: "
                       "…_INITIAL_RAW; in DBC: GenSigStartValue."))
    source: SignalSource | None = Field(
        None,
        description=N_("The signal always carries a value taken from the map: map_version.major, .minor or .patch "
                       "(document.version) or layout_crc32 (the fingerprint of the frame layouts). The value is "
                       "written to code as the signal's initial value, so a device sends the map it was built "
                       "from."))
    invalid_raw: RawSet | InvalidRaw | None = Field(
        None,
        description=N_("Raw values that carry no value: one value, a list, ranges such as \"0xFF00..0xFFFF\", or by "
                       "meaning: {not_available: …, error: …}. A plain value or list means “not available”. In C: "
                       "…_is_not_available() and …_is_error(). Formerly invalid."))
    comment: Text | None = Field(None, description=COMMENT)
    spn: int | None = Field(None, ge=0, le=0x7FFFF,
                            description=N_("J1939: suspect parameter number (SPN) per SAE J1939-71."))
    index: int | None = Field(None, ge=0, le=0xFFFF,
                              description=N_("CANopen: index of the dictionary object mapped into the PDO."))
    subindex: int | None = Field(None, ge=0, le=0xFF,
                                 description=N_("CANopen: subindex of the dictionary object (0 by default)."))

    _source_value: int | None = PrivateAttr(default=None)     # the value of source, set by resolve()

    @property
    def terminator_byte(self) -> int | None:
        """The terminator of a string as a byte (None: not set or not one byte in the charset)."""
        t = self.terminator
        if isinstance(t, int):
            return t if 0 <= t <= 0xFF else None
        if isinstance(t, str):
            try:
                b = t.encode(self.charset or "ascii")
            except UnicodeEncodeError:
                return None
            return b[0] if len(b) == 1 else None
        return None

    @property
    def signed(self) -> bool:
        """The raw value is a signed integer."""
        return self.representation not in ("unsigned", "float")

    @property
    def is_float(self) -> bool:
        """An IEEE 754 number (``representation: float``)."""
        return self.representation == "float"

    @property
    def is_text(self) -> bool:
        """Text: bytes with a character set."""
        return self.encoding == "bytes" and self.charset is not None

    @property
    def signed_code(self) -> str | None:
        """How a negative value is encoded (None for an unsigned signal)."""
        return self.representation if self.signed else None

    @property
    def invalid_ranges(self) -> dict[str, list[tuple[int, int]]]:
        """Raw values without a value by meaning (not_available, error): ranges lo..hi, a single value as v..v."""
        v = self.invalid_raw
        if v is None:
            return {}
        sets = {"not_available": v} if not isinstance(v, InvalidRaw) else \
            {"not_available": v.not_available, "error": v.error}
        out = {}
        for meaning, s in sets.items():
            ranges = raw_set_ranges(s)
            if ranges:
                out[meaning] = ranges
        return out

    @property
    def invalid_values(self) -> list[int]:
        """Single "not available" values (for DBC and the …_INVALID_RAW constants)."""
        return [lo for lo, hi in self.invalid_ranges.get("not_available", []) if lo == hi]

    @property
    def initial_raw(self) -> int | float | None:
        """Raw initial value (for a float, the value itself); for a signal with ``source``, the value from the map."""
        if self.source is not None:
            return self._source_value
        if self.initial is None or self.factor == 0:
            return None
        raw = (self.initial - self.offset) / self.factor
        return raw if self.is_float else round(raw)

    @model_validator(mode="after")
    def _resolve_layout(self) -> Signal:
        if not isinstance(self.invalid_raw, InvalidRaw):
            _check_raw_set(self.invalid_raw)
        sugar =self.byte is not None or self.bit is not None or self.byte_length is not None
        if self.start_bit is not None and sugar:
            raise ValueError(N_("specify either start_bit or byte/bit, not both"))
        if self.bit_length is not None and self.byte_length is not None:
            raise ValueError(N_("specify either bit_length or byte_length"))

        if self.byte_length is not None:
            self.bit_length = self.byte_length * 8
        if self.bit_length is None:
            # The length can be omitted only for a float: 32 bits
            if self.is_float:
                self.bit_length = 32
            else:
                raise ValueError(N_("signal length is not set: bit_length or byte_length"))

        if self.start_bit is None:
            if self.byte is None:
                raise ValueError(N_("signal position is not set (start_bit or byte)"))
            bit = self.bit or 0
            if self.byte_order == "little_endian":
                self.start_bit = self.byte * 8 + bit
            else:
                # For big-endian, "byte" is the byte with the high part, the LSB is
                # in the last byte of the field (the Motorola chain).
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
    encoding: Literal["number", "enum"] = Field(description=N_("Value encoding: number or enum."))
    description: Text | None = Field(None, description=DESCRIPTION)
    bit_length: Literal[8, 16, 24, 32]
    representation: Literal["unsigned", "twos_complement"] = Field(
        "unsigned",
        description=N_("unsigned or twos_complement (a signed integer). Formerly signed: true."))
    factor: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    min: float | None = None
    max: float | None = None
    values: ValueTableRef | None = Field(None, description=VALUES)


class SdoExchange(_Base):
    """One SDO transfer (expedited): command, index, subindex, value."""

    name: str = Field(
        description=N_("SDO exchange identifier: Latin letters, digits and _. Used in generated code. Required."))
    description: Text | None = Field(None, description=DESCRIPTION)
    command: int = Field(
        ge=0, le=0xFF,
        description=N_("SDO command byte (CCS/SCS), e.g. 0x2B — write 2 bytes, 0x23 — write 4 bytes, 0x40 — read."))
    index: int = Field(
        ge=0, le=0xFFFF,
        description=N_("CANopen object dictionary index, 0x0000..0xFFFF."))
    subindex: int = Field(
        0, ge=0, le=0xFF,
        description=N_("Object dictionary subindex, 0x00..0xFF."))
    value: SdoValue | None = None


# --------------------------------------------------------------------------- #
# Frames, devices, buses
# --------------------------------------------------------------------------- #


class Frame(_Base):
    name: str = Field(
        description=N_("Frame identifier: Latin letters, digits and _. Used in generated code and DBC. Required, "
                       "unique on the bus."))
    title: Text | None = Field(
        None,
        description=N_("Human-readable frame name, e.g. “Status”: the frame heading in documents and its label in "
                       "the map tree. Optional; without it, the tree shows the identifier."))
    description: Text | None = Field(None, description=DESCRIPTION)
    canopen: CanopenFunction | None = Field(
        None,
        description=N_("CANopen function of the frame (CiA 301): nmt, sync, emcy, time, pdo_tx1..4, pdo_rx1..4, "
                       "sdo_tx, sdo_rx, heartbeat. Sets the base ID (e.g. PDO TX 1 = 0x180 + node_id), the default "
                       "direction and the length of service frames. Empty: not a CANopen service frame, the ID is "
                       "set explicitly. Only on CANopen buses. Formerly type (raw: empty)."))
    id: int | None = Field(
        None, ge=0, le=0x1FFFFFFF,
        description=N_("Frame CAN ID: 11-bit (0x000..0x7FF) or 29-bit (up to 0x1FFFFFFF). Leave empty to compute "
                       "it: for CANopen from the type and node_id, for J1939 from the PGN, priority and address."))
    extended: bool = Field(
        False,
        description=N_("Use a 29-bit (extended) identifier instead of an 11-bit one."))
    brs: bool | None = Field(
        None,
        description=N_("Bit rate switch (BRS) of a CAN FD frame: the data field is sent at the data phase bit rate. "
                       "Empty: as set on the bus. Written to DBC (the CANFD_BRS attribute)."))
    # J1939
    pgn: int | None = Field(
        None, ge=0, le=0x3FFFF,
        description=N_("J1939 parameter group number, 0..0x3FFFF. PF < 240 (0xF0) means PDU1, a "
                       "destination-specific frame: the low byte of the PGN must be 0 and the destination is set "
                       "separately. PF ≥ 240 means PDU2, broadcast."))
    priority: int | None = Field(
        None, ge=0, le=7,
        description=N_("J1939 priority 0..7: the top 3 bits of the ID. Lower values mean higher priority. Default 6."))
    destination: int | None = Field(
        None, ge=0, le=0xFF,
        description=N_("Destination address for a J1939 PDU1 frame, 0..255. 0xFF means all nodes."))
    receivers: list[str] = Field(
        default_factory=list,
        description=N_("Devices on this bus that receive the frame. The owner of an RX frame is a receiver even "
                       "without this list. Used in documents, DBC and each device's \"Receives\" summary."))
    sender: str | None = Field(
        None,
        description=N_("Device on this bus that sends the frame when it is not the frame's owner, which then "
                       "receives it (e.g. a node's RPDO sent by the master). Empty: a frame of a device is sent by "
                       "the device (a CANopen RX function: from outside the map), a frame of the bus from outside "
                       "the map. A frame sent by one of your devices is best described at the sender, with the "
                       "receiving devices listed in \"Receivers\"."))
    length: int | None = Field(
        None, ge=0, le=J1939_TP_MAX,
        description=N_("Frame data length in bytes: 0..8, for CAN FD up to 64 (12, 16, 20, 24, 32, 48, 64). "
                       "Required except for CANopen service frames (NMT, SYNC, TIME, Heartbeat, SDO), whose length "
                       "is set by CiA 301. Up to 1785 bytes on a J1939 bus, with the transport protocol. Formerly "
                       "dlc: the DLC on the bus is the code of this length."))
    # Deprecated: the direction follows from the CANopen function and sender (resolve.derived_direction). Still read
    # in version 1 of the format (mapcan migrate removes it); resolve() sets it for every frame of a device.
    direction: Direction | None = Field(
        None,
        description=N_("Deprecated: the direction follows from the CANopen function and the sender, remove it. A frame "
                       "from outside the map goes to the frames of the bus, with the receiving devices in receivers "
                       "(mapcan migrate moves it)."),
        json_schema_extra={"deprecated": True})
    cycle_ms: int | None = Field(
        None, gt=0,
        description=N_("Cyclic transmission period in milliseconds. With trigger: event the frame is also sent at "
                       "once on an event."))
    trigger: Trigger | None = Field(
        None, description=N_("Transmission on an event (event; with cycle_ms also every period) or on request "
                             "(on_request)."))
    inhibit_ms: float | None = Field(
        None, gt=0,
        description=N_("Minimum time between two transmissions in milliseconds (inhibit time): the frame is not "
                       "sent again sooner. May be fractional, e.g. 0.5 (CANopen counts it in 0.1 ms). In DBC: "
                       "GenMsgDelayTime; in EDS: the PDO's inhibit time; in C: …_INHIBIT_US."))
    timeout_ms: int | None = Field(
        None, gt=0,
        description=N_("Receive timeout in milliseconds: when the frame has not arrived for this long, the receivers "
                       "treat its data as lost. Usually a few periods, e.g. 3 × cycle_ms. In code: …_TIMEOUT_MS."))
    signals: list[Signal] = Field(default_factory=list)
    sdo: list[SdoExchange] | None = None
    comment: Text | None = Field(None, description=COMMENT)

    _can_id: int | None = PrivateAttr(default=None)
    _device: Any = PrivateAttr(default=None)
    _bus: Any = PrivateAttr(default=None)
    _synthetic: list | None = PrivateAttr(default=None)
    _length_missing: bool = PrivateAttr(default=False)
    _direction_written: bool = PrivateAttr(default=False)   # direction is in the map (deprecated)

    @property
    def type(self) -> str:
        """The CANopen function, or "raw" for a frame without one (the former field type)."""
        return self.canopen or "raw"

    @property
    def layout(self) -> list[Signal]:
        """Signals of the layout: the explicit ones or those built from the SDO description."""
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
        """Transmission mode: cyclic if a period is set (cyclic_event with trigger: event), otherwise trigger
        (None: not set)."""
        if self.cycle_ms is None:
            return self.trigger
        return "cyclic_event" if self.trigger == "event" else "cyclic"

    @property
    def sender_name(self) -> str | None:
        """Sending device: the owner of a TX frame, otherwise the explicit sender (None: the sender is outside the
        map)."""
        if self._device is not None and self.direction == "tx":
            return self._device.name
        return self.sender

    @property
    def receiver_names(self) -> list[str]:
        """Receiving devices: the explicit receivers and the owner of an RX frame."""
        out = list(self.receivers)
        if self._device is not None and self.direction == "rx" and self._device.name not in out:
            out.append(self._device.name)
        return out


class Device(_Base):
    name: str = Field(
        description=N_("Device identifier: Latin letters, digits and _. Used in generated code, DBC, and frame "
                       "senders and receivers. Required."))
    short: str | None = Field(
        None,
        description=N_("Short device abbreviation for tables and headings in documents, e.g. BMS. If set, the map "
                       "tree shows it before the full name. If empty, documents use the identifier in uppercase."))
    title: Text | None = Field(
        None,
        description=N_("Full human-readable device name, e.g. “Battery management system”. Shown in the device "
                       "section heading in documents and in the map tree. Required."))
    node_id: int | None = Field(
        None, ge=0, le=0x7F,
        description=N_("CANopen node address 1..127 (0x01..0x7F). Added to the base ID of PDO, SDO, EMCY and "
                       "Heartbeat frames."))
    address: int | None = Field(
        None, ge=0, le=0xFF,
        description=N_("J1939 source address 0..253 (0x00..0xFD). Forms the low byte of every frame ID the device "
                       "sends; 254 and 255 are reserved."))
    description: Text | None = Field(None, description=DESCRIPTION)
    frames: list[Frame] = Field(default_factory=list)


class Bus(_Base):
    name: str = Field(
        description=N_("Bus identifier: Latin letters, digits and _, no spaces. Used in DBC and C file names and as "
                       "an anchor in documents. Required."))
    title: Text | None = Field(
        None,
        description=N_("Human-readable bus name, e.g. “Bus 1” or “Powertrain CAN”. Used as the section heading in "
                       "documents and as the bus label in the map tree. Required."))
    connector: str | None = Field(
        None,
        description=N_("Connector or harness of the bus, e.g. “X3, pins 4–5”. Used in documents only. The CAN adapter "
                       "and channel of a workstation are not part of the map."))
    bitrate: int | None = Field(
        None, gt=0,
        description=N_("Bus bitrate in bit/s, e.g. 250000 or 500000. Shown in documents and DBC."))
    protocol: Protocol = Field(
        description=N_("Higher-layer protocol. CANopen: the frame ID is computed from the frame type and node_id; "
                       "SAE J1939: from PGN, priority and the device address; CAN: each frame has an explicit ID."))
    fd: bool = Field(
        False,
        description=N_("CAN FD bus: frames up to 64 bytes (DLC 0..8, 12, 16, 20, 24, 32, 48, 64)."))
    brs: bool | None = Field(
        None,
        description=N_("Default bit rate switch (BRS) of CAN FD frames: the data field is sent at the data phase "
                       "bit rate. Turn it off if the nodes or the wiring of the bus cannot handle the higher rate. "
                       "A frame can set its own value."))
    data_bitrate: int | None = Field(
        None, gt=0,
        description=N_("CAN FD: bit rate of the data phase in bit/s, e.g. 2000000. Frames with the bit rate switch "
                       "(BRS) send their data field at this rate; it is used in the bus load estimate and shown in "
                       "documents."))
    sample_point: float | None = Field(
        None, ge=50, le=100,
        description=N_("Sample point of the (nominal) bit rate, percent of the bit time, e.g. 87.5. All nodes of a "
                       "bus should use the same one. Shown in documents."))
    data_sample_point: float | None = Field(
        None, ge=50, le=100,
        description=N_("CAN FD: sample point of the data phase, percent, e.g. 75. Shown in documents."))
    description: Text | None = Field(None, description=DESCRIPTION)
    frames: list[Frame] = Field(
        default_factory=list,
        description=N_("Frames whose sender is outside the map, with the receiving devices in receivers; also "
                       "CANopen broadcast frames (NMT, SYNC, TIME)."),
    )
    devices: list[Device] = Field(default_factory=list)

    def all_frames(self) -> list[Frame]:
        out = list(self.frames)
        for d in self.devices:
            out.extend(d.frames)
        return out

    def received_by(self, device: str) -> list[Frame]:
        """Frames of the bus the device receives: its own RX ones and others' where it is among the receivers."""
        return [f for f in self.all_frames() if device in f.receiver_names]

    def sent_by(self, device: str) -> list[Frame]:
        """Frames of the bus the device sends: its own TX ones and others' with sender = device."""
        return [f for f in self.all_frames() if f.sender_name == device]


class MapCan(_Base):
    mapcan: Literal[2] = Field(
        title="mapcan",
        description=N_("File format version: 2. A map of version 1 is still read; mapcan migrate rewrites it."))
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
    _base_dir: Path | None = PrivateAttr(default=None)   # folder of the map file (for the logo)

    @property
    def lang(self) -> str:
        return self.document.language

    @property
    def logo_path(self) -> Path | None:
        """Absolute path of the logo (a relative one is relative to the map's folder)."""
        if not self.document.print.logo:
            return None
        p = Path(self.document.print.logo).expanduser()
        if not p.is_absolute():
            p = (self._base_dir or Path.cwd()) / p
        return p


# --------------------------------------------------------------------------- #
# Included file (for its JSON Schema; the loader merges it into the map)
# --------------------------------------------------------------------------- #


def _partial(model: type[_Base], name: str, keep: tuple[str, ...]) -> type[_Base]:
    """The model with every field optional except ``keep``: a bus of an included file may only add devices and
    frames to a bus of the main file."""
    fields: dict[str, Any] = {}
    for n, f in model.model_fields.items():
        fi = copy.copy(f)
        if n not in keep:
            fi.default, fi.default_factory = None, None
        fields[n] = (f.annotation if n in keep else Optional[f.annotation], fi)
    return create_model(name, __base__=_Base, __doc__=model.__doc__, **fields)


BusPart = _partial(Bus, "BusPart", keep=("name",))


class MapPart(_Base):
    """A file of ``include``: buses and value tables added to the map named by ``part_of``."""

    mapcan: Literal[2] = Field(title="mapcan", description=N_("File format version: the same as the map's."))
    part_of: str = Field(
        description=N_("The map this file belongs to: the path of its file, relative to this one. The map includes "
                       "this file in its include list."))
    value_tables: dict[str, ValueTable] = Field(
        default_factory=dict, description=N_("Named value tables: in a signal, values: <name>."))
    buses: list[BusPart] = Field(  # type: ignore[valid-type]
        default_factory=list,
        description=N_("New buses, or buses of the map (by name) that get more devices and frames."))
