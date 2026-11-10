"""Object dictionary of a CANopen bus and its devices (objects): validation, the dictionary of a device, EDS."""

from __future__ import annotations

import configparser
import textwrap

from mapcan import od
from mapcan.export.eds import device_eds
from mapcan.loader import loads

from .conftest import DATA, codes, run

# Software version and map version every device has; the drive has its own map version (another index) and an
# array of its own. A master reads the versions by SDO.
MAP = (DATA / "canopen-od.yaml").read_text(encoding="utf-8")


def _map(extra: str = "") -> str:
    return MAP + (textwrap.indent(textwrap.dedent(extra), " " * 10) if extra else "")


def test_clean():
    res, report = run(_map())
    assert res.map is not None
    assert not [d for d in report.diagnostics if d.code.startswith("od")], [d.format() for d in report.diagnostics]


def test_dictionary_of_a_device():
    m = loads(_map(), "m.yaml").map
    bus = m.buses[0]
    objects = od.dictionary(bus, bus.devices[0])
    assert [o.index for o in objects] == [0x100A, 0x1018, 0x2000, 0x2100]
    assert next(o for o in objects if o.index == 0x2000).data_type == "unsigned8"    # the device's own
    assert [o.kind for o in objects] == ["var", "record", "var", "array"]
    assert [o.index for o in od.dictionary(bus, None)] == [0x100A, 0x1018, 0x2000]
    assert od.area_of(0x1018).title == "Communication profile" and od.area_of(0xA000).first == 0xA000


def test_sdo_frame_lists_the_dictionary():
    # Bytes 1..3 of an SDO frame: an enum of the objects of the device's dictionary, the bus's ones included
    m = loads(_map(), "m.yaml").map
    frame = m.buses[0].devices[0].frames[0]
    obj = next(s for s in frame.layout if s.name == "sdo_object")
    assert (obj.start_bit, obj.bit_length) == (8, 24)
    assert {k: v.name for k, v in obj.values.items()} == {
        0x00100A: "SOFTWARE_VERSION", 0x011018: "IDENTITY_VENDOR_ID", 0x021018: "IDENTITY_PRODUCT_CODE",
        0x031018: "IDENTITY_REVISION_NUMBER", 0x002000: "MAP_VERSION", 0x012100: "LIMITS_MAX_SPEED",
        0x022100: "LIMITS_MAX_TORQUE"}


def test_unknown_object():
    sdo = """\
    - name: drive_sdo_tx
      canopen: sdo_tx
      sdo:
        - {name: answer, command: 0x43, index: 0x2200}
        - {name: count, command: 0x4F, index: 0x2100, subindex: 0}
        - {name: entry9, command: 0x4B, index: 0x2100, subindex: 9}
    """
    report = run(_map(sdo))[1]
    unknown = [d.node[-2:] for d in report.diagnostics if d.code == "od-unknown"]
    assert len(unknown) == 2 and all(d.level == "info" for d in report.diagnostics if d.code == "od-unknown")


def test_rules():
    def bad(old: str, new: str) -> set[str]:
        assert old in MAP
        return {c for c in codes(_map().replace(old, new, 1)) if c.startswith("od")}

    assert bad("index: 0x100A", "index: 0x0100") == {"od-object-area", "od-unknown"}
    assert bad("index: 0x100A", "index: 0xC000") == {"od-object-area", "od-unknown"}
    assert bad("index: 0x2100", "index: 0x6100") == set()  # device objects can use profile areas
    assert bad("index: 0x100A", "index: 0x1018") == {"od-object-duplicate", "od-unknown"}
    assert bad("name: software_version", "name: identity") == {"od-object-duplicate"}
    assert bad("        data_type: visible_string\n", "") == {"od-object-shape"}
    assert bad("title: Identity object\n", "title: Identity object\n        data_type: unsigned32\n") \
        == {"od-object-shape"}
    assert bad("{subindex: 2, name: product_code", "{subindex: 1, name: product_code") == {"od-object-duplicate"}
    assert bad("default: 3000", "default: 70000") == {"od-default"}
    assert bad("default: 50", "default: fast") == {"od-default"}
    assert bad("name: max_torque, data_type: unsigned16", "name: max_torque, data_type: integer16") \
        == {"od-object-shape"}
    assert bad("access: const\n", "access: const\n        default: 12\n") == {"od-default"}
    assert bad("data_type: unsigned8\n", "data_type: unsigned8\n            default: 1\n") == {"od-default"}
    assert bad("source: layout_crc32", "source: map_version.major") == set()
    assert bad("data_type: unsigned32\n        source: layout_crc32", "data_type: unsigned16\n        source: "
               "layout_crc32") == {"od-default"}
    assert "od-protocol" in codes(_map().replace("protocol: canopen", "protocol: can"))


def test_pdo_signal_index_range():
    pdo = """\
    - name: drive_tpdo
      canopen: pdo_tx1
      length: 2
      signals:
        - {name: s, encoding: number, description: x, byte: 0, byte_length: 2, index: 0xA000}
    """
    found = codes(_map(pdo))
    assert "canopen-od" not in found and "od-unknown" in found


def _eds() -> configparser.ConfigParser:
    m = loads(_map(), "m.yaml").map
    bus = m.buses[0]
    eds = configparser.ConfigParser(interpolation=None)
    eds.optionxform = str
    eds.read_string(device_eds(m, bus, bus.devices[0]))
    return eds


def test_eds():
    eds = _eds()
    assert eds["1018sub1"]["DefaultValue"] == "0x12345678" and eds["1018"]["SubNumber"] == "4"
    assert eds["1018sub0"]["DefaultValue"] == "3"
    assert eds["100A"]["DataType"] == "0x0009" and eds["100A"]["AccessType"] == "const"
    assert eds["2000"]["DataType"] == "0x0005" and eds["2000"]["DefaultValue"] == "4"     # map_version.minor
    assert eds["2100sub1"]["DefaultValue"] == "3000" and eds["2100sub2"]["DataType"] == "0x0006"
    assert eds["2100"]["ParameterName"] == "limits" and eds["2100"]["ObjectType"] == "0x8"
    assert eds["1018"]["ObjectType"] == "0x9"
    assert "0x100A" in eds["OptionalObjects"].values() and "0x2000" in eds["ManufacturerObjects"].values()
    assert set(eds["MandatoryObjects"].values()) >= {"0x1000", "0x1001", "0x1018"}
