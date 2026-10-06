"""Справочник единиц и их перевод в документах."""

from __future__ import annotations

import pytest

from mapcan.docmodel import ViewBuilder
from mapcan.loader import loads
from mapcan.units import UNITS, dbc_unit, translate_unit

from .conftest import one_bus


@pytest.mark.parametrize(("unit", "lang", "expected"), [
    ("об/мин", "en", "rpm"), ("rpm", "ru", "об/мин"), ("В", "en", "V"), ("V", "ru", "В"),
    ("км/ч", "ru", "км/ч"), ("°C", "en", "°C"),
    ("попугаи", "en", "попугаи"), ("", "en", ""), (None, "ru", None),
    ("Ω", "ru", "Ом"), ("℃", "en", "°C"), (" Ω ", "ru", "Ом"),
])
def test_translate_unit(unit, lang, expected):
    assert translate_unit(unit, lang) == expected


@pytest.mark.parametrize(("unit", "expected"), [
    ("Ом", "Ohm"), ("Ω", "Ohm"), ("Ω", "Ohm"), ("°C", "degC"), ("℃", "degC"),
    ("Н·м", "Nm"), ("В", "V"), ("об/мин", "rpm"), ("попугаи", "попугаи"), ("", ""), (None, None),
])
def test_dbc_unit(unit, expected):
    assert dbc_unit(unit) == expected


def test_dbc_units_are_ascii():
    for ru, en in UNITS:
        assert dbc_unit(ru) == dbc_unit(en)
        assert dbc_unit(en).isascii(), en


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


def test_dbc_export_writes_ascii_units(tmp_path):
    from mapcan.export.dbc import export_dbc

    text = one_bus("""
        - name: status
          id: 0x181
          signals:
            - name: resistance
              start_bit: 0
              bit_length: 16
              unit: Ом
            - name: temperature
              start_bit: 16
              bit_length: 8
              unit: "\u2103"
    """)
    res = loads(text, "t.yaml")
    assert res.map is not None
    warnings: list[str] = []
    [path] = export_dbc(res.map, tmp_path / "bus.dbc", warn=warnings.append)
    dbc = path.read_text(encoding="cp1251")
    assert '"Ohm"' in dbc and '"degC"' in dbc
    assert not warnings
