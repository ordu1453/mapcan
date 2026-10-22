"""CANopen dictionary objects of PDO signals and EDS export."""

from __future__ import annotations

import configparser

import pytest

from mapcan.docmodel import build_view
from mapcan.export.eds import device_eds, export_eds
from mapcan.loader import load

from .conftest import ROOT, codes, one_bus

NODE = ROOT / "examples" / "canopen-node.yaml"


def _eds(name: str = "drive") -> configparser.ConfigParser:
    m = load(NODE).map
    bus = m.buses[0]
    dev = next(d for d in bus.devices if d.name == name)
    eds = configparser.ConfigParser(interpolation=None)
    eds.optionxform = str
    eds.read_string(device_eds(m, bus, dev))
    return eds


def test_example_is_clean():
    assert not {"canopen-od", "od-duplicate"} & codes(NODE.read_text(encoding="utf-8"))


def test_od_rules():
    frame = """
        - name: f
          canopen: pdo_tx1
          length: 4
          signals:
            - {name: a, encoding: raw, description: x, byte: 0, byte_length: 2, index: INDEX}
            - {name: b, encoding: raw, description: x, byte: 2, byte_length: 2, index: 0x2001}
    """
    assert "canopen-od" not in codes(one_bus(frame.replace("INDEX", "0x2000")))
    assert "canopen-od" in codes(one_bus(frame.replace("INDEX", "0x1000")))         # communication area
    assert "od-duplicate" in codes(one_bus(frame.replace("INDEX", "0x2001")))
    assert "canopen-od" in codes(one_bus(frame.replace("INDEX", "0x2000").replace("          canopen: pdo_tx1\n", "")
                                         .replace("length: 4", "length: 4\n          id: 0x300")))
    be = frame.replace("INDEX", "0x2000").replace("byte_length: 2, index: 0x2000",
                                                  "byte_length: 2, byte_order: big_endian, index: 0x2000")
    assert "canopen-od" not in codes(one_bus(be)) and "byte-order-protocol" in codes(one_bus(be))


def test_od_in_documents():
    view = build_view(load(NODE).map)
    sig = next(s for d in view["buses"][0]["devices"] for f in d["frames"] for s in f["signals"]
               if s["name"] == "motor_temp")
    assert sig["encoding"][0] == "OD 0x2100:01" and sig["od"] == "0x2100:01"


def test_eds_structure():
    eds = _eds()
    assert eds["DeviceInfo"]["BaudRate_500"] == "1" and eds["DeviceInfo"]["NrOfTXPDO"] == "2"
    assert eds["DeviceInfo"]["NrOfRXPDO"] == "1" and eds["DeviceInfo"]["VendorName"] == "Example Motors"
    # Communication parameters: COB-ID from node_id, event timer from cycle_ms
    assert eds["1800sub1"]["DefaultValue"] == "$NODEID+0x180" and eds["1800sub5"]["DefaultValue"] == "10"
    assert eds["1400sub1"]["DefaultValue"] == "$NODEID+0x200"
    # Mapping: index, subindex, length
    assert [eds[f"1A01sub{i}"]["DefaultValue"] for i in (1, 2, 3)] == ["0x21000108", "0x21000208", "0x21000310"]
    assert eds["1600sub2"]["DefaultValue"] == "0x60FF0020"
    # Objects: a profile variable and a manufacturer record
    assert eds["6041"]["DataType"] == "0x0006" and eds["6041"]["AccessType"] == "ro"
    assert eds["606C"]["DataType"] == "0x0004"                   # INTEGER32
    assert eds["6040"]["AccessType"] == "rww"                    # received in an RPDO
    assert eds["2100"]["ObjectType"] == "0x9" and eds["2100sub0"]["DefaultValue"] == "3"
    assert eds["ManufacturerObjects"]["1"] == "0x2100"
    assert eds["1017"]["DefaultValue"] == "500"                  # heartbeat


def test_eds_dummies_fill_gaps():
    text = one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 4
          signals:
            - {name: a, encoding: raw, description: x, byte: 0, byte_length: 1, index: 0x2000}
            - {name: b, encoding: raw, description: x, start_bit: 19, bit_length: 5, index: 0x2001}
    """)
    from mapcan.loader import loads

    m = loads(text, "t.yaml").map
    eds = configparser.ConfigParser(interpolation=None)
    eds.optionxform = str
    eds.read_string(device_eds(m, m.buses[0], m.buses[0].devices[0]))
    # 8 bits of a, then a filler byte, 3 filler bits and 5 bits of b
    mapped = [eds[f"1A00sub{i}"]["DefaultValue"] for i in range(1, int(eds["1A00sub0"]["DefaultValue"]) + 1)]
    assert mapped == ["0x20000008", "0x00050008", "0x00010001", "0x00010001", "0x00010001", "0x20010005"]
    assert eds["DummyUsage"]["Dummy0001"] == "1" and eds["DeviceInfo"]["Granularity"] == "1"


def test_export_eds_files(tmp_path):
    files = export_eds(load(NODE).map, tmp_path)
    assert sorted(p.name for p in files) == ["controller.eds", "drive.eds"]
    assert b"\r\n" in files[1].read_bytes()                      # EDS is text with CRLF
    assert export_eds(load(ROOT / "examples" / "j1939.yaml").map, tmp_path / "x") == []


def test_eds_reads_in_canopen_library(tmp_path):
    canopen = pytest.importorskip("canopen")
    (path,) = [p for p in export_eds(load(NODE).map, tmp_path) if p.stem == "drive"]
    node = canopen.Network().add_node(5, str(path))
    node.tpdo.read(from_od=True)
    node.rpdo.read(from_od=True)
    tpdo1 = node.tpdo.map[1]
    assert tpdo1.cob_id == 0x185 and tpdo1.event_timer == 10
    assert [(v.index, v.length) for v in tpdo1.map] == [(0x6041, 16), (0x606C, 32)]
    assert [(v.index, v.subindex) for v in node.tpdo.map[2].map] == [(0x2100, 1), (0x2100, 2), (0x2100, 3)]
    assert [v.index for v in node.rpdo.map[1].map] == [0x6040, 0x60FF]


def test_eds_inhibit_time(tmp_path):
    """inhibit_ms of a TPDO is its inhibit time (sub-index 3) in units of 100 µs."""
    from mapcan.loader import loads

    text = NODE.read_text(encoding="utf-8").replace(
        "cycle_ms: 10\n", "cycle_ms: 10\n            trigger: event\n            inhibit_ms: 0.5\n", 1)
    m = loads(text, "node.yaml").map
    bus = m.buses[0]
    eds = configparser.ConfigParser(interpolation=None)
    eds.optionxform = str
    eds.read_string(device_eds(m, bus, next(d for d in bus.devices if d.name == "drive")))
    assert (eds["1800"]["SubNumber"], eds["1800sub0"]["DefaultValue"]) == ("5", "5")
    assert (eds["1800sub3"]["ParameterName"], eds["1800sub3"]["DefaultValue"]) == ("Inhibit time", "5")
    assert "1801sub3" not in eds
    canopen = pytest.importorskip("canopen")
    (path,) = [p for p in export_eds(m, tmp_path) if p.stem == "drive"]
    node = canopen.Network().add_node(5, str(path))
    node.tpdo.read(from_od=True)
    assert (node.tpdo.map[1].inhibit_time, node.tpdo.map[1].event_timer) == (5, 10)
