"""J1939, float-сигналы, получатели кадров, значения по умолчанию и «нет данных»."""

from __future__ import annotations

import textwrap

import cantools
import pytest

from mapcan.docmodel import build_view
from mapcan.export.dbc import bus_database
from mapcan.export.text import render
from mapcan.loader import load
from mapcan.protocols import j1939_decode, j1939_id, j1939_is_pdu1

from .conftest import ROOT, codes, run

J1939 = ROOT / "examples" / "j1939.yaml"
VEHICLE = ROOT / "examples" / "vehicle-can.yaml"


@pytest.mark.parametrize("pgn, sa, prio, da, can_id", [
    (0xF004, 0x00, 3, None, 0x0CF00400),     # EEC1, PDU2
    (0xFEEE, 0x00, 6, None, 0x18FEEE00),     # ET1
    (0xEA00, 0xF9, 6, 0x00, 0x18EA00F9),     # Request, PDU1 → двигателю
    (0xEA00, 0xF9, 6, None, 0x18EAFFF9),     # Request всем
])
def test_j1939_id(pgn, sa, prio, da, can_id):
    assert j1939_id(pgn, sa, prio, da) == can_id
    p, g, s, d = j1939_decode(can_id)
    assert (p, g, s) == (prio, pgn, sa)
    assert d == (0xFF if da is None and j1939_is_pdu1(pgn) else da)


def test_example_ids():
    m = load(J1939).map
    ids = {f.name: (f.can_id, f.extended) for f in m.buses[0].all_frames()}
    assert ids["eec1"] == (0x0CF00400, True)
    assert ids["request_to_engine"] == (0x18EA00F9, True)
    assert ids["dash_display"] == (0x18FEFC17, True)


def _bus(frames: str, devices: str = "", protocol: str = "j1939") -> str:
    frames = textwrap.indent(textwrap.dedent(frames).strip("\n"), " " * 10)
    return ("mapcan: 1\ndocument:\n  title: T\n  language: ru\nbuses:\n"
            f"  - name: bus\n    protocol: {protocol}\n    devices:\n"
            "      - name: ecu\n        address: 0x10\n        frames:\n" + frames + "\n" + devices)


def test_j1939_rules():
    assert "frame-id-missing" in codes(_bus("""
        - name: f
          dlc: 1
    """))
    assert "j1939-pdu1-pgn" in codes(_bus("""
        - name: f
          pgn: 0xEA05
    """))
    assert "j1939-destination" in codes(_bus("""
        - name: f
          pgn: 0xFEEE
          destination: 0x00
    """))
    assert "j1939-address" in codes(_bus("""
        - name: f
          pgn: 0xFEEE
    """, devices="      - name: other\n        address: 0x10\n"))
    assert "j1939-address" in codes(_bus("- {name: f, pgn: 0xFEEE}").replace("address: 0x10", "address: 0xFE"))
    assert "j1939-field-protocol" in codes(_bus("""
        - name: f
          id: 0x100
          pgn: 0xFEEE
    """, protocol="can"))
    assert "frame-type-protocol" in codes(_bus("""
        - name: f
          type: pdo_tx1
          pgn: 0xFEEE
    """))


def test_receivers_rule():
    assert "unknown-receiver" in codes(_bus("""
        - name: f
          pgn: 0xFEEE
          receivers: [nobody]
    """))
    assert "unknown-receiver" not in codes(_bus("""
        - name: f
          pgn: 0xFEEE
          receivers: [ecu]
    """))


def test_float_initial_invalid_rules():
    c = codes(_bus("""
        - name: f
          pgn: 0xFEEE
          signals:
            - {name: a, description: x, byte: 0, encoding: float, bit_length: 16}
            - {name: b, encoding: raw, description: x, byte: 2, byte_length: 1, invalid: 0x1FF}
            - {name: c, encoding: metric, description: x, byte: 3, byte_length: 1, factor: 0.5, initial: 200}
            - {name: d, encoding: raw, description: x, byte: 4, byte_length: 1, min: 0, max: 10, initial: 20}
    """))
    assert {"float-length", "invalid-overflow", "initial-range"} <= c


def test_diagnostics_point_to_fields():
    """Сообщения привязаны к полю, которое нужно исправить (редактор подсвечивает его)."""
    _, rep = run(_bus("""
        - name: f
          dlc: 1
        - name: g
          pgn: 0xFEEE
          signals:
            - {name: a, byte: 0, encoding: float, bit_length: 16}
    """))
    node = {d.code: d.node for d in rep.diagnostics}
    assert node["frame-id-missing"][-1] == "pgn"
    assert node["float-length"][-1] == "bit_length"
    assert node["missing-description"][-1] == "description"


def test_dbc_j1939_and_receivers():
    m = load(J1939).map
    db = cantools.database.load_string(bus_database(m, m.buses[0]).as_dbc_string(), "dbc")
    msg = db.get_message_by_name("eec1")
    assert msg.frame_id == 0x0CF00400 and msg.is_extended_frame
    assert msg.protocol == "j1939"
    assert "cluster" in msg.get_signal_by_name("engine_speed").receivers
    assert msg.senders == ["engine"]
    assert msg.get_signal_by_name("engine_speed").raw_initial == 0


def test_dbc_float():
    m = load(VEHICLE).map
    db = cantools.database.load_string(bus_database(m, m.buses[0]).as_dbc_string(), "dbc")
    sig = db.get_message_by_name("bms_status").get_signal_by_name("pack_voltage")
    assert sig.is_float and sig.length == 32
    data = db.encode_message("bms_status", {"pack_voltage": 400.5, "pack_current": -12.25})
    assert db.decode_message("bms_status", data)["pack_voltage"] == 400.5


def test_documents_show_j1939_and_defaults():
    m = load(J1939).map
    v = build_view(m)
    bus = v["buses"][0]
    assert bus["addressing"]["has_pgn"] and bus["addressing"]["has_receivers"]
    eec1 = bus["devices"][0]["frames"][0]
    assert eec1["pgn"] == "0xF004" and eec1["priority"] == "3" and "IC" in eec1["receivers"]
    speed = next(s for s in eec1["signals"] if s["name"] == "engine_speed")
    assert "default: 0 rpm" in speed["values"]
    assert "no data: 0xFFFF" in speed["values"]
    md = render(m, "md")
    assert "| PGN |" in md and "`0xF004`" in md and "**Receivers:**" in md


def test_document_float_encoding():
    m = load(VEHICLE).map
    v = build_view(m)
    fr = v["buses"][1]["devices"][0]["frames"][0]
    assert fr["signals"][0]["encoding"][0] == "float64"
