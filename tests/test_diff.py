import json

from typer.testing import CliRunner

from canmap.cli import app
from canmap.diff import changelog_lines, diff_maps
from canmap.loader import loads

from .conftest import REFERENCE

BASE = REFERENCE.read_text(encoding="utf-8")


def _map(text: str):
    res = loads(text, "t.yaml")
    assert res.map is not None, [d.format() for d in res.report.diagnostics]
    return res.map


def _diff(new_text: str):
    return diff_maps(_map(BASE), _map(new_text))


def test_no_changes():
    d = _diff(BASE)
    assert d.empty
    assert changelog_lines(d) == []


def test_signal_field_changed():
    d = _diff(BASE.replace("factor: 0.1\n", "factor: 0.01\n", 1))
    [c] = d.changes
    assert (c.kind, c.scope, c.frame, c.signal, c.field, c.old, c.new) == \
        ("changed", "signal", "imd_data", "bus_voltage", "factor", 0.1, 0.01)
    assert changelog_lines(d) == ["0x2A1 imd_data: bus_voltage.factor 0.1 → 0.01"]


def test_enum_value_added_and_renamed():
    new = BASE.replace("                  3: ALARM\n", "                  3: ALARM\n                  4: SERVICE\n", 1)
    new = new.replace("                  1: OK\n", "                  1: GOOD\n", 1)
    lines = changelog_lines(_diff(new))
    assert "0x1A2 cmu_state: cmu_status: добавлено значение 4 = SERVICE" in lines
    assert "0x1A2 cmu_state: cmu_status = 1: OK → GOOD" in lines


def test_signal_added_removed():
    new = BASE.replace("              - name: frame_request\n"
                       "                description: Номер повторно запрашиваемого кадра\n"
                       "                byte: 1\n", "")
    d = _diff(new)
    assert any(c.kind == "removed" and c.signal == "frame_request" for c in d.changes)
    assert "0x222 cmu_request: удалён сигнал frame_request (биты 8–15)" in changelog_lines(d)


def test_frame_added_and_id_changed():
    new = BASE.replace("node_id: 0x23\n", "node_id: 0x26\n", 1)
    d = _diff(new)
    lines = changelog_lines(d)
    assert "pcu: node_id 0x23 → 0x26" in lines
    assert "0x1A6 pcu_state: can_id 0x1A3 → 0x1A6" in lines


def test_flag_changes():
    new = BASE.replace("{bit: 4, name: err_igbt_driver,", "{bit: 5, name: err_igbt_driver,", 1)
    lines = changelog_lines(_diff(new))
    assert "0x1A3 pcu_state: error_code.err_igbt_driver.bit 4 → 5" in lines


def test_cli_diff(tmp_path):
    new = tmp_path / "new.yaml"
    new.write_text(BASE.replace("factor: 0.1\n", "factor: 0.01\n", 1), encoding="utf-8")
    r = CliRunner().invoke(app, ["diff", str(REFERENCE), str(new), "--format", "md"])
    assert r.exit_code == 0, r.output
    assert "- 0x2A1 imd_data: bus_voltage.factor 0.1 → 0.01" in r.output
    r = CliRunner().invoke(app, ["diff", str(REFERENCE), str(new), "--format", "json"])
    assert json.loads(r.output)["changes"][0]["field"] == "factor"
