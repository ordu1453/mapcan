"""Command line: exit codes, output and files of every command."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from mapcan import __version__
from mapcan.cli import app
from mapcan.schema import json_schema
from mapcan.validate import RULES

from .conftest import DATA, REFERENCE, ROOT, one_bus

MINIMAL = ROOT / "examples" / "minimal.yaml"
FRAME = """
    - name: f
      type: pdo_tx1
      length: 1
      cycle_ms: 100
      signals:
        - {name: a, encoding: raw, description: x, byte: 0, byte_length: 1}
"""


def invoke(*args):
    return CliRunner().invoke(app, [str(a) for a in args], catch_exceptions=False)


@pytest.fixture
def warning_map(tmp_path):
    """A map without errors but with a warning (non-standard bus bitrate)."""
    p = tmp_path / "warn.yaml"
    p.write_text(one_bus(FRAME).replace("    protocol: canopen\n", "    protocol: canopen\n    bitrate: 300000\n"),
                 encoding="utf-8")
    return p


def test_version():
    r = invoke("--version")
    assert r.exit_code == 0 and r.stdout.strip() == f"mapcan {__version__}"


def test_validate_clean_map():
    r = invoke("validate", MINIMAL)
    assert r.exit_code == 0 and r.stdout.strip().endswith("errors: 0, warnings: 0, notes: 0")


def test_validate_errors_exit_1():
    r = invoke("validate", DATA / "invalid_map.yaml")
    assert r.exit_code == 1 and "FAIL:" in r.stdout and "error[" in r.stdout


def test_validate_strict_and_disable(warning_map):
    assert invoke("validate", warning_map).exit_code == 0
    r = invoke("validate", warning_map, "--strict")
    assert r.exit_code == 1 and "bitrate-nonstandard" in r.stdout
    assert invoke("validate", warning_map, "--strict", "--disable", "bitrate-nonstandard").exit_code == 0


def test_validate_info_and_json():
    assert "info[" not in invoke("validate", REFERENCE).stdout
    assert "info[" in invoke("validate", REFERENCE, "--info").stdout
    r = invoke("validate", DATA / "invalid_map.yaml", "--format", "json")
    assert r.exit_code == 1
    diags = json.loads(r.stdout)
    assert any(d["level"] == "error" and d["code"] == "bit-overlap" for d in diags)


def test_validate_missing_file(tmp_path):
    assert invoke("validate", tmp_path / "nope.yaml").exit_code == 2


def test_rules_lists_every_rule():
    out = invoke("rules").stdout.splitlines()
    assert [line.split()[0] for line in out] == list(RULES)


def test_schema(tmp_path):
    assert json.loads(invoke("schema").stdout) == json_schema()
    out = tmp_path / "s" / "schema.json"
    r = invoke("schema", "-o", out)
    assert r.exit_code == 0 and json.loads(out.read_text(encoding="utf-8")) == json_schema()


def test_diff(tmp_path):
    new = tmp_path / "new.yaml"
    new.write_text(MINIMAL.read_text(encoding="utf-8").replace("factor: 0.01", "factor: 0.02", 1), encoding="utf-8")
    r = invoke("diff", MINIMAL, new)
    assert r.exit_code == 0 and "0.01 → 0.02" in r.stdout
    assert json.loads(invoke("diff", MINIMAL, new, "--format", "json").stdout)
    broken = tmp_path / "broken.yaml"
    broken.write_text("mapcan: [\n", encoding="utf-8")
    assert invoke("diff", MINIMAL, broken).exit_code == 1


def test_template(tmp_path):
    r = invoke("template", "--list")
    assert r.exit_code == 0 and "mapcan" in r.stdout
    assert invoke("template", "md", "-o", tmp_path / "doc.md.j2").exit_code == 0
    assert (tmp_path / "doc.md.j2").is_file()
    assert invoke("template", "pdf", "-o", tmp_path / "pdf" / "my.typ").exit_code == 0
    assert (tmp_path / "pdf" / "my.typ").is_file() and (tmp_path / "pdf" / "lib.typ").is_file()
    assert invoke("template", "pdf", "--name", "nope", "-o", tmp_path / "x.typ").exit_code == 2
    assert invoke("template", "md").exit_code == 2      # -o is required


@pytest.mark.parametrize(("cmd", "name"), [
    (["export", "md"], "out.md"), (["export", "html"], "out.html"), (["export", "xlsx"], "out.xlsx"),
])
def test_export_documents(tmp_path, cmd, name):
    out = tmp_path / name
    r = invoke(*cmd, MINIMAL, "-o", out)
    assert r.exit_code == 0 and out.is_file() and out.stat().st_size > 0 and str(out) in r.stdout


def test_export_dbc_and_gen(tmp_path):
    assert invoke("export", "dbc", MINIMAL, "-o", tmp_path / "x.dbc").exit_code == 0
    assert (tmp_path / "x.dbc").is_file()
    assert invoke("gen", "c", MINIMAL, "-o", tmp_path / "c", "--prefix", "ne_").exit_code == 0
    assert sorted(p.suffix for p in (tmp_path / "c").iterdir()) == [".c", ".h"]
    assert "ne_" in next((tmp_path / "c").glob("*.h")).read_text(encoding="utf-8")
    assert invoke("gen", "py", MINIMAL, "-o", tmp_path / "py").exit_code == 0
    assert list((tmp_path / "py").glob("*.py"))


def test_generation_stops_on_errors(tmp_path):
    bad = DATA / "invalid_map.yaml"
    r = invoke("export", "md", bad, "-o", tmp_path / "x.md")
    assert r.exit_code == 1 and not (tmp_path / "x.md").exists()
    assert "--force" in r.stderr


def test_force_generates_despite_errors(tmp_path):
    text = one_bus(FRAME).replace("byte: 0, byte_length: 1", "byte: 0, byte_length: 2")   # does not fit in the DLC
    p = tmp_path / "err.yaml"
    p.write_text(text, encoding="utf-8")
    assert invoke("export", "md", p, "-o", tmp_path / "x.md").exit_code == 1
    assert invoke("export", "md", p, "-o", tmp_path / "x.md", "--force").exit_code == 0
    assert (tmp_path / "x.md").is_file()


def test_build(tmp_path):
    r = invoke("build", MINIMAL, "-o", tmp_path, "--formats", "md,html,xlsx,dbc,c,py")
    assert r.exit_code == 0
    assert {p.name for p in tmp_path.iterdir()} == {"minimal.md", "minimal.html", "minimal.xlsx", "dbc", "c", "py"}


def test_build_rejects_unknown_format(tmp_path):
    r = invoke("build", MINIMAL, "-o", tmp_path, "--formats", "md,doc")
    assert r.exit_code == 2 and "doc" in r.stderr
