"""J1939, float signals, frame receivers, initial values and "no data"."""

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
    (0xEA00, 0xF9, 6, 0x00, 0x18EA00F9),     # Request, PDU1 → to the engine
    (0xEA00, 0xF9, 6, None, 0x18EAFFF9),     # Request to all
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
          length: 1
    """))
    assert "j1939-pdu1-pgn" in codes(_bus("""
        - name: f
          pgn: 0xEA05
          length: 8
    """))
    assert "j1939-destination" in codes(_bus("""
        - name: f
          pgn: 0xFEEE
          destination: 0x00
          length: 8
    """))
    assert "j1939-address" in codes(_bus("""
        - name: f
          pgn: 0xFEEE
          length: 8
    """, devices="      - name: other\n        address: 0x10\n"))
    assert "j1939-address" in codes(_bus("- {name: f, pgn: 0xFEEE}").replace("address: 0x10", "address: 0xFE"))
    assert "j1939-field-protocol" in codes(_bus("""
        - name: f
          id: 0x100
          pgn: 0xFEEE
          length: 8
    """, protocol="can"))
    assert "frame-type-protocol" in codes(_bus("""
        - name: f
          canopen: pdo_tx1
          pgn: 0xFEEE
          length: 8
    """))


def test_rx_frame_source_address():
    """The source address of an RX frame is the sender's, not the receiver's."""
    engine = "      - name: engine\n        address: 0x00\n        frames: []\n"
    res, rep = run(_bus("- {name: eec1, pgn: 0xF004, length: 8, direction: rx, sender: engine}", devices=engine))
    assert res.map is not None and not rep.errors
    [f] = res.map.buses[0].all_frames()
    assert f.can_id == 0x18F00400 and f.sender_name == "engine"
    # A sender implies RX
    res, _ = run(_bus("- {name: eec1, pgn: 0xF004, length: 8, sender: engine}", devices=engine))
    assert res.map.buses[0].all_frames()[0].can_id == 0x18F00400
    # Without sender and id the source address is unknown
    res, rep = run(_bus("- {name: eec1, pgn: 0xF004, length: 8, direction: rx}"))
    [d] = [d for d in rep.diagnostics if d.code == "frame-id-missing"]
    assert "sender" in d.message and d.node[-1] == "sender"
    # The sender without an address
    rep = run(_bus("- {name: eec1, pgn: 0xF004, length: 8, sender: engine}",
                   devices="      - name: engine\n        frames: []\n"))[1]
    assert "frame-id-missing" in rep.codes()
    # An explicit id is kept, and a TX frame still takes the owner's address
    res, rep = run(_bus("- {name: eec1, pgn: 0xF004, id: 0x0CF00400, extended: true, length: 8, direction: rx}"))
    assert "frame-id-missing" not in rep.codes() and res.map.buses[0].all_frames()[0].can_id == 0x0CF00400
    res, _ = run(_bus("- {name: eec1, pgn: 0xF004, length: 8}"))
    assert res.map.buses[0].all_frames()[0].can_id == 0x18F00410


def test_receivers_rule():
    assert "unknown-receiver" in codes(_bus("""
        - name: f
          pgn: 0xFEEE
          length: 8
          receivers: [nobody]
    """))
    assert "unknown-receiver" not in codes(_bus("""
        - name: f
          pgn: 0xFEEE
          length: 8
          receivers: [ecu]
    """))


def test_float_initial_invalid_rules():
    c = codes(_bus("""
        - name: f
          pgn: 0xFEEE
          length: 8
          signals:
            - {name: a, description: x, byte: 0, encoding: float, bit_length: 16}
            - {name: b, encoding: raw, description: x, byte: 2, byte_length: 1, invalid: 0x1FF}
            - {name: c, encoding: scaled, description: x, byte: 3, byte_length: 1, factor: 0.5, initial: 200}
            - {name: d, encoding: raw, description: x, byte: 4, byte_length: 1, min: 0, max: 10, initial: 20}
    """))
    assert {"float-length", "invalid-overflow", "initial-range"} <= c


def test_diagnostics_point_to_fields():
    """Messages are bound to the field to fix (the editor highlights it)."""
    _, rep = run(_bus("""
        - name: f
          length: 1
        - name: g
          pgn: 0xFEEE
          length: 8
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


