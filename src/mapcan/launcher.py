"""Running the editor as a desktop app (`mapcan app`, mapcan.exe from the installer).

- One instance: running it again (also a double click on a .yaml) passes the
  file to the window that is already open and brings it to the front.
- Port 8765, or any free one if it is taken.
- The window opens when the server is really ready to take requests.
- The app window is pywebview (WebView2 on Windows); without it, the default browser.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__
from .i18n import _
from .userconfig import config_dir

DEFAULT_PORT = 8765
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


# --------------------------------------------------------------------------- port and server


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as s:
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def pick_port(host: str, preferred: int = DEFAULT_PORT) -> int:
    """The preferred port if it is free, otherwise a random free one (0: random right away)."""
    if preferred > 0 and port_free(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def browser_url(host: str, port: int) -> str:
    h = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{'[' + h + ']' if ':' in h else h}:{port}/"


class ServerThread:
    """uvicorn in a background thread: start that waits until it is ready, and stop."""

    def __init__(self, app, host: str, port: int):
        import uvicorn

        # log_config=None: a windowed .exe has no console, and uvicorn's default config fails on it.
        self.server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning",
                                                    log_config=None))
        self.thread = threading.Thread(target=self.server.run, name="mapcan-server", daemon=True)

    def start(self, timeout: float = 30.0) -> None:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while not self.server.started:
            if not self.thread.is_alive():
                raise RuntimeError(_("the mapcan server did not start (is the port in use?)"))
            if time.monotonic() > deadline:
                raise RuntimeError(_("the mapcan server did not respond in time"))
            time.sleep(0.02)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)

    def wait(self) -> None:
        """Wait until Ctrl+C (browser mode)."""
        try:
            while self.thread.is_alive():
                self.thread.join(0.5)
        except KeyboardInterrupt:
            self.stop()


# --------------------------------------------------------------------------- single instance


def instance_file() -> Path:
    return config_dir() / "instance.json"


def activate_existing(path: Path | None, timeout: float = 2.0) -> bool:
    """Pass a file to the running instance. True: the instance was found and answered."""
    try:
        info = json.loads(instance_file().read_text(encoding="utf-8"))
        url = browser_url("127.0.0.1", int(info["port"])) + "api/instance/activate"
        body = json.dumps({"token": info["token"], "path": str(path.resolve()) if path else None}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — localhost only
            return r.status == 200
    except Exception:  # noqa: BLE001 — no file, the process has ended, the port is someone else's
        return False


def _write_instance(port: int, token: str) -> None:
    with contextlib.suppress(OSError):
        d = config_dir()
        d.mkdir(parents=True, exist_ok=True)
        f = instance_file()
        f.write_text(json.dumps({"port": port, "token": token, "pid": os.getpid(), "version": __version__}),
                     encoding="utf-8")


def _remove_instance(token: str) -> None:
    with contextlib.suppress(OSError, ValueError, KeyError):
        f = instance_file()
        if json.loads(f.read_text(encoding="utf-8"))["token"] == token:
            f.unlink()


# --------------------------------------------------------------------------- window


def _message_box(text: str, title: str = "mapcan", yes_no: bool = False) -> bool:
    """System message box (Windows); on other systems, output to stderr."""
    if os.name == "nt":
        flags = 0x40000 | (0x04 | 0x30 if yes_no else 0x10)     # MB_TOPMOST | (YESNO+WARNING | ERROR)
        return ctypes.windll.user32.MessageBoxW(None, text, title, flags) == 6  # IDYES
    if sys.stderr:
        print(f"{title}: {text}", file=sys.stderr)
    return True


def _ask_save(text: str, title: str = "mapcan") -> bool | None:
    """Yes / No / Cancel: True to save, False not to save, None to cancel the action.

    Outside Windows there is no way to ask: close without saving, as before.
    """
    if os.name == "nt":
        flags = 0x40000 | 0x03 | 0x30      # MB_TOPMOST | MB_YESNOCANCEL | MB_ICONWARNING
        r = ctypes.windll.user32.MessageBoxW(None, text, title, flags)
        return {6: True, 7: False}.get(r)  # IDYES, IDNO; IDCANCEL and closing the box cancel
    if sys.stderr:
        print(f"{title}: {text}", file=sys.stderr)
    return False


def _unblock_bundle() -> None:
    """Remove the "downloaded from the internet" mark (Zone.Identifier) from the build's DLLs.

    After a zip archive is extracted from the browser, .NET refuses to load Python.Runtime.dll
    (pythonnet) with such a mark, and the pywebview window does not open.
    """
    root = getattr(sys, "_MEIPASS", None)
    if os.name != "nt" or not getattr(sys, "frozen", False) or not root:
        return
    for dll in Path(root).rglob("*.dll"):
        with contextlib.suppress(OSError):
            os.remove(f"{dll}:Zone.Identifier")


def _webview():
    _unblock_bundle()
    try:
        import webview
    except ImportError:
        return None
    return webview


class DialogApi:
    """Methods for the window's JS (window.pywebview.api): the system open and save file dialogs."""

    FILE_TYPES = ("YAML (*.yaml;*.yml)", "All files (*.*)")

    def __init__(self, get_window):
        self._get_window = get_window   # with "_": pywebview does not expose the attribute to JS

    def pick_file(self, mode: str, directory: str = "", filename: str = "") -> str | None:
        """``mode``: "open" or "save". Returns the chosen path or None (cancelled)."""
        import webview

        win = self._get_window()
        if win is None:
            return None
        kind = webview.FileDialog.SAVE if mode == "save" else webview.FileDialog.OPEN
        result = win.create_file_dialog(kind, directory=directory or "", save_filename=filename or "",
                                        file_types=self.FILE_TYPES)
        if not result:
            return None
        return result if isinstance(result, str) else result[0]


