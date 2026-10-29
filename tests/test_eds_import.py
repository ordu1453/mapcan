"""EDS and DCF import (CiA 306): PDOs, their objects and the heartbeat of a CANopen device → a map."""

from __future__ import annotations

from typer.testing import CliRunner

from mapcan.cli import app
from mapcan.export.eds import export_eds
from mapcan.importers.eds import import_eds
from mapcan.loader import load, loads

from .conftest import DATA, ROOT, run

NODE = ROOT / "examples" / "canopen-node.yaml"
VENDOR = DATA / "vendor-io.eds"


def _map(text: str):
    res = loads(text, "imported.yaml")
    assert res.map is not None
    return res.map


def _layout(dev) -> list:
    """What an EDS carries of a device: PDOs with their IDs, timing and mapped objects, and the heartbeat."""
    return [(f.type, f.can_id, f.length, f.cycle_ms if f.type != "pdo_rx1" else None, f.inhibit_ms,
             [(s.start_bit, s.bit_length, s.index, s.subindex or 0, s.representation, s.encoding) for s in f.signals])
            for f in sorted(dev.frames, key=lambda f: f.type)]


def test_roundtrip_of_the_example(tmp_path):
    """export eds → import eds: the same frames and signals."""
    original = load(NODE).map
    (path,) = [p for p in export_eds(original, tmp_path) if p.stem == "drive"]
    text, warnings = import_eds(path, node_id=5)
    assert warnings == []
    _res, report = run(text)
    assert report.errors == 0 and report.warnings == 0, [d.format() for d in report.diagnostics]
    dev = _map(text).buses[0].devices[0]
    drive = next(d for d in original.buses[0].devices if d.name == "drive")
    assert _layout(dev) == _layout(drive)
    assert dev.title == "Traction drive" and dev.node_id == 5
    assert [s.title for s in dev.frames[0].signals] == ["Statusword", "Velocity actual value"]


def test_vendor_file():
    text, warnings = import_eds(VENDOR, node_id=0x20)
    _res, report = run(text)
    assert report.errors == 0 and report.warnings == 0, [d.format() for d in report.diagnostics]
    m = _map(text)
    assert m.document.organization == "ACME Automation"
    assert m.buses[0].bitrate is None                     # the device supports 125 and 250 kbit/s
    dev = m.buses[0].devices[0]
    assert (dev.name, dev.node_id) == ("io_module_8di_8do", 0x20)
    frames = {f.name: f for f in dev.frames}
    assert list(frames) == ["tpdo1", "tpdo2", "rpdo1", "rpdo2", "heartbeat"]
    tpdo1 = frames["tpdo1"]
    # $NODEID+0x180 is the default ID; the dummy byte is a gap; INTEGER16 is signed, with its limits
    assert (tpdo1.id, tpdo1.can_id, tpdo1.length, tpdo1.trigger, tpdo1.inhibit_ms) == (None, 0x1A0, 4, "event", 10)
    a, b = tpdo1.signals
    assert (a.index, a.subindex, a.start_bit, a.bit_length) == (0x6000, 1, 0, 8)
    assert (b.start_bit, b.bit_length, b.representation, b.min, b.max) == (16, 16, "twos_complement", -1000, 1000)
    assert (frames["rpdo1"].timeout_ms, frames["rpdo1"].cycle_ms) == (500, None)
    assert frames["rpdo2"].id == 0x321
    (sp,) = frames["rpdo2"].signals
    assert (sp.representation, sp.min, sp.max) == ("float", -10.5, 10.5)
    assert frames["heartbeat"].cycle_ms == 1000
    joined = "\n".join(warnings)
    for part in ("1 dummy entries", "tpdo2: the PDO is disabled", "data type 0x0040", "synchronous transmission",
                 "tpdo5", "0x2100"):
        assert part in joined, part
    assert "node ID" not in joined


def test_eds_without_node_id():
    _text, warnings = import_eds(VENDOR)
    assert any("node ID: 1 is used" in w for w in warnings)


def test_dcf_gives_node_id_bit_rate_and_configured_values(tmp_path):
    dcf = tmp_path / "io.dcf"
    text = VENDOR.read_text(encoding="utf-8").replace(
        "[1800sub3]", "[1800sub5]\nDataType=0x0006\nDefaultValue=0\nParameterValue=50\n\n[1800sub3]")
    dcf.write_text(text + "\n[DeviceComissioning]\nNodeID=0x10\nBaudrate=250\n", encoding="utf-8")
    out, warnings = import_eds(dcf)
    assert not any("node ID" in w for w in warnings)
    m = _map(out)
    dev = m.buses[0].devices[0]
    assert (dev.node_id, m.buses[0].bitrate) == (0x10, 250000)
    tpdo1 = dev.frames[0]
    assert (tpdo1.can_id, tpdo1.cycle_ms, tpdo1.trigger) == (0x190, 50, None)


def test_import_eds_cli(tmp_path):
    out = tmp_path / "io.yaml"
    invoke = CliRunner().invoke
    r = invoke(app, ["import", "eds", str(VENDOR), "-o", str(out), "--node-id", "0x20", "--title", "IO"])
    assert r.exit_code == 0 and "errors: 0" in r.stdout, r.output
    assert "title: IO\n" in out.read_text(encoding="utf-8") and "node_id: 0x20" in out.read_text(encoding="utf-8")
    assert invoke(app, ["import", "eds", str(VENDOR), "-o", str(out)]).exit_code == 1     # does not overwrite
    assert invoke(app, ["import", "eds", str(VENDOR), "-o", str(out), "--force", "--node-id", "200"]).exit_code == 2
    assert invoke(app, ["import", "eds", str(VENDOR), "-o", str(out), "--force", "--node-id", "32"]).exit_code == 0
