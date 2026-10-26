"""Command line: exit codes, output and files of every command."""

from __future__ import annotations

import json
import sys

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
      canopen: pdo_tx1
      length: 1
      cycle_ms: 100
      signals:
        - {name: a, encoding: number, description: x, byte: 0, byte_length: 1}
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


@pytest.fixture
def fake_server(monkeypatch):
    """`mapcan serve` without a real server and browser: what it would serve, where, and the opened address."""
    import webbrowser

    from mapcan import launcher
    from mapcan.web import app as web_app

    seen = {"opened": []}

    class Server:
        def __init__(self, app, host, port):
            seen.update(host=host, port=port)

        def start(self):
            if seen.get("fail"):
                raise RuntimeError("port is busy")

        def wait(self):
            seen["waited"] = True

    monkeypatch.setattr(launcher, "ServerThread", Server)
    monkeypatch.setattr(launcher, "pick_port", lambda host, preferred: 9999)
    monkeypatch.setattr(web_app, "create_app", lambda session, **kw: seen.update(session=session, **kw))
    monkeypatch.setattr(webbrowser, "open", seen["opened"].append)
    return seen


def test_serve_local(fake_server, tmp_path):
    r = invoke("serve", MINIMAL, "--readonly")
    assert r.exit_code == 0, r.output
    # A local address: a free port, no token, only local Host headers, update check on
    assert (fake_server["host"], fake_server["port"]) == ("127.0.0.1", 9999)
    assert fake_server["auth_token"] is None and fake_server["check_updates"]
    assert fake_server["allowed_hosts"] == ("127.0.0.1", "localhost", "::1")
    assert fake_server["readonly"] and fake_server["session"].path == MINIMAL
    assert fake_server["opened"] == ["http://127.0.0.1:9999/"] and fake_server["waited"]
    assert "http://127.0.0.1:9999/" in r.output

    # A folder is the working folder of the start screen, without a session
    r = invoke("serve", tmp_path, "--no-browser", "--port", 8000)
    assert r.exit_code == 0 and fake_server["session"] is None and fake_server["cwd"] == tmp_path.resolve()
    assert fake_server["port"] == 8000 and fake_server["opened"] == ["http://127.0.0.1:9999/"]


def test_serve_network_needs_a_token(fake_server):
    r = invoke("serve", "--host", "0.0.0.0", "--no-browser")
    assert r.exit_code == 0, r.output
    token = fake_server["auth_token"]
    # A random token, on the default port, in the printed address; no update check, any Host header
    assert token and len(token) >= 24 and fake_server["port"] == 8765
    assert fake_server["allowed_hosts"] is None and not fake_server["check_updates"]
    assert f"http://127.0.0.1:8765/?token={token}" in r.output

    r = invoke("serve", "--host", "10.0.0.5", "--token", "a b", "--no-browser")
    assert fake_server["auth_token"] == "a b" and "?token=a%20b" in r.output


def test_serve_network_without_auth_warns(fake_server):
    r = CliRunner().invoke(app, ["serve", "--host", "0.0.0.0", "--no-auth", "--no-browser"])
    assert r.exit_code == 0 and fake_server["auth_token"] is None
    assert "without authentication" in r.output or "без аутентификации" in r.output
    assert "?token=" not in r.output


def test_serve_start_error(fake_server):
    fake_server["fail"] = True
    r = CliRunner().invoke(app, ["serve", "--no-browser"])
    assert r.exit_code == 1 and "port is busy" in r.output and "waited" not in fake_server


def test_app_and_lsp_commands(monkeypatch):
    from mapcan import launcher
    from mapcan.lsp import server

    calls = []
    monkeypatch.setattr(launcher, "run", lambda path, **kw: calls.append((path, kw)) or 3)
    monkeypatch.setattr(server, "main", lambda: calls.append("lsp"))
    assert invoke("app", MINIMAL, "--browser", "--readonly").exit_code == 3
    assert invoke("app").exit_code == 3
    assert invoke("lsp").exit_code == 0
    assert calls == [(MINIMAL, {"window": False, "readonly": True}), (None, {"window": True, "readonly": False}),
                     "lsp"]


def test_fmt_reports_a_broken_file(tmp_path):
    broken = tmp_path / "broken.yaml"
    broken.write_text("mapcan: [\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["fmt", str(broken)])
    assert r.exit_code == 1 and "broken.yaml" in r.output
    assert broken.read_text(encoding="utf-8") == "mapcan: [\n"


def test_export_eds(tmp_path):
    r = invoke("export", "eds", MINIMAL, "-o", tmp_path)
    assert r.exit_code == 0, r.output
    assert list(tmp_path.glob("*.eds"))


def test_import_dbc_refuses(tmp_path, monkeypatch):
    # Without -o the map is written to the current folder
    monkeypatch.chdir(tmp_path)
    dbc = tmp_path / "car.dbc"
    dbc.write_text('VERSION ""\n', encoding="utf-8")
    (tmp_path / "car.yaml").write_text("keep\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["import", "dbc", str(dbc)])
    assert r.exit_code == 1 and "--force" in r.output
    assert (tmp_path / "car.yaml").read_text(encoding="utf-8") == "keep\n"
    r = CliRunner().invoke(app, ["import", "dbc", str(dbc), "-o", str(tmp_path / "new.yaml"), "--lang", "english"])
    assert r.exit_code == 2 and "english" in r.output and not (tmp_path / "new.yaml").exists()


def test_main(monkeypatch, capsys):
    from mapcan import cli

    monkeypatch.setattr(sys, "argv", ["mapcan", "--version"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 0 and __version__ in capsys.readouterr().out