def _redirect_output() -> None:
    """A windowed .exe has no stdout/stderr: write them to a log so that print/logging do not fail."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    with contextlib.suppress(OSError):
        d = config_dir()
        d.mkdir(parents=True, exist_ok=True)
        log = open(d / "mapcan.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115 — lives until exit
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def run(path: Path | None = None, *, window: bool = True, readonly: bool = False,
        single_instance: bool = True, check_updates: bool = True) -> int:
    """Open the editor. ``path`` is a map (.yaml) or a workspace folder."""
    from .web.app import create_app
    from .web.session import EditorSession

    _redirect_output()
    if single_instance and activate_existing(path):
        return 0

    host = "127.0.0.1"
    port = pick_port(host)
    token = secrets.token_urlsafe(16)
    url = browser_url(host, port)
    webview = _webview() if window else None
    win = None
    minimized = False

    def on_activate() -> None:
        if win is not None:
            if minimized:
                win.restore()
            win.show()
            win.on_top = True       # bring it above the other windows, then back to normal
            win.on_top = False
        else:
            webbrowser.open(url)

    session, cwd = None, Path.cwd()
    try:
        if path is not None and path.is_dir():
            cwd = path
        elif path is not None:
            session = EditorSession(path, readonly=readonly)
            cwd = path.resolve().parent
    except (OSError, UnicodeDecodeError) as e:
        _message_box(_("Could not open {path}:\n{error}", path=path, error=e))
        session = None

    app = create_app(session, cwd=cwd.resolve(), readonly=readonly, check_updates=check_updates,
                     instance_token=token if single_instance else None, on_activate=on_activate,
                     allowed_hosts=LOCAL_HOSTS)
    server = ServerThread(app, host, port)
    try:
        server.start()
    except RuntimeError as e:
        _message_box(str(e))
        return 1
    if single_instance:
        _write_instance(port, token)

    try:
        if webview is not None:
            wsp = app.state.workspace

            def on_closing() -> bool:
                s = wsp.session
                if s is None or s.text == s.saved_text:
                    return True
                answer = _ask_save(_("“{name}” has unsaved changes.\n\nSave before closing?", name=s.path.name))
                if answer is None:
                    return False
                if answer:
                    try:
                        s.save()
                    except Exception as e:  # noqa: BLE001 — read-only file, changed outside etc.
                        _message_box(_("Could not save {path}:\n{error}", path=s.path, error=e))
                        return False
                return True

            webview.settings["ALLOW_DOWNLOADS"] = True
            win = webview.create_window("mapcan", url, width=1440, height=900, min_size=(960, 600),
                                        maximized=True, text_select=True, zoomable=True,
                                        js_api=DialogApi(lambda: win))
            def set_minimized(value: bool):
                def handler() -> None:
                    nonlocal minimized
                    minimized = value
                return handler

            win.events.closing += on_closing
            win.events.minimized += set_minimized(True)
            win.events.restored += set_minimized(False)
            win.events.maximized += set_minimized(False)
            try:
                storage = config_dir() / "webview"
                webview.start(private_mode=False, storage_path=str(storage))
            except Exception as e:  # noqa: BLE001 — no WebView2 etc.: work in the browser
                win = None
                print(_(
                    "mapcan: the app window is unavailable ({error}), opening the browser", error=e), file=sys.stderr)
                webbrowser.open(url)
                server.wait()
        else:
            print(_("mapcan {version}: {url}  (Ctrl+C to stop)", version=__version__, url=url), file=sys.stderr)
            webbrowser.open(url)
            server.wait()
    finally:
        if single_instance:
            _remove_instance(token)
        server.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point of mapcan.exe / mapcan-app: ``mapcan-app [map.yaml | folder] [--browser]``."""
    import argparse

    _redirect_output()
    p = argparse.ArgumentParser(prog="mapcan-app", description=_("mapcan signal map editor."))
    p.add_argument("path", nargs="?", type=Path, help=_("map (.yaml) or working folder"))
    p.add_argument("--browser", action="store_true", help=_("open in a browser instead of the app window"))
    p.add_argument("--readonly", action="store_true", help=_("view only"))
    p.add_argument("--version", action="version", version=f"mapcan {__version__}")
    a = p.parse_args(argv)
    if a.path is not None and not a.path.exists():
        _message_box(_("File not found:\n{path}", path=a.path))
        a.path = None
    return run(a.path, window=not a.browser, readonly=a.readonly)
