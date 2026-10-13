"""Former names of fields (deprecated-key): read with a warning, written under the current name, migrated."""

from __future__ import annotations

from typer.testing import CliRunner

from mapcan.cli import app
from mapcan.lsp import analysis as A
from mapcan.lsp import edits as E
from mapcan.upgrade import node_kind, upgrade_tree
from mapcan.web.session import EditorSession
from mapcan.web.yamlops import migrate_text

from .conftest import ROOT, run
from .test_lsp_edits import FRAME, apply, fixed

MINIMAL = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8")
# The same map as written before the rename: the frame's length under its former name
LEGACY = MINIMAL.replace("            length: 8\n", "            dlc: 8        # bytes\n", 1)


def test_minimal_has_the_length():
    assert LEGACY != MINIMAL


def test_former_name_is_read_with_a_warning():
    res, report = run(LEGACY)
    assert res.map.buses[0].devices[0].frames[0].length == 8
    d = next(d for d in report.diagnostics if d.code == "deprecated-key")
    assert d.level == "warning" and "'dlc'" in d.message and "'length'" in d.message
    assert LEGACY.splitlines()[d.line - 1].strip().startswith("dlc:")


def test_messages_about_the_field_point_at_the_former_key():
    res, report = run(LEGACY.replace("dlc: 8 ", "dlc: 9 "))
    d = next(d for d in report.diagnostics if d.code == "dlc-range")
    assert LEGACY.splitlines()[d.line - 1].strip().startswith("dlc:")


def test_both_names_is_an_error():
    text = LEGACY.replace("dlc: 8        # bytes\n", "dlc: 8\n            length: 4\n")
    res, report = run(text)
    d = next(d for d in report.diagnostics if d.code == "deprecated-key")
    assert d.level == "error"
    assert res.map.buses[0].devices[0].frames[0].length == 4


def test_node_kinds():
    assert node_kind(("buses", 0, "devices", 1, "frames", 2)) == "frame"
    assert node_kind(("buses", 0, "frames", 2)) == "frame"
    assert node_kind(("buses", 0, "devices", 1, "frames", 2, "signals", 0)) == "signal"
    assert node_kind(("buses", 0, "devices", 1, "frames", 2, "signals", 0, "flags", 3)) == "flag"
    assert node_kind(("buses", 0, "devices", 1, "frames", 2, "sdo", 0, "value")) == "sdo_value"
    assert node_kind(("buses", 0, "devices", 1)) == "device"
    assert node_kind(("value_tables", "x")) is None


def test_migrate_keeps_the_rest_of_the_text():
    out = migrate_text(LEGACY)
    # Only the key changes: the comment keeps its distance from the value
    assert "length: 8        # bytes\n" in out
    assert out.replace("length: 8        # bytes\n", "length: 8\n") == MINIMAL
    assert migrate_text(MINIMAL) == MINIMAL


