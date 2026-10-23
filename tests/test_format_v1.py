"""Format version 1 (#140): still read, converted to version 2, rewritten by mapcan migrate."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from mapcan.cli import app
from mapcan.codegen.c import generate_c
from mapcan.codegen.py import generate_py
from mapcan.export.dbc import export_dbc
from mapcan.export.text import render
from mapcan.layout import layout_crc32
from mapcan.loader import load, loads
from mapcan.lsp import analysis as A
from mapcan.web.session import EditorSession
from mapcan.web.yamlops import migrate_format_text, migrate_text

from .conftest import DATA, ROOT, one_bus, run
from .test_lsp_edits import fixed

V1 = DATA / "v1"
# Version 1 as mapcan 0.23 had it, and the same map in version 2
PAIRS = [(V1 / "reference.yaml", DATA / "reference.yaml")] + [
    (V1 / f"{name}.yaml", ROOT / "examples" / f"{name}.yaml") for name in ("vehicle-can", "j1939", "canopen-node")]


def _outputs(cmap, tmp) -> dict[str, str]:
    files = generate_c(cmap, tmp / "c") + generate_py(cmap, tmp / "py") + export_dbc(cmap, tmp / "dbc")
    out = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in files}
    out["md"] = render(cmap, "md")
    out["crc"] = f"{layout_crc32(cmap):08X}"
    return out


@pytest.mark.parametrize(("old", "new"), PAIRS, ids=lambda p: p.name)
def test_version_1_is_read_as_version_2(old, new, tmp_path):
    """A map of version 1 gives the code, DBC, documents and layout fingerprint of the same map in version 2."""
    v1, v2 = load(old), load(new)
    assert v1.map is not None and v2.map is not None
    assert [d.code for d in v1.report.diagnostics if d.level != "info"] == \
        [d.code for d in v2.report.diagnostics if d.level != "info"]
    assert "format-v1" in v1.report.codes() and "format-v1" not in v2.report.codes()
    assert _outputs(v1.map, tmp_path / "1") == _outputs(v2.map, tmp_path / "2")


@pytest.mark.parametrize(("old", "new"), PAIRS, ids=lambda p: p.name)
def test_migrate_rewrites_version_1(old, new, tmp_path):
    text = old.read_text(encoding="utf-8")
    out = migrate_text(text)
    assert "mapcan: 2\n" in out and "mapcan: 1\n" not in out
    res = loads(out, str(old))
    assert res.map is not None and "format-v1" not in res.report.codes()
    assert _outputs(res.map, tmp_path / "m") == _outputs(load(new).map, tmp_path / "2")
    # Comments stay
    assert all(line in out for line in text.splitlines() if line.lstrip().startswith("#") and "$schema" not in line)
    assert migrate_text(out) == out


V1_SIGNALS = """
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, description: x, byte: 0, bit: 0, encoding: flag, values: {0: OFF, 1: ON}}
            - name: b       # a float
              description: x
              byte: 1
              encoding: float
              unit: V
            - {name: c, description: x, byte: 5, byte_length: 3, encoding: string}
            - {name: d, description: x, byte: 0, bit: 1, bit_length: 7, encoding: raw}
"""


def _v1(text: str) -> str:
    return text.replace("mapcan: 2\n", "mapcan: 1\n", 1)


def test_each_encoding_of_version_1():
    res, report = run(_v1(one_bus(V1_SIGNALS)))
    s = {x.name: x for x in res.map.buses[0].devices[0].frames[0].signals}
    assert (s["a"].encoding, s["a"].bit_length) == ("enum", 1)
    assert (s["b"].encoding, s["b"].representation, s["b"].bit_length) == ("number", "float", 32)
    assert (s["c"].encoding, s["c"].charset) == ("bytes", "ascii")
    assert s["d"].encoding == "number"
    assert [d.level for d in report.diagnostics if d.code == "format-v1"] == ["info"]
    assert not [d for d in report.diagnostics if d.level == "error"]


def test_migrate_adds_what_keeps_the_meaning():
    out = migrate_format_text(_v1(one_bus(V1_SIGNALS)))
    assert "{name: a, description: x, byte: 0, bit: 0, encoding: enum, bit_length: 1, values: {0: OFF, 1: ON}}" in out
    assert "            - name: b       # a float\n" in out
    assert "                encoding: number\n                representation: float\n" in out
    assert "encoding: bytes, charset: ascii}" in out and "encoding: number}" in out


def test_version_2_does_not_read_the_encodings_of_version_1():
    _, report = run(one_bus(V1_SIGNALS))
    assert "schema" in report.codes() and "format-v1" not in report.codes()


def test_migrate_rewrites_the_schema_line():
    text = "# yaml-language-server: $schema=https://ordu1453.github.io/mapcan/schema/v1.json\n" + _v1(one_bus(""))
    assert migrate_format_text(text).startswith(
        "# yaml-language-server: $schema=https://ordu1453.github.io/mapcan/schema/v2.json\n")
    part = "# yaml-language-server: $schema=https://ordu1453.github.io/mapcan/schema/part-v1.json\nmapcan: 1\n"
    assert migrate_format_text(part + "part_of: m.yaml\n").startswith(
        "# yaml-language-server: $schema=https://ordu1453.github.io/mapcan/schema/part-v2.json\nmapcan: 2\n")


def test_cli_migrate_included_files(tmp_path):
    for f in (ROOT / "examples" / "tractor").glob("*.yaml"):
        (tmp_path / f.name).write_text(_v1(f.read_text(encoding="utf-8")), encoding="utf-8")
    main = tmp_path / "tractor.yaml"
    res = load(main)
    assert res.map is not None and "format-v1" in res.report.codes()
    r = CliRunner().invoke(app, ["migrate", "--check", str(main)])
    assert r.exit_code == 1
    assert CliRunner().invoke(app, ["migrate", str(main)]).exit_code == 0
    assert all("mapcan: 2\n" in f.read_text(encoding="utf-8") for f in tmp_path.glob("*.yaml"))
    assert "format-v1" not in load(main).report.codes()


def test_lsp_form_and_quick_fix():
    text = _v1(one_bus(V1_SIGNALS))
    a = A.analyze(text, "m.yaml")
    from mapcan.lsp import edits as E
    path = ["buses", 0, "devices", 0, "frames", 0, "signals", 1]
    node = E.node_fields(a, tuple(path))
    assert node["values"]["encoding"] == "number" and node["values"]["representation"] == "float"
    assert fixed(text, "format-v1") == migrate_format_text(text)


def test_web_editor_shows_version_2(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(_v1(one_bus(V1_SIGNALS)), encoding="utf-8")
    sig = EditorSession(p).state()["data"]["buses"][0]["devices"][0]["frames"][0]["signals"][2]
    assert (sig["encoding"], sig["charset"]) == ("bytes", "ascii")
