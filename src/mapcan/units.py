"""Справочник единиц измерения: пары обозначений (ru, en).

Редактор предлагает эти единицы в поле «Единица», а документы выводят их на языке документа:
«В», выбранный в русском интерфейсе, в английском документе становится «V», и наоборот.
Единица хранится в карте строкой как есть; свой текст пользователя не переводится.
Символы-двойники (знак ома U+2126, «℃» U+2103 и т. п., вставленные из других программ) приводятся
к обычным через NFKC, поэтому справочник их узнаёт.
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

# Замены для DBC: инструменты читают его в разных однобайтовых кодировках, поэтому единицы
# из справочника выводятся латиницей ASCII (английское обозначение с этими заменами).
_DBC_ASCII = {"Ω": "Ohm", "°C": "degC", "·": ""}


def _normalize(unit: str) -> str:
    return unicodedata.normalize("NFKC", unit.strip())


_BY_SYMBOL: dict[str, tuple[str, str]] = {}
for _pair in UNITS:
    for _sym in _pair:
        _BY_SYMBOL.setdefault(_normalize(_sym), _pair)


def translate_unit(unit: str | None, lang: str) -> str | None:
    """Обозначение единицы на языке lang, если она есть в справочнике; иначе unit без изменений."""
    if not unit:
        return unit
    pair = _BY_SYMBOL.get(_normalize(unit))
    if pair is None:
        return unit
    return pair[1] if lang == "en" else pair[0]


def dbc_unit(unit: str | None) -> str | None:
    """Единица для DBC: из справочника — ASCII-обозначение (Ом, Ω → Ohm; °C → degC; Н·м → Nm),
    свой текст пользователя — без изменений."""
    if not unit:
        return unit
    pair = _BY_SYMBOL.get(_normalize(unit))
    if pair is None:
        return unit
    sym = pair[1]
    for k, v in _DBC_ASCII.items():
        sym = sym.replace(k, v)
    return sym
