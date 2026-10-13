"""Optional parts of the package (extras): a command that needs a missing one names it."""

from __future__ import annotations

from typer.testing import CliRunner

from mapcan import extras
from mapcan.cli import app

from .conftest import ROOT

runner = CliRunner()
MAP = str(ROOT / "examples" / "minimal.yaml")


def missing(monkeypatch, *names: str) -> None:
    real = extras.find_spec
    monkeypatch.setattr(extras, "find_spec", lambda m: None if m in names else real(m))


def test_missing_extra_is_named(monkeypatch, tmp_path):
    missing(monkeypatch, "typst")
    r = runner.invoke(app, ["export", "pdf", MAP, "-o", str(tmp_path / "x.pdf")])
    assert r.exit_code == 1 and 'mapcan[pdf]' in r.output
    r = runner.invoke(app, ["build", MAP, "-o", str(tmp_path), "--formats", "pdf"])
    assert r.exit_code == 1 and 'mapcan[pdf]' in r.output


def test_core_outputs_need_no_extra(monkeypatch, tmp_path):
    missing(monkeypatch, "typst", "openpyxl", "PIL", "fastapi", "uvicorn")
    r = runner.invoke(app, ["build", MAP, "-o", str(tmp_path), "--formats", "md,html,dbc,eds,c,py"])
    assert r.exit_code == 0, r.output