def test_cli_migrate(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_bytes(LEGACY.replace("\n", "\r\n").encode())
    r = CliRunner().invoke(app, ["migrate", "--check", str(p)])
    assert r.exit_code == 1 and "migrate" in r.output
    r = CliRunner().invoke(app, ["migrate", str(p)])
    assert r.exit_code == 0
    text = p.read_bytes().decode()
    assert "length: 8" in text and "dlc:" not in text and "\r\n" in text and "\n" not in text.replace("\r\n", "")
    assert CliRunner().invoke(app, ["migrate", "--check", str(p)]).exit_code == 0


def test_cli_migrate_included_files(tmp_path):
    (tmp_path / "part.yaml").write_text("buses:\n  - name: b\n    frames:\n      - {name: f, id: 0x10, dlc: 1}\n",
                                        encoding="utf-8")
    main = tmp_path / "m.yaml"
    main.write_text("mapcan: 1\ninclude: [part.yaml]\n", encoding="utf-8")
    assert CliRunner().invoke(app, ["migrate", str(main)]).exit_code == 0
    assert "length: 1" in (tmp_path / "part.yaml").read_text(encoding="utf-8")


def test_upgrade_tree_does_not_change_its_input():
    data = {"buses": [{"name": "b", "frames": [{"name": "f", "dlc": 2, "id": 1}]}]}
    out = upgrade_tree(data)
    assert list(out["buses"][0]["frames"][0]) == ["name", "length", "id"]
    assert data["buses"][0]["frames"][0]["dlc"] == 2


def test_lsp_form_reads_and_writes_the_current_name():
    a = A.analyze(LEGACY, "m.yaml")
    assert E.node_fields(a, FRAME)["values"]["length"] == 8
    out = apply(LEGACY, E.set_field(a, FRAME + ("length",), 6))
    assert "            length: 6     # bytes\n" in out and "dlc" not in out
    out = apply(LEGACY, E.set_field(a, FRAME + ("length",), None))
    assert "dlc" not in out and "length" not in out.split("pump_state")[1].split("signals")[0]


def test_lsp_quick_fix_migrates_the_map():
    assert fixed(LEGACY, "deprecated-key") == migrate_text(LEGACY)


def test_web_editor_data_and_writes(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(LEGACY, encoding="utf-8")
    s = EditorSession(p)
    frame = s.state()["data"]["buses"][0]["devices"][0]["frames"][0]
    assert frame["length"] == 8 and "dlc" not in frame
    s.apply([{"op": "set", "path": list(FRAME) + ["length"], "value": 4}])
    assert "            length: 4     # bytes\n" in s.text and "dlc" not in s.text


def test_signed_and_signed_code_become_representation():
    sig = "              - {name: a, encoding: raw, description: x, byte: 0, byte_length: 1, %s}\n"
    base = MINIMAL.split("            signals:\n")[0] + "            signals:\n"
    cases = [("signed: true", "twos_complement"), ("signed: true, signed_code: sign_magnitude", "sign_magnitude"),
             ("signed: false", "unsigned"), ("signed_code: ones_complement", "unsigned")]
    for extra, expected in cases:
        res, report = run(base + sig % extra)
        assert res.map.buses[0].devices[0].frames[0].signals[0].representation == expected, extra
        assert "deprecated-key" in report.codes()
        out = migrate_text(base + sig % extra)
        assert "signed" not in out.split("signals:")[-1]
        assert (f"representation: {expected}" in out) == (expected != "unsigned")


def test_sdo_value_signed_becomes_representation():
    from mapcan.upgrade import upgrade_tree as up
    data = {"buses": [{"frames": [{"sdo": [{"value": {"name": "v", "signed": True}}]}]}]}
    assert up(data)["buses"][0]["frames"][0]["sdo"][0]["value"] == {"name": "v", "representation": "twos_complement"}


def test_frame_type_becomes_canopen():
    frames = [{"name": "a", "type": "pdo_tx1"}, {"name": "b", "type": "raw", "id": 1}]
    data = {"buses": [{"devices": [{"frames": frames}]}]}
    frames = upgrade_tree(data)["buses"][0]["devices"][0]["frames"]
    assert frames == [{"name": "a", "canopen": "pdo_tx1"}, {"name": "b", "id": 1}]
    legacy = MINIMAL.replace("canopen: pdo_tx1", "type: pdo_tx1")
    res, report = run(legacy)
    assert res.map.buses[0].devices[0].frames[0].canopen == "pdo_tx1" and "deprecated-key" in report.codes()
    assert migrate_text(legacy) == MINIMAL


def test_migrate_keeps_line_breaks_of_flow_mappings():
    text = MINIMAL.replace(
        "            signals:\n",
        "            signals:\n"
        "              - {name: wrapped, encoding: raw, description: x, byte: 7, byte_length: 1,\n"
        "                 signed: true, invalid: 0x7F}\n", 1)
    out = migrate_text(text)
    assert "                 representation: twos_complement, invalid_raw: 0x7F}\n" in out
    assert out.count("\n") == text.count("\n")


def test_invalid_raw_by_meaning_and_ranges():
    sig = ("              - {name: t, encoding: scaled, description: x, byte: 6, byte_length: 2, factor: 0.1, "
           "unit: V, min: 0, max: 100, invalid_raw: %s}\n")
    base = MINIMAL.split("            signals:\n")[0] + "            signals:\n"
    res, report = run(base + sig % "{not_available: [0xFF00..0xFFFF], error: [0xFE00..0xFEFF]}")
    s = res.map.buses[0].devices[0].frames[0].signals[0]
    assert s.invalid_ranges == {"not_available": [(0xFF00, 0xFFFF)], "error": [(0xFE00, 0xFEFF)]}
    assert "invalid-in-range" not in report.codes()
    assert "invalid-in-range" in run(base + sig % "[0..10]")[1].codes()
    assert "invalid-overflow" in run(base + sig % "[0xFF00..0x1FFFF]")[1].codes()
    assert "schema" in run(base + sig % "[0xFF..0x10]")[1].codes()


def test_bus_interface_becomes_connector():
    assert upgrade_tree({"buses": [{"name": "b", "interface": "X3"}]}) == {"buses": [{"name": "b", "connector": "X3"}]}
    legacy = MINIMAL.replace("    protocol:", "    interface: X3\n    protocol:", 1)
    res, report = run(legacy)
    assert res.map.buses[0].connector == "X3" and "deprecated-key" in report.codes()
    assert "    connector: X3\n" in migrate_text(legacy)
