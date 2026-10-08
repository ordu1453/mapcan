"""Reference of units: pairs of symbols (ru, en).

The editor offers these units in the Unit field, and documents show them in the document language:
"В" chosen in the Russian interface becomes "V" in an English document, and the other way round.
The map stores the unit as a string as is; the user's own text is not translated.
Look-alike characters (the ohm sign U+2126, "℃" U+2103 etc., pasted from other programs) are normalized
to the usual ones with NFKC, so the reference recognizes them.
"""

from __future__ import annotations

import unicodedata

UNITS: list[tuple[str, str]] = [
    ("В", "V"), ("мВ", "mV"), ("А", "A"), ("мА", "mA"), ("Вт", "W"), ("кВт", "kW"), ("Ом", "Ω"),
    ("А·ч", "Ah"), ("кВт·ч", "kWh"),
    ("°C", "°C"), ("%", "%"),
    ("об/мин", "rpm"), ("км/ч", "km/h"), ("м/с", "m/s"), ("м", "m"), ("мм", "mm"), ("км", "km"),
    ("кг", "kg"), ("Н", "N"), ("Н·м", "N·m"), ("бар", "bar"), ("кПа", "kPa"), ("Па", "Pa"),
    ("Гц", "Hz"), ("с", "s"), ("мс", "ms"), ("мин", "min"), ("ч", "h"),
    ("л", "L"), ("л/ч", "L/h"),
]

# Replacements for DBC: tools read it in different single-byte encodings, so units
# of the reference are written in ASCII Latin (the English symbol with these replacements).
_DBC_ASCII = {"Ω": "Ohm", "°C": "degC", "·": ""}


def _normalize(unit: str) -> str:
    return unicodedata.normalize("NFKC", unit.strip())


_BY_SYMBOL: dict[str, tuple[str, str]] = {}
for _pair in UNITS:
    for _sym in _pair:
        _BY_SYMBOL.setdefault(_normalize(_sym), _pair)


def translate_unit(unit: str | None, lang: str) -> str | None:
    """Symbol of the unit in the language lang if the reference has it; otherwise unit unchanged.
    Russian symbols only for ru, international ones for other languages (ms, V, kOhm)."""
    if not unit:
        return unit
    pair = _BY_SYMBOL.get(_normalize(unit))
    if pair is None:
        return unit
    return pair[0] if lang == "ru" else pair[1]


def dbc_unit(unit: str | None) -> str | None:
    """Unit for DBC: from the reference, the ASCII symbol (Ом, Ω → Ohm; °C → degC; Н·м → Nm);
    the user's own text unchanged."""
    if not unit:
        return unit
    pair = _BY_SYMBOL.get(_normalize(unit))
    if pair is None:
        return unit
    sym = pair[1]
    for k, v in _DBC_ASCII.items():
        sym = sym.replace(k, v)
    return sym
