"""Desktop launch: a single instance, port choice, update check."""

from __future__ import annotations

import json
import shutil
import socket
import sys
from types import SimpleNamespace

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


# --------------------------------------------------------------------------- versions and updates


@pytest.mark.parametrize(("latest", "current", "newer"), [
    ("0.7.0", "0.6.0", True),
    ("v0.6.1", "0.6.0", True),
    ("1.0", "0.9.9", True),
    ("0.6.0", "0.6.0", False),
    ("0.5.9", "0.6.0", False),
    ("0.7.0-rc1", "0.6.0", False),   # pre-releases are not offered
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
    assert updates.check() == first and len(calls) == 1          # the second time from the cache


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
        assert c.get("/api/update").json()["newer"] is False         # not checked by default
    with TestClient(create_app(EditorSession(mapfile), check_updates=True)) as c:
        assert c.get("/api/update").json()["newer"] is True


# --------------------------------------------------------------------------- activating the instance


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
        # No edits: the server opens the file (the window may not be connected yet).
        r = c.post("/api/instance/activate", json={"token": "secret", "path": str(other)})
        assert r.status_code == 200 and focused == [1]
        assert ws.receive_json()["type"] == "session"
        assert c.get("/api/meta").json()["file"] == str(other.resolve())
        # There are unsaved edits: the tab decides.
        c.post("/api/text", json={"text": c.get("/api/state").json()["text"] + "\n# правка\n"})
        assert ws.receive_json()["type"] == "state"
        c.post("/api/instance/activate", json={"token": "secret", "path": str(mapfile)})
        assert ws.receive_json() == {"type": "open-request", "path": str(mapfile.resolve())}
        assert c.get("/api/meta").json()["file"] == str(other.resolve())


# --------------------------------------------------------------------------- port and server


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
        assert not launcher.activate_existing(mapfile)               # no instance file yet
        launcher._write_instance(port, "tok")
        assert json.loads(launcher.instance_file().read_text(encoding="utf-8"))["port"] == port
        assert launcher.activate_existing(mapfile) and focused == [1]
        launcher._remove_instance("other")                          # another token: the file is left alone
        assert launcher.instance_file().exists()
        launcher._remove_instance("tok")
        assert not launcher.instance_file().exists()
    finally:
        server.stop()
    assert not server.thread.is_alive()


def test_browser_url():
    assert launcher.browser_url("0.0.0.0", 80) == "http://127.0.0.1:80/"
    assert launcher.browser_url("::1", 80) == "http://[::1]:80/"
    assert launcher.browser_url("::", 80) == "http://127.0.0.1:80/"


class _Thread:
    def __init__(self, alive=True, interrupt=False):
        self.alive, self.interrupt, self.joined = alive, interrupt, []

    def start(self):
        pass

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.joined.append(timeout)
        if self.interrupt:
            self.interrupt = False      # Ctrl+C once, while waiting
            raise KeyboardInterrupt
        self.alive = False


def _server_thread(thread, started=False):
    st = launcher.ServerThread(create_app(None), "127.0.0.1", 0)
    st.thread = thread
    st.server.started = started
    return st


def test_server_thread_start_errors():
    with pytest.raises(RuntimeError, match="port"):
        _server_thread(_Thread(alive=False)).start()
    with pytest.raises(RuntimeError, match="in time"):
        _server_thread(_Thread()).start(timeout=0)
    _server_thread(_Thread(), started=True).start()


def test_server_thread_wait_stops_on_ctrl_c():
    st = _server_thread(_Thread(interrupt=True))
    st.wait()
    assert st.server.should_exit
    st = _server_thread(_Thread())
    st.wait()
    assert st.thread.joined == [0.5] and not st.server.should_exit


@pytest.fixture
def boxes(monkeypatch):
    """System message boxes: what was asked, and the answers to give (IDYES 6, IDNO 7, IDCANCEL 2)."""
    seen = {"asked": [], "answers": []}

    def box(_owner, text, title, flags):
        seen["asked"].append((text, title, flags))
        return seen["answers"].pop(0) if seen["answers"] else 1

    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(launcher, "ctypes", SimpleNamespace(windll=SimpleNamespace(
        user32=SimpleNamespace(MessageBoxW=box))))
    return seen


def test_message_boxes_on_windows(boxes):
    boxes["answers"] = [6, 7, 6, 7, 2]
    assert launcher._message_box("Sure?", yes_no=True) is True
    assert launcher._message_box("Sure?", yes_no=True) is False
    assert [launcher._ask_save("Save?") for _ in range(3)] == [True, False, None]
    assert [title for _t, title, _f in boxes["asked"]] == ["mapcan"] * 5


def test_message_boxes_elsewhere(monkeypatch, capsys):
    monkeypatch.setattr(launcher.os, "name", "posix")
    assert launcher._message_box("Broken", "Title") is True
    assert launcher._ask_save("Save?") is False
    assert capsys.readouterr().err == "Title: Broken\nmapcan: Save?\n"


def test_unblock_bundle(monkeypatch, tmp_path):
    (tmp_path / "sub").mkdir()
    for name in ("a.dll", "sub/b.dll", "c.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    removed = []
    monkeypatch.setattr(launcher.os, "remove", removed.append)
    launcher._unblock_bundle()          # not a frozen build: nothing
    assert removed == []
    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    launcher._unblock_bundle()
    assert sorted(removed) == sorted(f"{tmp_path / n}:Zone.Identifier" for n in ("a.dll", "sub/b.dll"))


def test_webview_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)
    assert launcher._webview() is None


def test_redirect_output(monkeypatch):
    from mapcan.userconfig import config_dir

    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", None)
    launcher._redirect_output()
    print("to the log", file=sys.stderr)
    sys.stderr.close()
    assert "to the log" in (config_dir() / "mapcan.log").read_text(encoding="utf-8")


@pytest.fixture
def fake_run(monkeypatch, boxes):
    """launcher.run with the server, the browser and the window replaced: what they were asked to do."""
    import webbrowser

    from mapcan.web import app as web_app

    seen = {"opened": [], "stopped": 0, "waited": 0}

    class Server:
        def __init__(self, app, host, port):
            seen["port"] = port

        def start(self):
            if seen.get("fail"):
                raise RuntimeError("the port is busy")

        def stop(self):
            seen["stopped"] += 1

        def wait(self):
            seen["waited"] += 1
            f = launcher.instance_file()
            seen["instance"] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def create(session, **kw):
        seen.update(session=session, **kw)
        return SimpleNamespace(state=SimpleNamespace(workspace=SimpleNamespace(session=session)))

    monkeypatch.setattr(launcher, "activate_existing", lambda path: seen.get("running", False))
    monkeypatch.setattr(launcher, "ServerThread", Server)
    monkeypatch.setattr(launcher, "pick_port", lambda host, preferred=0: 9001)
    monkeypatch.setattr(web_app, "create_app", create)
    monkeypatch.setattr(webbrowser, "open", seen["opened"].append)
    return seen


def test_run_in_the_browser(fake_run, mapfile, tmp_path):
    assert launcher.run(mapfile, window=False, readonly=True) == 0
    assert fake_run["opened"] == ["http://127.0.0.1:9001/"] and fake_run["waited"] == 1 and fake_run["stopped"] == 1
    assert fake_run["session"].path == mapfile and fake_run["readonly"] and fake_run["cwd"] == tmp_path.resolve()
    assert fake_run["mode"] == "app" and fake_run["instance_token"]
    # The instance file is there while the editor runs, and removed after
    assert fake_run["instance"]["port"] == 9001 and not launcher.instance_file().exists()
    # Activating the running instance opens the browser again
    fake_run["on_activate"]()
    assert fake_run["opened"][-1] == "http://127.0.0.1:9001/"

    # A folder: the start screen; without a single instance: no token and no instance file
    assert launcher.run(tmp_path, window=False, single_instance=False) == 0
    assert fake_run["session"] is None and fake_run["cwd"] == tmp_path.resolve()
    assert fake_run["instance_token"] is None and fake_run["instance"] is None


def test_run_hands_over_to_the_running_instance(fake_run, mapfile):
    fake_run["running"] = True
    assert launcher.run(mapfile) == 0 and "port" not in fake_run


def test_run_errors(fake_run, boxes, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_bytes(b"\xff\xfe\x00broken")
    fake_run["fail"] = True
    assert launcher.run(bad, window=False) == 1
    texts = [t for t, _title, _f in boxes["asked"]]
    assert str(bad) in texts[0] and texts[1] == "the port is busy"
    assert fake_run["session"] is None


class _Events:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _Window:
    def __init__(self, seen):
        self.seen, self.on_top_history = seen, []
        self.events = SimpleNamespace(closing=_Events(), minimized=_Events(), restored=_Events(),
                                      maximized=_Events())

    def restore(self):
        self.seen["restored"] = True

    def show(self):
        self.seen["shown"] = True

    def __setattr__(self, name, value):
        if name == "on_top":
            self.on_top_history.append(value)
        object.__setattr__(self, name, value)


def _fake_webview(monkeypatch, seen, start):
    def create_window(title, url, **kw):
        seen["window"] = _Window(seen)
        seen["window_url"] = url
        return seen["window"]

    wv = SimpleNamespace(settings={}, create_window=create_window, start=lambda **kw: start(seen["window"], kw))
    monkeypatch.setattr(launcher, "_webview", lambda: wv)
    return wv


def test_run_in_the_window(fake_run, monkeypatch, mapfile):
    def start(win, kw):
        fake_run["storage"] = kw["storage_path"]
        # Minimized, then activated by a second launch: restored and brought to the front
        for h in win.events.minimized.handlers:
            h()
        fake_run["on_activate"]()
        fake_run["closing"] = [h() for h in win.events.closing.handlers]

    wv = _fake_webview(monkeypatch, fake_run, start)
    assert launcher.run(mapfile) == 0
    assert wv.settings["ALLOW_DOWNLOADS"] and fake_run["window_url"] == "http://127.0.0.1:9001/"
    assert fake_run["restored"] and fake_run["shown"] and fake_run["window"].on_top_history == [True, False]
    assert fake_run["closing"] == [True]        # nothing unsaved: the window closes
    assert fake_run["storage"].endswith("webview") and fake_run["opened"] == []


@pytest.mark.parametrize(("answers", "save_fails", "closes", "saved"), [
    ([2], False, False, False),     # Cancel: the window stays
    ([7], False, True, False),      # No: closes without saving
    ([6], False, True, True),       # Yes: saved, then closes
    ([6], True, False, False),      # Yes, but saving fails: an error box, the window stays
])
def test_closing_the_window_with_unsaved_changes(fake_run, monkeypatch, boxes, mapfile, answers, save_fails, closes,
                                                 saved):
    def start(win, kw):
        calls = []

        def save():
            calls.append(1)
            if save_fails:
                raise OSError("read-only")

        session = fake_run["session"]
        monkeypatch.setattr(type(session), "dirty", property(lambda self: True))
        monkeypatch.setattr(session, "save", save)
        boxes["answers"] = list(answers)
        fake_run["closing"] = [h() for h in win.events.closing.handlers]
        fake_run["saved"] = bool(calls) and not save_fails

    _fake_webview(monkeypatch, fake_run, start)
    launcher.run(mapfile)
    assert fake_run["closing"] == [closes] and fake_run["saved"] is saved
    assert ("read-only" in boxes["asked"][-1][0]) is save_fails


def test_run_falls_back_to_the_browser_without_a_window(fake_run, monkeypatch, mapfile, capsys):
    def start(win, kw):
        raise RuntimeError("no WebView2")

    _fake_webview(monkeypatch, fake_run, start)
    assert launcher.run(mapfile) == 0
    assert fake_run["opened"] == ["http://127.0.0.1:9001/"] and fake_run["waited"] == 1
    assert "no WebView2" in capsys.readouterr().err
    fake_run["on_activate"]()
    assert fake_run["opened"][-1] == "http://127.0.0.1:9001/"


def test_main(monkeypatch, boxes, mapfile, tmp_path):
    calls = []
    monkeypatch.setattr(launcher, "run", lambda path, **kw: calls.append((path, kw)) or 5)
    assert launcher.main([str(mapfile), "--browser", "--readonly"]) == 5
    assert launcher.main([str(tmp_path / "missing.yaml")]) == 5
    assert calls == [(mapfile, {"window": False, "readonly": True}), (None, {"window": True, "readonly": False})]
    assert "missing.yaml" in boxes["asked"][0][0]
