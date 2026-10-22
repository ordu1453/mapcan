"""`mapcan fmt`: one key order, the rest of the text kept."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from mapcan.cli import app
from mapcan.fmt import format_text
from mapcan.web.yamlops import make_yaml, plain

from .conftest import ROOT

runner = CliRunner()
MAPS = sorted(p for p in (ROOT / "examples").rglob("*.yaml") if "mapcan:" in p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", MAPS + [ROOT / "tests" / "data" / "reference.yaml"], ids=lambda p: p.name)
def test_same_data_and_idempotent(path):
    text = path.read_text(encoding="utf-8")
    new = format_text(text)
    assert plain(make_yaml(new).load(new)) == plain(make_yaml(text).load(text))
    assert format_text(new) == new
    assert sorted(ln.strip() for ln in new.splitlines() if ln.strip().startswith("#")) == \
        sorted(ln.strip() for ln in text.splitlines() if ln.strip().startswith("#"))


def test_examples_are_formatted():
    for path in MAPS:
        text = path.read_text(encoding="utf-8")
        assert format_text(text) == text, f"{path.name}: run mapcan fmt"


def test_keys_move_with_their_comments():
    text = """mapcan: 1
document:
  language: en   # the language
  # the title
  title: T
buses:
  - name: b
    protocol: can
    devices:
      - name: d
        frames:
          - id: 0x100     # explicit
            name: f
            length: 1
            signals:
              - {encoding: raw, name: s, byte: 0x0, byte_length: 1}
"""
    assert format_text(text) == """mapcan: 1
document:
  # the title
  title: T
  language: en   # the language
buses:
  - name: b
    protocol: can
    devices:
      - name: d
        frames:
          - name: f
            id: 0x100     # explicit
            length: 1
            signals:
              - {name: s, encoding: raw, byte: 0x0, byte_length: 1}
"""


def test_editors_write_new_keys_in_their_place():
    from mapcan.web.yamlops import dump, op_set

    text = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8")
    y = make_yaml(text)
    doc = y.load(text)
    frame = ["buses", 0, "devices", 0, "frames", 0]
    op_set(doc, [*frame, "comment"], "a note")
    op_set(doc, [*frame, "signals", 0, "title"], "Mode")
    out = dump(y, doc)
    assert "            description: Pump state\n            comment: a note\n" in out
    assert "              - name: mode            # enum, byte 0\n                title: Mode\n" in out
    assert format_text(out) == out


def test_cli_check_and_write(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_bytes(b"mapcan: 1\r\ndocument: {language: en, title: T}\r\nbuses: []\r\n")
    r = runner.invoke(app, ["fmt", "--check", str(p)])
    assert r.exit_code == 1 and "mapcan fmt" in r.output
    assert runner.invoke(app, ["fmt", str(p)]).exit_code == 0
    assert p.read_bytes() == b"mapcan: 1\r\ndocument: {title: T, language: en}\r\nbuses: []\r\n"
    assert runner.invoke(app, ["fmt", "--check", str(p)]).exit_code == 0


def test_cli_check_notes_positions_in_another_notation():
    """#117: a position written otherwise than the editors write it is a note, not a failure, and is not
    rewritten."""
    r = runner.invoke(app, ["fmt", "--check", str(ROOT / "examples" / "minimal.yaml")])
    assert r.exit_code == 0
    assert "minimal.yaml:76: note: signal 'counter': the editors write its position as byte: 7, bit: 0, " \
           "bit_length: 4" in r.output
