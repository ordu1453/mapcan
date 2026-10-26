"""Backend of the web editor: the answers to requests that cannot be done, and helpers of the API."""

from __future__ import annotations

import asyncio
import shutil

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from mapcan.web import app as web_app
from mapcan.web.app import create_app
from mapcan.web.session import EditorSession

from .conftest import REFERENCE, ROOT


@pytest.fixture
def mapfile(tmp_path):
    p = tmp_path / "mapcan.yaml"
    shutil.copyfile(REFERENCE, p)
    return p


@pytest.fixture
def client(mapfile):
    with TestClient(create_app(EditorSession(mapfile), cwd=mapfile.parent)) as c:
        yield c


def code(r) -> tuple[int, str | None]:
    return r.status_code, r.json().get("code")


# --------------------------------------------------------------------------- export


def test_export_refuses_unknown_requests(client):
    assert client.get("/api/export/svg").status_code == 404
    assert client.get("/api/export/pdf?template=nope").status_code == 400
    r = client.get("/api/export/md?lang=english")
    assert r.status_code == 400 and "english" in r.json()["detail"]
    # A known alias of a language is taken
    assert client.get("/api/export/md?lang=en-US").status_code == 200


def test_export_eds_as_zip(client):
    r = client.get("/api/export/eds")
    assert r.status_code == 200 and r.headers["content-disposition"].endswith('mapcan-eds.zip"')


def test_export_errors(client, monkeypatch):
    from mapcan.extras import MissingExtra

    def missing(*extras):
        raise MissingExtra("xlsx")

    monkeypatch.setattr("mapcan.extras.require", missing)
    r = client.get("/api/export/xlsx")
    assert code(r) == (400, "missing-extra") and 'pip install "mapcan[xlsx]"' in r.json()["detail"]
    monkeypatch.undo()

    def broken(*args):
        raise RuntimeError("disk full")

    monkeypatch.setattr(web_app, "build_export", broken)
    r = client.get("/api/export/md")
    assert r.status_code == 500 and "disk full" in r.json()["detail"]


def test_build_export_without_an_extra(monkeypatch):
    from mapcan.extras import MissingExtra
    from mapcan.loader import load

    def missing(*extras):
        if extras:
            raise MissingExtra("pdf")

    monkeypatch.setattr("mapcan.extras.require", missing)
    with pytest.raises(web_app.AppError) as e:
        web_app.build_export(load(REFERENCE).map, "pdf", "m", None, None)
    assert e.value.code == "missing-extra"
    with pytest.raises(ValueError):
        web_app.build_export(load(REFERENCE).map, "svg", "m", None, None)


def test_export_of_a_map_with_structural_errors(tmp_path):
    p = tmp_path / "broken.yaml"
    p.write_text("mapcan: 2\ndocument: {title: X, language: en}\nbuses: 5\n", encoding="utf-8")
    with TestClient(create_app(EditorSession(p))) as c:
        assert c.get("/api/export/md").status_code == 409
        r = c.post("/api/diff/upload", files={"file": ("old.yaml", REFERENCE.read_bytes())})
        assert r.status_code == 409


# --------------------------------------------------------------------------- files and profile


def test_file_requests_that_fail(client, mapfile, tmp_path):
    assert code(client.post("/api/file/open", json={"path": "missing.yaml"})) == (404, "not-found")
    bad = tmp_path / "bad.yaml"
    bad.write_bytes(b"\xff\xfe\x00 not utf-8")
    assert code(client.post("/api/file/open", json={"path": str(bad)})) == (400, "read")
    # A new map over an existing file, or from an unknown template
    assert code(client.post("/api/file/new", json={"path": str(mapfile)})) == (409, "exists")
    assert code(client.post("/api/file/new", json={"path": "n.yaml", "template": "nope"})) == (400, "template")
    assert not (tmp_path / "n.yaml").exists()
    assert code(client.post("/api/file/example", json={"name": "nope", "path": "e.yaml"})) == (400, "template")
    assert code(client.post("/api/file/import_dbc", json={"source": "missing.dbc"})) == (404, "not-found")
    broken = tmp_path / "broken.dbc"
    broken.write_text("BO_ not a dbc", encoding="utf-8")
    assert code(client.post("/api/file/import_dbc", json={"source": str(broken), "path": "i.yaml"})) == \
        (400, "import")
    # Save as over an existing file
    other = tmp_path / "other.yaml"
    other.write_text("x", encoding="utf-8")
    assert code(client.post("/api/file/save_as", json={"path": str(other)})) == (409, "exists")
    # A file where a folder of the path should be: the file cannot be written there (not "it exists")
    assert code(client.post("/api/file/save_as", json={"path": str(bad / "sub")})) == (400, "write")
    # A name without .yaml gets it
    r = client.post("/api/file/save_as", json={"path": str(tmp_path / "copy")})
    assert r.status_code == 200 and (tmp_path / "copy.yaml").is_file()


def test_create_file_that_cannot_be_written(client, tmp_path):
    (tmp_path / "taken").write_text("a file, not a folder", encoding="utf-8")
    assert code(client.post("/api/file/new", json={"path": str(tmp_path / "taken" / "n.yaml"), "force": True})) == \
        (400, "write")


def test_user_profile_errors(client, monkeypatch):
    assert code(client.put("/api/user", json={"name": "Ann", "github": "not a login!"})) == (400, "github")

    def fail(self):
        raise OSError("read-only")

    monkeypatch.setattr("mapcan.userconfig.UserConfig.save", fail)
    assert code(client.put("/api/user", json={"name": "Ann"})) == (500, "config")


