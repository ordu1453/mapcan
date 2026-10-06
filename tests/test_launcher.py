"""Настольный запуск: один экземпляр, выбор порта, проверка обновлений."""

from __future__ import annotations

import json
import shutil
import socket

import pytest
from fastapi.testclient import TestClient

from mapcan import launcher, updates
from mapcan.web.app import create_app
from mapcan.web.session import EditorSession

from .conftest import REFERENCE


@pytest.fixture
def mapfile(tmp_path):
    p = tmp_path / "mapcan.yaml"
    shutil.copyfile(REFERENCE, p)
    return p


# --------------------------------------------------------------------------- версии и обновления


@pytest.mark.parametrize(("latest", "current", "newer"), [
    ("0.7.0", "0.6.0", True),
    ("v0.6.1", "0.6.0", True),
    ("1.0", "0.9.9", True),
    ("0.6.0", "0.6.0", False),
    ("0.5.9", "0.6.0", False),
    ("0.7.0-rc1", "0.6.0", False),   # пред-релизы не предлагаем
    ("", "0.6.0", False),
])
def test_is_newer(latest, current, newer):
    assert updates.is_newer(latest, current) is newer


def test_check_uses_cache(monkeypatch):
    calls = []

    def fake_fetch(timeout):
        calls.append(timeout)
        return {"latest": "99.0.0", "url": "https://example/r", "installer": "https://example/s.exe"}

    monkeypatch.setattr(updates, "_fetch", fake_fetch)
    first = updates.check()
    assert first["newer"] and first["latest"] == "99.0.0" and first["installer"] == "https://example/s.exe"
    assert updates.check() == first and len(calls) == 1          # второй раз — из кеша


def test_check_network_error_and_disable(monkeypatch):
    def boom(timeout):
        raise OSError("нет сети")

    monkeypatch.setattr(updates, "_fetch", boom)
    assert updates.check()["newer"] is False
    monkeypatch.setenv("MAPCAN_NO_UPDATE_CHECK", "1")
    monkeypatch.setattr(updates, "_fetch", lambda t: pytest.fail("проверка отключена"))
    assert updates.check(use_cache=False)["latest"] is None


def test_update_endpoint(monkeypatch, mapfile):
    monkeypatch.setattr(updates, "_fetch", lambda t: {"latest": "99.0.0", "url": "u", "installer": None})
    with TestClient(create_app(EditorSession(mapfile))) as c:
        assert c.get("/api/update").json()["newer"] is False         # по умолчанию не проверяем
    with TestClient(create_app(EditorSession(mapfile), check_updates=True)) as c:
        assert c.get("/api/update").json()["newer"] is True


# --------------------------------------------------------------------------- активация экземпляра


def test_activate_requires_token(mapfile):
    with TestClient(create_app(EditorSession(mapfile))) as c:
        assert c.post("/api/instance/activate", json={"token": "x"}).status_code == 403
    with TestClient(create_app(EditorSession(mapfile), instance_token="secret")) as c:
        assert c.post("/api/instance/activate", json={"token": "x"}).status_code == 403


def test_activate_focuses_and_opens(mapfile, tmp_path):
    focused = []
    other = tmp_path / "other.yaml"
    shutil.copyfile(REFERENCE, other)
    app = create_app(EditorSession(mapfile), instance_token="secret", on_activate=lambda: focused.append(1))
    with TestClient(app) as c, c.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        # Правок нет — файл открывает сервер (окно могло ещё не подключиться).
        r = c.post("/api/instance/activate", json={"token": "secret", "path": str(other)})
        assert r.status_code == 200 and focused == [1]
        assert ws.receive_json()["type"] == "session"
        assert c.get("/api/meta").json()["file"] == str(other.resolve())
        # Есть несохранённые правки — решает вкладка.
        c.post("/api/text", json={"text": c.get("/api/state").json()["text"] + "\n# правка\n"})
        assert ws.receive_json()["type"] == "state"
        c.post("/api/instance/activate", json={"token": "secret", "path": str(mapfile)})
        assert ws.receive_json() == {"type": "open-request", "path": str(mapfile.resolve())}
        assert c.get("/api/meta").json()["file"] == str(other.resolve())


# --------------------------------------------------------------------------- порт и сервер


def test_pick_port_falls_back_when_busy():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        busy = s.getsockname()[1]
        port = launcher.pick_port("127.0.0.1", busy)
        assert port != busy and launcher.port_free("127.0.0.1", port)


def test_native_file_dialog():
    webview = pytest.importorskip("webview")
    calls = []

    class FakeWindow:
        def __init__(self, result):
            self.result = result

        def create_file_dialog(self, kind, **kw):
            calls.append((kind, kw))
            return self.result

    api = launcher.DialogApi(lambda: FakeWindow(("C:/maps/a.yaml",)))
    assert api.pick_file("open", "C:/maps") == "C:/maps/a.yaml"
    assert calls[-1][0] == webview.FileDialog.OPEN and calls[-1][1]["directory"] == "C:/maps"

    api = launcher.DialogApi(lambda: FakeWindow("C:/maps/b.yaml"))
    assert api.pick_file("save", "", "b.yaml") == "C:/maps/b.yaml"
    assert calls[-1][0] == webview.FileDialog.SAVE and calls[-1][1]["save_filename"] == "b.yaml"

    assert launcher.DialogApi(lambda: FakeWindow(None)).pick_file("open") is None
    assert launcher.DialogApi(lambda: None).pick_file("open") is None


def test_second_launch_activates_running_instance(mapfile):
    port = launcher.pick_port("127.0.0.1", 0)
    focused = []
    app = create_app(EditorSession(mapfile), instance_token="tok", on_activate=lambda: focused.append(1))
    server = launcher.ServerThread(app, "127.0.0.1", port)
    server.start()
    try:
        assert not launcher.activate_existing(mapfile)               # файла экземпляра ещё нет
        launcher._write_instance(port, "tok")
        assert json.loads(launcher.instance_file().read_text(encoding="utf-8"))["port"] == port
        assert launcher.activate_existing(mapfile) and focused == [1]
        launcher._remove_instance("other")                          # чужой токен — файл не трогаем
        assert launcher.instance_file().exists()
        launcher._remove_instance("tok")
        assert not launcher.instance_file().exists()
    finally:
        server.stop()
    assert not server.thread.is_alive()
