"""Справочник единиц и их перевод в документах."""

from __future__ import annotations

import pytest

from mapcan.docmodel import ViewBuilder
from mapcan.loader import loads
from mapcan.units import UNITS, translate_unit

from .conftest import one_bus


@pytest.mark.parametrize(("unit", "lang", "expected"), [
    ("об/мин", "en", "rpm"), ("rpm", "ru", "об/мин"), ("В", "en", "V"), ("V", "ru", "В"),
    ("км/ч", "ru", "км/ч"), ("°C", "en", "°C"),
    ("попугаи", "en", "попугаи"), ("", "en", ""), (None, "ru", None),
])
def test_translate_unit(unit, lang, expected):
    assert translate_unit(unit, lang) == expected


def test_units_symbols_are_unambiguous():
    for i, sym in enumerate(s for pair in UNITS for s in pair):
        others = [p for p in UNITS if sym in p]
        assert len(others) == 1, f"{sym} ({i}) встречается в нескольких парах: {others}"


def _signal_view(lang: str) -> dict:
    text = one_bus("""
        - name: status
          id: 0x181
          signals:
            - name: voltage
              start_bit: 0
              bit_length: 16
              factor: 0.1
              unit: В
              max: 100
    """)
    res = loads(text, "t.yaml")
    assert res.map is not None
    sig = res.map.buses[0].devices[0].frames[0].signals[0]
    return ViewBuilder(res.map, lang).signal(sig, "#fff", None)


def test_document_unit_in_document_language():
    en = _signal_view("en")
    assert any(e.startswith("0.1 V/") for e in en["encoding"]), en["encoding"]
    assert any(v.endswith("100 V") for v in en["values"]), en["values"]
    ru = _signal_view("ru")
    assert any(e.startswith("0.1 В/") for e in ru["encoding"]), ru["encoding"]