def test_activate_opens_the_file(mapfile, tmp_path):
    other = tmp_path / "other.yaml"
    shutil.copyfile(ROOT / "examples" / "minimal.yaml", other)
    bad = tmp_path / "bad.yaml"
    bad.write_bytes(b"\xff\xfe\x00")
    with TestClient(create_app(EditorSession(mapfile), instance_token="t")) as c:
        assert code(c.post("/api/instance/activate", json={"token": "t", "path": str(bad)})) == (400, "read")
        assert c.post("/api/instance/activate", json={"token": "t", "path": str(other)}).json() == {"ok": True}
        assert c.get("/api/meta").json()["file"] == str(other.resolve())


def test_list_dir(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "node_modules").mkdir()
    for name in ("a.yaml", "b.YML", "c.txt", "d.dbc"):
        (tmp_path / name).write_text("", encoding="utf-8")
    names = {e["name"] for e in web_app.list_dir(tmp_path)["entries"]}
    assert names == {"sub", "a.yaml", "b.YML"}
    assert {e["name"] for e in web_app.list_dir(tmp_path, "dbc")["entries"]} == {"sub", "d.dbc"}
    with pytest.raises(web_app.AppError) as e:
        web_app.list_dir(tmp_path / "a.yaml")
    assert e.value.code == "not-found"


def test_logo_errors(client, monkeypatch):
    assert code(client.get("/api/logo")) == (404, "no-logo")
    assert code(client.post("/api/logo", files={"file": ("logo.bmp", b"BM")})) == (400, "logo-format")
    monkeypatch.setattr(web_app, "LOGO_MAX_BYTES", 4)
    assert code(client.post("/api/logo", files={"file": ("logo.png", b"\x89PNG and more")})) == (400, "logo-size")


def test_diff_upload_errors(client):
    r = client.post("/api/diff/upload", files={"file": ("old.yaml", b"\xff\xfe")})
    assert r.status_code == 400 and "UTF-8" in r.json()["detail"]
    r = client.post("/api/diff/upload", files={"file": ("old.yaml", b"mapcan: [\n")})
    assert r.status_code == 400 and r.json()["detail"].startswith("old.yaml: ")


# --------------------------------------------------------------------------- git and GitHub


@pytest.mark.parametrize(("text", "expected"), [
    ("fatal: Not possible to fast-forward, aborting.", "git-diverged"),
    ("hint: You have divergent branches", "git-diverged"),
    ("error: Your local changes would be overwritten by merge", "git-local-changes"),
    ("! [rejected] main -> main (fetch first)", "git-push-rejected"),
])
def test_remote_errors_get_clear_codes(text, expected):
    e = web_app._remote_error(HTTPException(400, text), "origin/main")
    assert e.code == expected


def test_other_remote_errors_are_kept():
    e = HTTPException(400, "fatal: unable to access")
    assert web_app._remote_error(e, None) is e


def test_github_cli_missing(client, monkeypatch):
    monkeypatch.setattr(web_app.shutil, "which", lambda name: None)
    assert client.get("/api/gh/status").json() == {"installed": False, "user": None}
    assert code(client.post("/api/gh/create", json={"name": "bad name!"})) == (400, "gh-name")


def test_github_cli_status(client, monkeypatch):
    monkeypatch.setattr(web_app.shutil, "which", lambda name: "gh")
    monkeypatch.setattr(web_app, "_gh", lambda args, cwd, timeout=15: "octocat\n")
    assert client.get("/api/gh/status").json() == {"installed": True, "user": "octocat"}

    def not_signed_in(args, cwd, timeout=15):
        raise HTTPException(400, "gh auth login")

    monkeypatch.setattr(web_app, "_gh", not_signed_in)
    assert client.get("/api/gh/status").json() == {"installed": True, "user": None}


def test_git_tool_timeout(monkeypatch, tmp_path):
    import subprocess

    def slow(*args, **kw):
        raise subprocess.TimeoutExpired("git", 1)

    monkeypatch.setattr(web_app.subprocess, "run", slow)
    with pytest.raises(HTTPException) as e:
        web_app._git(["status"], tmp_path)
    assert e.value.status_code == 504
    assert web_app._refs_with_file(tmp_path, "m.yaml", []) == []


# --------------------------------------------------------------------------- helpers


def test_hostname():
    assert web_app._hostname("example.org:8080") == "example.org"
    assert web_app._hostname("[::1]:80") == "::1"
    assert web_app._hostname("[bad") is None


def test_hub_drops_closed_tabs():
    class Tab:
        def __init__(self, ok):
            self.ok, self.got = ok, []

        async def send_json(self, message):
            if not self.ok:
                raise RuntimeError("closed")
            self.got.append(message)

    hub = web_app.Hub()
    open_tab, closed_tab = Tab(True), Tab(False)
    hub.clients.update({open_tab, closed_tab})
    asyncio.run(hub.broadcast({"type": "state"}))
    assert hub.clients == {open_tab} and open_tab.got == [{"type": "state"}]


def test_without_a_built_interface(mapfile, monkeypatch, tmp_path):
    monkeypatch.setattr(web_app, "STATIC_DIR", tmp_path / "static")
    with TestClient(create_app(EditorSession(mapfile))) as c:
        r = c.get("/")
        assert r.status_code == 200 and "npm run build" in r.text
