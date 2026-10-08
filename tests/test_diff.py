import json

from typer.testing import CliRunner

from mapcan.cli import app
from mapcan.diff import bump_version, changed_paths, changelog_lines, diff_maps, release_draft, release_message
from mapcan.loader import loads

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
                       "                encoding: raw\n"
                       "                description: Номер повторно запрашиваемого кадра\n"
                       "                byte: 1\n"
                       "                byte_length: 1\n", "")
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


def _paths(new_text: str) -> dict:
    new = _map(new_text)
    return changed_paths(diff_maps(_map(BASE), new), new)


def _path_of(cmap, frame: str, signal: str | None = None) -> tuple:
    f = next(f for b in cmap.buses for f in b.all_frames() if f.name == frame)
    return f._path if signal is None else next(s for s in f.signals if s.name == signal)._path


def test_changed_paths():
    assert _paths(BASE) == {}
    # A changed field marks the signal, a new enum value also the signal (not its frame)
    new = BASE.replace("factor: 0.1\n", "factor: 0.01\n", 1)
    new = new.replace("                  3: ALARM\n", "                  3: ALARM\n                  4: SERVICE\n", 1)
    m = _map(new)
    assert _paths(new) == {_path_of(m, "imd_data", "bus_voltage"): "modified",
                           _path_of(m, "cmu_state", "cmu_status"): "modified"}
    # A removed signal marks its frame
    new = BASE.replace("              - name: frame_request\n"
                       "                encoding: raw\n"
                       "                description: Номер повторно запрашиваемого кадра\n"
                       "                byte: 1\n"
                       "                byte_length: 1\n", "")
    m = _map(new)
    assert _paths(new) == {_path_of(m, "cmu_request"): "modified"}
    # A changed node_id marks the device and the frames whose ID is computed from it
    new = BASE.replace("node_id: 0x23\n", "node_id: 0x26\n", 1)
    m = _map(new)
    pcu = _path_of(m, "pcu_state")
    paths = _paths(new)
    assert paths[pcu[:4]] == "modified" and paths[pcu] == "modified"


def test_changed_paths_added():
    new = BASE.replace("{bit: 4, name: err_igbt_driver,", "{bit: 4, name: err_igbt_driver2,", 1)
    m = _map(new)
    sig = next(s for b in m.buses for f in b.all_frames() for s in f.signals
               if any(x.name == "err_igbt_driver2" for x in s.flags or []))
    flag = next(x for x in sig.flags if x.name == "err_igbt_driver2")
    # A renamed flag: the new one added, the old one removed, the signal changed
    assert _paths(new) == {flag._path: "added", sig._path: "modified"}


def test_bump_and_message():
    assert bump_version("1.2.3") == "1.2.4"
    assert bump_version("1.2.3-rc1") == "1.2.4"
    assert bump_version("") == "0.1.0"
    assert bump_version("draft") == "draft"
    assert release_message("1.0.1", ["a"]) == "1.0.1: a"
    # The heading is in the interface language ("Версия 1.0.1" or "Version 1.0.1")
    head, *rest = release_message("1.0.1", ["a", "b"]).split("\n")
    assert head.endswith(" 1.0.1") and rest == ["", "- a", "- b"]
    assert release_message("1.0.1", []) == head


def test_release_draft():
    base = _map(BASE)
    new = _map(BASE.replace("factor: 0.1\n", "factor: 0.01\n", 1))
    # Version 1.0.0 is first in the history but has no tag: it is released with its recorded changes
    d = release_draft(new, base, lambda v: False)
    assert d["version"] == "1.0.0" and d["recorded"] and d["changes"][0].startswith("Карта описана в YAML")
    # There is a tag v1.0.0: the next version, with the changes since the previous release
    d = release_draft(new, base, lambda v: v == "1.0.0")
    assert d == {"version": "1.0.1", "recorded": False,
                 "changes": ["0x2A1 imd_data: bus_voltage.factor 0.1 → 0.01"]}
    # First release without history: the current version if it has no tag, otherwise the next one without a tag
    start = BASE.index("  history:\n")
    plain = _map(BASE[:start] + BASE[BASE.index("\n\n", start) + 1:])
    assert release_draft(plain, None, lambda v: False)["version"] == "1.0.0"
    assert release_draft(plain, None, lambda v: v in ("1.0.0", "1.0.1"))["version"] == "1.0.2"
