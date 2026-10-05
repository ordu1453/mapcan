"""Запуск редактора как настольного приложения (`canmap app`, canmap.exe из установщика).

- Один экземпляр: повторный запуск (в том числе двойной щелчок по .yaml) передаёт
  файл уже открытому окну и выводит его на передний план.
- Порт 8765, а если он занят — любой свободный.
- Окно открывается, когда сервер действительно готов принимать запросы.
- Окно приложения — pywebview (WebView2 в Windows); без него — браузер по умолчанию.
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
from .userconfig import config_dir

DEFAULT_PORT = 8765
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


# --------------------------------------------------------------------------- порт и сервер


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as s:
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def pick_port(host: str, preferred: int = DEFAULT_PORT) -> int:
    """Предпочтительный порт, если свободен, иначе случайный свободный (0 — сразу случайный)."""
    if preferred > 0 and port_free(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def browser_url(host: str, port: int) -> str:
    h = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{'[' + h + ']' if ':' in h else h}:{port}/"


class ServerThread:
    """uvicorn в фоновом потоке: старт с ожиданием готовности и остановка."""

    def __init__(self, app, host: str, port: int):
        import uvicorn

        # log_config=None: в оконном .exe нет консоли, стандартный конфиг uvicorn на ней падает.
        self.server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning",
                                                    log_config=None))
        self.thread = threading.Thread(target=self.server.run, name="canmap-server", daemon=True)

    def start(self, timeout: float = 30.0) -> None:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while not self.server.started:
            if not self.thread.is_alive():
                raise RuntimeError("сервер canmap не запустился (порт занят?)")
            if time.monotonic() > deadline:
                raise RuntimeError("сервер canmap не ответил за отведённое время")
            time.sleep(0.02)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)

    def wait(self) -> None:
        """Ждать до Ctrl+C (режим браузера)."""
        try:
            while self.thread.is_alive():
                self.thread.join(0.5)
        except KeyboardInterrupt:
            self.stop()


# --------------------------------------------------------------------------- один экземпляр


def instance_file() -> Path:
    return config_dir() / "instance.json"


def activate_existing(path: Path | None, timeout: float = 2.0) -> bool:
    """Передать файл работающему экземпляру. True — экземпляр найден и ответил."""
    try:
        info = json.loads(instance_file().read_text(encoding="utf-8"))
        url = browser_url("127.0.0.1", int(info["port"])) + "api/instance/activate"
        body = json.dumps({"token": info["token"], "path": str(path.resolve()) if path else None}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — только localhost
            return r.status == 200
    except Exception:  # noqa: BLE001 — файла нет, процесс завершён, порт занят чужим
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


# --------------------------------------------------------------------------- окно


def _message_box(text: str, title: str = "canmap", yes_no: bool = False) -> bool:
    """Системное окно сообщения (Windows); в остальных ОС — вывод в stderr."""
    if os.name == "nt":
        flags = 0x40000 | (0x04 | 0x30 if yes_no else 0x10)     # MB_TOPMOST | (YESNO+WARNING | ERROR)
        return ctypes.windll.user32.MessageBoxW(None, text, title, flags) == 6  # IDYES
    if sys.stderr:
        print(f"{title}: {text}", file=sys.stderr)
    return True


def _unblock_bundle() -> None:
    """Снять с DLL сборки отметку «скачано из интернета» (Zone.Identifier).

    После распаковки zip-архива из браузера .NET отказывается загружать Python.Runtime.dll
    (pythonnet) с такой отметкой, и окно pywebview не открывается.
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


def _redirect_output() -> None:
    """В оконном .exe нет stdout/stderr — пишем их в лог, чтобы print/logging не падали."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    with contextlib.suppress(OSError):
        d = config_dir()
        d.mkdir(parents=True, exist_ok=True)
        log = open(d / "canmap.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115 — живёт до выхода
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def run(path: Path | None = None, *, window: bool = True, readonly: bool = False,
        single_instance: bool = True, check_updates: bool = True) -> int:
    """Открыть редактор. ``path`` — карта (.yaml) или рабочая папка."""
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
            win.on_top = True       # вывести поверх остальных окон и вернуть обычный режим
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
        _message_box(f"Не удалось открыть {path}:\n{e}")
        session = None

    app = create_app(session, cwd=cwd.resolve(), readonly=readonly, check_updates=check_updates,
                     instance_token=token if single_instance else None, on_activate=on_activate)
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
                if s is not None and s.text != s.saved_text:
                    return _message_box(f"В «{s.path.name}» есть несохранённые изменения.\n\n"
                                        "Закрыть без сохранения?", yes_no=True)
                return True

            webview.settings["ALLOW_DOWNLOADS"] = True
            win = webview.create_window("canmap", url, width=1440, height=900, min_size=(960, 600),
                                        maximized=True, text_select=True, zoomable=True)
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
            except Exception as e:  # noqa: BLE001 — нет WebView2 и т.п.: работаем в браузере
                win = None
                print(f"canmap: окно приложения недоступно ({e}), открываю браузер", file=sys.stderr)
                webbrowser.open(url)
                server.wait()
        else:
            print(f"canmap {__version__}: {url}  (Ctrl+C — остановить)", file=sys.stderr)
            webbrowser.open(url)
            server.wait()
    finally:
        if single_instance:
            _remove_instance(token)
        server.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Точка входа canmap.exe / canmap-app: ``canmap-app [карта.yaml | папка] [--browser]``."""
    import argparse

    _redirect_output()
    p = argparse.ArgumentParser(prog="canmap-app", description="Редактор карты сигналов canmap.")
    p.add_argument("path", nargs="?", type=Path, help="карта (.yaml) или рабочая папка")
    p.add_argument("--browser", action="store_true", help="открыть в браузере вместо окна приложения")
    p.add_argument("--readonly", action="store_true", help="только просмотр")
    p.add_argument("--version", action="version", version=f"canmap {__version__}")
    a = p.parse_args(argv)
    if a.path is not None and not a.path.exists():
        _message_box(f"Файл не найден:\n{a.path}")
        a.path = None
    return run(a.path, window=not a.browser, readonly=a.readonly)