def _sig(extra: str, length: int = 8, frame_extra: str = "", protocol: str = "j1939") -> str:
    return _bus(f"""
        - name: f
          pgn: 0xFF10
          length: {length}{frame_extra}
          signals:
            - {{name: a, encoding: raw, description: x, byte: 0, byte_length: 1, {extra}}}
    """, protocol=protocol)


def test_spn_rules():
    assert not {"j1939-field-protocol", "j1939-spn-duplicate"} & codes(_sig("spn: 190"))
    assert "j1939-field-protocol" in codes(_sig("spn: 190", protocol="can").replace("pgn: 0xFF10", "id: 0x100"))
    two = _bus("""
        - name: f
          pgn: 0xFF10
          length: 2
          signals:
            - {name: a, encoding: raw, description: x, byte: 0, byte_length: 1, spn: 190}
            - {name: b, encoding: raw, description: x, byte: 1, byte_length: 1, spn: 190}
    """)
    assert "j1939-spn-duplicate" in codes(two)
    res, _ = run(_sig("spn: 600000"))     # more than 19 bits
    assert res.map is None


def test_spn_in_outputs(tmp_path):
    m = load(J1939).map
    eec1 = next(f for f in m.buses[0].all_frames() if f.name == "eec1")
    speed = next(s for s in eec1.signals if s.name == "engine_speed")
    assert speed.spn == 190
    # Documents: SPN in the first line of the encoding
    view = build_view(m)
    sig = next(s for d in view["buses"][0]["devices"] for f in d["frames"] if f["name"] == "eec1"
               for s in f["signals"] if s["name"] == "engine_speed")
    assert sig["encoding"][0] == "SPN 190" and sig["spn"] == 190
    # DBC: the SPN attribute of the signal
    db = cantools.database.load_string(bus_database(m, m.buses[0]).as_dbc_string(), database_format="dbc")
    attr = db.get_message_by_name("eec1").get_signal_by_name("engine_speed").dbc.attributes["SPN"]
    assert attr.value == 190
    # Code: constants
    from mapcan.codegen.c import generate_c
    from mapcan.codegen.py import generate_py

    header = next(p for p in generate_c(m, tmp_path / "c") if p.suffix == ".h").read_text(encoding="utf-8")
    assert "#define EEC1_ENGINE_SPEED_SPN 190u" in header
    module = generate_py(m, tmp_path / "py")[0].read_text(encoding="utf-8")
    assert "EEC1_ENGINE_SPEED_SPN = 190" in module


def test_spn_survives_dbc_import(tmp_path):
    from mapcan.export.dbc import export_dbc
    from mapcan.importers.dbc import import_dbc
    from mapcan.loader import loads

    (dbc,) = export_dbc(load(J1939).map, tmp_path)
    m = loads(import_dbc(dbc)[0], "x.yaml").map
    spns = {s.name: s.spn for f in m.buses[0].all_frames() for s in f.signals}
    assert spns["engine_speed"] == 190 and spns["software_id"] == 234


def test_transport_protocol():
    c = codes(_sig("spn: 1", length=20))
    assert "j1939-tp" in c and "dlc-range" not in c
    assert "dlc-range" in codes(_sig("spn: 1", length=20, protocol="can").replace("pgn: 0xFF10", "id: 0x100")
                                .replace(", spn: 1", ""))
    res, rep = run(_bus("""
        - name: f
          pgn: 0xEF00
          destination: 0x17
          length: 30
    """))
    tp = next(d for d in rep.diagnostics if d.code == "j1939-tp")
    assert "RTS/CTS" in tp.message
    res, _ = run(_sig("spn: 1", length=1786))   # more than 255 packets
    assert res.map is None


def test_transport_protocol_bus_load():
    from mapcan.validate import _frame_bits, _tp_bits

    m = load(J1939).map
    soft = next(f for f in m.buses[0].all_frames() if f.name == "soft")
    # 20 bytes: 3 TP.DT packets and TP.CM BAM, 4 frames of 8 bytes
    assert _tp_bits(soft) == 4 * _frame_bits(8, True)


def test_long_signals_only_byte_arrays():
    raw = _sig("spn: 1", length=20).replace("byte_length: 1", "byte_length: 12")
    assert "signal-length" in codes(raw)
    assert "signal-length" not in codes(raw.replace("encoding: raw", "encoding: bytes"))
