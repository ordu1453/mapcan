"""Файловые операции веб-редактора, профиль пользователя, версия."""

from __future__ import annotations

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from mapcan import __version__
from mapcan.loader import loads
from mapcan.userconfig import UserConfig, config_dir, normalize_github
from mapcan.web.app import create_app
from mapcan.web.newmap import TEMPLATES, new_map_text
from mapcan.web.session import EditorSession

from .conftest import REFERENCE


@pytest.fixture
def empty(tmp_path):
    """Редактор, запущенный без карты (стартовый экран)."""
    with TestClient(create_app(None, cwd=tmp_path, poll_interval=0.05)) as c:
        yield c


def test_meta_without_session(empty, tmp_path):
    m = empty.get("/api/meta").json()
    assert m["version"] == __version__
    assert m["open"] is False and m["cwd"] == str(tmp_path.resolve())
    assert set(m["templates"]) == set(TEMPLATES)
    r = empty.get("/api/state")
    assert r.status_code == 409 and r.json()["code"] == "no-session"


def test_user_profile_roundtrip(empty):
    r = empty.put("/api/user", json={"name": "Иван Петров", "github": "https://github.com/ivan-p/"})
    assert r.status_code == 200
    assert r.json() == {"name": "Иван Петров", "github": "ivan-p", "github_url": "https://github.com/ivan-p"}
    saved = json.loads((config_dir() / "config.json").read_text(encoding="utf-8"))
    assert saved["user"]["github"] == "ivan-p"
    assert empty.get("/api/meta").json()["user"]["name"] == "Иван Петров"
    bad = empty.put("/api/user", json={"name": "x", "github": "not a user!"})
    assert bad.status_code == 400 and bad.json()["code"] == "github"


@pytest.mark.parametrize("raw, user", [("@octo-cat", "octo-cat"), ("github.com/abc", "abc"), ("", None), (None, None)])
def test_normalize_github(raw, user):
    assert normalize_github(raw) == user


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_templates_are_valid(template):
    res = loads(new_map_text(template, "Тест", "Иван", "ivan"), "t.yaml")
    assert res.map is not None, [d.format() for d in res.report.diagnostics]
    h = res.map.document.history[0]
    assert (h.author, h.github) == ("Иван", "ivan")


def test_new_open_recent(empty, tmp_path):
    empty.put("/api/user", json={"name": "Иван", "github": "ivan"})
    r = empty.post("/api/file/new", json={"path": "maps/new_map", "template": "canopen", "title": "Моя карта"})
    assert r.status_code == 200, r.text
    body = r.json()
    path = tmp_path / "maps" / "new_map.yaml"
    assert path.is_file() and body["meta"]["open"] and body["meta"]["file"] == str(path.resolve())
    assert body["state"]["data"]["document"]["title"] == "Моя карта"
    assert "github: ivan" in body["state"]["text"]
    assert not [d for d in body["state"]["diagnostics"] if d["level"] == "error"]

    again = empty.post("/api/file/new", json={"path": "maps/new_map.yaml"})
    assert again.status_code == 409 and again.json()["code"] == "exists"

    other = tmp_path / "other.yaml"
    shutil.copyfile(REFERENCE, other)
    r = empty.post("/api/file/open", json={"path": str(other)})
    assert r.json()["meta"]["file"] == str(other.resolve())
    recent = [x["path"] for x in empty.get("/api/meta").json()["recent"]]
    assert recent[:2] == [str(other.resolve()), str(path.resolve())]
    assert UserConfig.load().recent[0] == str(other.resolve())


def test_unsaved_guard(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    shutil.copyfile(REFERENCE, a)
    shutil.copyfile(REFERENCE, b)
    with TestClient(create_app(EditorSession(a), cwd=tmp_path)) as c:
        c.post("/api/ops", json={"ops": [{"op": "set", "path": ["document", "version"], "value": "9.9"}]})
        r = c.post("/api/file/open", json={"path": str(b)})
        assert r.status_code == 409 and r.json()["code"] == "unsaved"
        assert c.post("/api/file/close", json={}).status_code == 409
        assert c.post("/api/file/open", json={"path": str(b), "force": True}).status_code == 200
        assert c.post("/api/file/close", json={}).json() == {
            "meta": c.get("/api/meta").json(), "state": None}


def test_save_as(tmp_path):
    a = tmp_path / "a.yaml"
    shutil.copyfile(REFERENCE, a)
    with TestClient(create_app(EditorSession(a), cwd=tmp_path)) as c:
        c.post("/api/ops", json={"ops": [{"op": "set", "path": ["document", "version"], "value": "2.0"}]})
        r = c.post("/api/file/save_as", json={"path": "copy"})
        assert r.status_code == 200
        st = r.json()["state"]
        assert st["file"] == "copy.yaml" and not st["dirty"]
        assert "version: '2.0'" in (tmp_path / "copy.yaml").read_text(encoding="utf-8")
        assert "version: 1.0.0" in a.read_text(encoding="utf-8")          # исходник не тронут
        assert c.post("/api/file/save_as", json={"path": str(a)}).json()["code"] == "exists"
        assert c.post("/api/file/save_as", json={"path": str(a), "overwrite": True}).status_code == 200


def test_fs_list(empty, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "m.yaml").write_text("a: 1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    r = empty.get("/api/fs/list").json()
    assert [e["name"] for e in r["entries"]] == ["sub", "m.yaml"]
    assert r["parent"] == str(tmp_path.resolve().parent)
    assert empty.get("/api/fs/list", params={"dir": str(tmp_path / "nope")}).status_code == 404


def test_readonly_workspace(tmp_path):
    a = tmp_path / "a.yaml"
    shutil.copyfile(REFERENCE, a)
    with TestClient(create_app(EditorSession(a, readonly=True), cwd=tmp_path)) as c:
        assert c.post("/api/file/new", json={"path": "n.yaml"}).status_code == 403
        assert c.post("/api/file/save_as", json={"path": "n.yaml"}).status_code == 403
        b = tmp_path / "b.yaml"
        shutil.copyfile(REFERENCE, b)
        r = c.post("/api/file/open", json={"path": str(b)})          # просмотр других файлов — можно
        assert r.status_code == 200 and r.json()["state"]["readonly"]


def test_history_author_in_documents(tmp_path):
    from mapcan.export.text import render

    text = new_map_text("canopen", "Карта", "Иван", "ivan")
    m = loads(text, "t.yaml").map
    md = render(m, "md")
    assert "Иван [@ivan](https://github.com/ivan)" in md
    assert '<a href="https://github.com/ivan">@ivan</a>' in render(m, "html")


def test_legacy_config_dir_is_renamed(tmp_path, monkeypatch):
    monkeypatch.delenv("MAPCAN_CONFIG_DIR")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / ".canmap").mkdir()
    (tmp_path / ".canmap" / "config.json").write_text('{"language": "ru"}', encoding="utf-8")
    assert config_dir() == tmp_path / ".mapcan"
    assert (tmp_path / ".mapcan" / "config.json").is_file() and not (tmp_path / ".canmap").exists()
