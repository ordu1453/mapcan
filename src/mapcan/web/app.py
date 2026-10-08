"""FastAPI-приложение веб-редактора (`mapcan serve`)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import os
import re
import shutil
import string
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import __version__, updates
from ..diff import changelog_lines, diff_maps, release_draft, release_message
from ..i18n import _, normalize_language
from ..loader import loads
from ..model import MapCan
from ..userconfig import UserConfig, normalize_github
from .examples import example_includes, example_text, list_examples
from .newmap import new_map_text, template_labels
from .session import ConflictError, EditorSession, ReadOnlyError
from .yamlops import OpError

STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGO_MAX_BYTES = 5 * 1024 * 1024

EXPORT_FORMATS = {
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "pdf": ("application/pdf", ".pdf"),
    "md": ("text/markdown; charset=utf-8", ".md"),
    "html": ("text/html; charset=utf-8", ".html"),
    "dbc": ("application/zip", ".zip"),
    "eds": ("application/zip", ".zip"),
    "c": ("application/zip", ".zip"),
    "py": ("application/zip", ".zip"),
}


class OpsBody(BaseModel):
    ops: list[dict[str, Any]]


class TextBody(BaseModel):
    text: str
    live: bool = False                 # применение по ходу ввода (см. EditorSession.set_text)


class SaveBody(BaseModel):
    force: bool = False


class GitDiffBody(BaseModel):
    rev: str = "HEAD"


class GitCommitBody(BaseModel):
    message: str
    tag: str = ""                 # поставить тег на новый коммит


class GitTagBody(BaseModel):
    name: str
    message: str = ""             # непустое — аннотированный тег


class GitReleaseBody(BaseModel):
    version: str
    changes: list[str] = []


class GhCreateBody(BaseModel):
    name: str                     # «repo» или «owner/repo»
    private: bool = True
    description: str = ""


class OpenBody(BaseModel):
    path: str
    force: bool = False           # открыть, даже если есть несохранённые правки


class NewBody(BaseModel):
    path: str
    template: str = "canopen"
    title: str = ""
    language: str = "en"          # язык документов новой карты
    force: bool = False
    overwrite: bool = False


class ExampleBody(BaseModel):
    name: str
    path: str
    force: bool = False
    overwrite: bool = False


class SaveAsBody(BaseModel):
    path: str
    overwrite: bool = False


class CloseBody(BaseModel):
    force: bool = False


class UserBody(BaseModel):
    name: str = ""
    github: str | None = None


class ActivateBody(BaseModel):
    token: str
    path: str | None = None       # файл, который просят открыть (двойной щелчок по .yaml)


class AppError(Exception):
    """Ошибка API с машинно-читаемым кодом (для диалогов в UI)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Hub:
    """Подключённые вкладки браузера."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, message: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 — вкладка закрыта
                self.clients.discard(ws)


def _hostname(netloc: str) -> str | None:
    try:
        return urlsplit("//" + netloc).hostname
    except ValueError:
        return None


class RequestGuard:
    """Защита локального сервера от чужих страниц в браузере.

    * ``Host`` должен быть из ``allowed_hosts`` (если задан): иначе страница с домена, который
      после DNS rebinding указывает на 127.0.0.1, читала бы и меняла файлы как «свой» сайт;
    * ``Origin`` изменяющих запросов и WebSocket должен совпадать с ``Host``: чужой сайт не может
      отправить форму или открыть сокет к редактору (CSRF). Запросы без ``Origin`` (curl,
      повторный запуск mapcan) пропускаются.
    """

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    def __init__(self, app, allowed_hosts: Collection[str] | None = None):
        self.app = app
        self.allowed = {h.strip("[]").lower() for h in allowed_hosts} if allowed_hosts else None

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            host = headers.get("host", "")
            if self.allowed is not None and _hostname(host) not in self.allowed:
                return await self._reject(scope, receive, send, _("недопустимый заголовок Host"))
            origin = headers.get("origin")
            unsafe = scope["type"] == "websocket" or scope["method"] not in self.SAFE_METHODS
            if unsafe and origin is not None and urlsplit(origin).netloc.lower() != host.lower():
                return await self._reject(scope, receive, send, _("запрос с чужой страницы отклонён"))
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(scope, receive, send, message: str) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await JSONResponse({"detail": message, "code": "forbidden"}, status_code=403)(scope, receive, send)


class Workspace:
    """Открытая карта (может отсутствовать), рабочая папка, настройки пользователя."""

    def __init__(self, session: EditorSession | None, cwd: Path, readonly: bool):
        self.session = session
        self.cwd = cwd
        self.readonly = readonly
        self.generation = 1 if session else 0
        self.config = UserConfig.load()
        if session:
            self.remember(session.path)

    def require(self) -> EditorSession:
        if self.session is None:
            raise AppError(409, "no-session", _("карта не открыта"))
        return self.session

    def resolve(self, raw: str) -> Path:
        p = Path(raw.strip().strip('"')).expanduser()
        return (p if p.is_absolute() else self.cwd / p).resolve()

    def check_unsaved(self, force: bool) -> None:
        s = self.session
        if s is not None and not force and s.text != s.saved_text:
            raise AppError(409, "unsaved", _("в «{name}» есть несохранённые изменения", name=s.path.name))

    def remember(self, path: Path) -> None:
        self.config.touch_recent(path)
        with contextlib.suppress(OSError):
            self.config.save()

    def open(self, path: Path) -> EditorSession:
        self.session = EditorSession(path, readonly=self.readonly)
        self.generation += 1
        self.remember(path)
        return self.session

    def meta(self) -> dict:
        s = self.session
        recent = []
        for r in self.config.recent:
            p = Path(r)
            recent.append({"path": r, "name": p.name, "dir": str(p.parent), "exists": p.is_file()})
        return {
            "version": __version__,
            "user": self.config.user.to_dict(),
            "recent": recent,
            "cwd": str(self.cwd),
            "home": str(Path.home()),
            "readonly": self.readonly,
            "templates": template_labels(),
            "examples": list_examples(),
            "open": s is not None,
            "file": str(s.path) if s else None,
            "session_id": self.generation,
        }


def list_dir(d: Path) -> dict:
    """Содержимое папки для диалога файлов: подпапки и YAML-файлы."""
    if not d.is_dir():
        raise AppError(404, "not-found", _("папка не найдена: {path}", path=d))
    try:
        items = list(d.iterdir())
    except PermissionError as e:
        raise AppError(403, "denied", _("нет доступа к папке: {path}", path=d)) from e
    entries = []
    for it in items:
        if it.name.startswith(".") or it.name in ("node_modules", "__pycache__"):
            continue
        try:
            is_dir = it.is_dir()
            if not is_dir and it.suffix.lower() not in (".yaml", ".yml"):
                continue
            st = it.stat()
        except OSError:
            continue
        entries.append({"name": it.name, "path": str(it), "is_dir": is_dir,
                        "size": None if is_dir else st.st_size, "mtime": st.st_mtime})
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    drives = [f"{c}:\\" for c in string.ascii_uppercase if Path(f"{c}:\\").exists()] if os.name == "nt" else []
    parent = d.parent if d.parent != d else None
    return {"dir": str(d), "parent": str(parent) if parent else None, "entries": entries,
            "drives": drives, "sep": os.sep}


def _zip(paths: list[Path], root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(p, p.relative_to(root).as_posix())
    return buf.getvalue()


def build_export(cmap: MapCan, fmt: str, stem: str, lang: str | None, template: str | None = None) -> bytes:
    from ..codegen.c import generate_c
    from ..codegen.py import generate_py
    from ..export.dbc import export_dbc
    from ..export.pdf import export_pdf
    from ..export.text import render
    from ..export.xlsx import export_xlsx

    if fmt == "md":
        return render(cmap, "md", lang=lang).encode("utf-8")
    if fmt == "html":
        return render(cmap, "html", lang=lang).encode("utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if fmt == "xlsx":
            return export_xlsx(cmap, root / f"{stem}.xlsx", lang=lang).read_bytes()
        if fmt == "pdf":
            return export_pdf(cmap, root / f"{stem}.pdf", template=template, lang=lang).read_bytes()
        if fmt == "dbc":
            return _zip(export_dbc(cmap, root), root)
        if fmt == "eds":
            from ..export.eds import export_eds

            return _zip(export_eds(cmap, root), root)
        if fmt == "c":
            return _zip(generate_c(cmap, root), root)
        if fmt == "py":
            return _zip(generate_py(cmap, root), root)
    raise ValueError(fmt)


# В оконной сборке под Windows каждый запуск консольного git открывает окно терминала.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_tool(cmd: list[str], cwd: Path, timeout: float, *, input: str | None = None,
              env: dict[str, str] | None = None) -> str:
    # Запрос пароля в терминале повесил бы сервер: без окна его некому ввести.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1",
           **(env or {})}
    try:
        r = subprocess.run(cmd, cwd=cwd, input=input, stdin=None if input is not None else subprocess.DEVNULL,
                           capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                           creationflags=_NO_WINDOW, env=env)
    except subprocess.TimeoutExpired as e:
        raise HTTPException(504, _("{tool} не ответил за {seconds} с", tool=cmd[0], seconds=int(timeout))) from e
    if r.returncode != 0:
        raise HTTPException(400, (r.stderr.strip() or r.stdout.strip()) or _("ошибка {tool}", tool=cmd[0]))
    return r.stdout


def _git(args: list[str], cwd: Path, timeout: float = 15, **kw: Any) -> str:
    return _run_tool(["git", *args], cwd, timeout, **kw)


def _git_ok(args: list[str], cwd: Path) -> bool:
    """Команда-проверка git: True при коде возврата 0."""
    try:
        _git(args, cwd)
    except HTTPException:
        return False
    return True


def _gh(args: list[str], cwd: Path, timeout: float = 15) -> str:
    return _run_tool(["gh", *args], cwd, timeout)


def _git_remote(args: list[str], cwd: Path) -> str:
    """push/pull/fetch: для github.com — учётные данные GitHub CLI (gh), если он установлен."""
    auth: list[str] = []
    if shutil.which("gh"):
        auth = ["-c", "credential.https://github.com.helper=",
                "-c", "credential.https://github.com.helper=!gh auth git-credential"]
    # Сообщения git — по-английски, чтобы распознать типичные ошибки pull/push
    return _git([*auth, *args], cwd, timeout=120, env={"LC_ALL": "C", "LANGUAGE": "C"})


# Имя репозитория GitHub: «repo» или «owner/repo»
_GH_REPO = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9-]*/)?[A-Za-z0-9._][A-Za-z0-9._-]*$")


def _check_rev(rev: str) -> str:
    """Ревизия из запроса: не пустая и не начинается с «-» (иначе git примет её за ключ)."""
    rev = rev.strip()
    if not rev or rev.startswith("-") or any(c.isspace() for c in rev):
        raise AppError(400, "git-rev", _("недопустимая ревизия: {rev}", rev=rev))
    return rev


def _web_url(remote_url: str) -> str | None:
    """Адрес репозитория для браузера: из https://… или git@host:owner/repo.git; иначе None."""
    u = remote_url.strip()
    m = re.match(r"^(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?/?$", u)
    if m:
        return f"https://{m[1]}/{m[2]}"
    parts = urlsplit(u)
    if parts.scheme in ("http", "https") and parts.hostname:
        port = f":{parts.port}" if parts.port else ""       # логин и токен из адреса не показываем
        return f"{parts.scheme}://{parts.hostname}{port}{parts.path.rstrip('/').removesuffix('.git')}"
    return None


def _refs_with_file(cwd: Path, name: str, refs: list[str]) -> list[str]:
    """Ссылки (теги, ветки), в которых есть файл карты, — одним запуском git cat-file."""
    if not refs:
        return []
    out = _git(["cat-file", "--batch-check"], cwd, input="".join(f"{r}:./{name}\n" for r in refs))
    return [r for r, line in zip(refs, out.splitlines(), strict=True) if not line.endswith(" missing")]


def _git_status(path: Path, extra: Collection[str] = ()) -> dict:
    """Ветка, расхождение с upstream и состояние в git файла карты и ``extra`` (логотипа)."""
    cwd = path.parent
    try:
        _git(["rev-parse", "--git-dir"], cwd)
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "reason": "no-git"}
    except HTTPException:
        return {"available": False, "reason": "no-repo"}
    out = _git(["status", "--porcelain=v2", "--branch", "--untracked-files=all", "--", path.name, *extra], cwd)
    st: dict[str, Any] = {"available": True, "branch": None, "upstream": None, "ahead": 0, "behind": 0,
                          "file": "clean", "last": None, "remote": None, "remote_url": None}
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            head = line.removeprefix("# branch.head ")
            st["branch"] = None if head == "(detached)" else head
        elif line.startswith("# branch.upstream "):
            st["upstream"] = line.removeprefix("# branch.upstream ")
        elif line.startswith("# branch.ab "):
            ahead, behind = line.removeprefix("# branch.ab ").split()
            st["ahead"], st["behind"] = int(ahead), -int(behind)
        elif line.startswith("? "):
            if st["file"] == "clean":
                st["file"] = "untracked"
        elif line[:2] in ("1 ", "2 ", "u "):
            st["file"] = "modified"
    if st["file"] == "clean" and _git_ok(["check-ignore", "-q", "--", path.name], cwd):
        st["file"] = "ignored"                      # не отслеживается и исключён через .gitignore
    try:
        log = _git(["log", "-1", "--format=%h%x09%s%x09%ad", "--date=short", "--", path.name], cwd)
    except HTTPException:
        log = ""                                    # в репозитории ещё нет коммитов
    parts = log.strip().split("\t")
    if len(parts) == 3:
        st["last"] = {"rev": parts[0], "subject": parts[1], "date": parts[2]}
    remotes = _git(["remote"], cwd).split()
    if remotes:
        st["remote"] = "origin" if "origin" in remotes else remotes[0]
        with contextlib.suppress(HTTPException):
            st["remote_url"] = _web_url(_git(["remote", "get-url", st["remote"]], cwd))
    return st


def _remote_error(e: HTTPException, upstream: str | None) -> Exception:
    """Понятное сообщение для типичных отказов pull/push (вывод git — на английском, см. _git_remote)."""
    text = str(e.detail)
    if "Not possible to fast-forward" in text or "diverging" in text or "divergent" in text:
        return AppError(409, "git-diverged", _(
            "ветка разошлась с {upstream}: и здесь, и на сервере есть свои коммиты. Объедините их в терминале "
            "(git pull --rebase или git merge) и повторите.", upstream=upstream or "upstream"))
    if "would be overwritten" in text or "commit your changes or stash them" in text:
        return AppError(409, "git-local-changes", _(
            "получение изменений перезапишет незакоммиченные правки: сначала закоммитьте их"))
    if "[rejected]" in text or "non-fast-forward" in text or "fetch first" in text:
        return AppError(409, "git-push-rejected", _(
            "на сервере есть коммиты, которых нет здесь: сначала получите изменения (pull)"))
    return e


def create_app(session: EditorSession | None = None, poll_interval: float = 1.0,
               cwd: Path | None = None, readonly: bool | None = None, *,
               check_updates: bool = False, instance_token: str | None = None,
               on_activate: Callable[[], None] | None = None,
               allowed_hosts: Collection[str] | None = None) -> FastAPI:
    """Приложение редактора.

    ``allowed_hosts`` — допустимые имена в заголовке ``Host`` (для сервера на localhost),
    None — любые (сервер слушает сеть);
    ``check_updates`` — отвечать на /api/update сведениями с GitHub Releases;
    ``instance_token`` — разрешить /api/instance/activate (повторный запуск mapcan
    передаёт файл уже работающему экземпляру), ``on_activate`` — вывести окно на передний план.
    """
    hub = Hub()
    lock = asyncio.Lock()
    root = cwd or (session.path.parent if session else Path.cwd())
    wsp = Workspace(session, root.resolve(),
                    readonly if readonly is not None else bool(session and session.readonly))

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async def watch() -> None:
            notified = None
            while True:
                await asyncio.sleep(poll_interval)
                s = wsp.session
                if s is None:
                    continue
                try:
                    if await run_in_threadpool(s.disk_changed):
                        mark = (str(s.path), hashlib.sha256(s.path.read_bytes()).hexdigest())
                        if mark != notified:
                            notified = mark
                            await hub.broadcast({"type": "file-changed"})
                    else:
                        notified = None
                except OSError:
                    pass

        task = asyncio.create_task(watch())
        yield
        task.cancel()

    app = FastAPI(title="mapcan editor", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", redoc_url=None)
    app.state.workspace = wsp
    app.state.hub = hub
    app.add_middleware(RequestGuard, allowed_hosts=allowed_hosts)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, e: AppError):
        return JSONResponse({"detail": e.message, "code": e.code}, status_code=e.status)

    @app.exception_handler(OpError)
    async def _op_error(_: Request, e: OpError):
        return JSONResponse({"detail": str(e), "code": "op"}, status_code=400)

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, e: ConflictError):
        return JSONResponse({"detail": str(e), "code": "conflict"}, status_code=409)

    @app.exception_handler(ReadOnlyError)
    async def _readonly(_: Request, e: ReadOnlyError):
        return JSONResponse({"detail": str(e), "code": "readonly"}, status_code=403)

    def state() -> dict:
        st = wsp.require().state()
        st["session_id"] = wsp.generation
        return st

    async def changed() -> dict:
        st = state()
        await hub.broadcast({"type": "state", "version": st["version"], "session_id": wsp.generation})
        return st

    async def session_changed() -> dict:
        await hub.broadcast({"type": "session", "session_id": wsp.generation})
        return {"meta": wsp.meta(), "state": state() if wsp.session else None}

    def writable() -> None:
        if wsp.readonly:
            raise AppError(403, "readonly", _("редактор запущен в режиме только для чтения"))

    # ---------------------------------------------------------------- метаданные, профиль

    @app.get("/api/meta")
    async def get_meta() -> dict:
        return wsp.meta()

    @app.get("/api/update")
    async def get_update() -> dict:
        if not check_updates:
            return {"current": __version__, "latest": None, "newer": False,
                    "url": updates.RELEASES_URL, "installer": None}
        return await run_in_threadpool(updates.check)

    @app.post("/api/instance/activate")
    async def activate(body: ActivateBody) -> dict:
        if not instance_token or body.token != instance_token:
            raise AppError(403, "token", _("неверный токен экземпляра"))
        if on_activate is not None:
            await run_in_threadpool(on_activate)
        if body.path:
            path = wsp.resolve(body.path)
            s = wsp.session
            async with lock:
                if s is not None and s.text != s.saved_text:
                    # Есть несохранённые правки — открывает вкладка, спросив пользователя.
                    await hub.broadcast({"type": "open-request", "path": str(path)})
                    return {"ok": True}
                if path.is_file() and (s is None or s.path != path):
                    try:
                        wsp.open(path)
                    except (OSError, UnicodeDecodeError) as e:
                        raise AppError(400, "read",
                                       _("не удалось прочитать {name}: {error}", name=path.name, error=e)) from e
                    await session_changed()
        return {"ok": True}

    @app.get("/api/user")
    async def get_user() -> dict:
        return wsp.config.user.to_dict()

    @app.put("/api/user")
    async def put_user(body: UserBody) -> dict:
        try:
            gh = normalize_github(body.github)
        except ValueError as e:
            raise AppError(400, "github", str(e)) from e
        wsp.config.user.name = body.name.strip()
        wsp.config.user.github = gh
        try:
            wsp.config.save()
        except OSError as e:
            raise AppError(500, "config", _("не удалось сохранить настройки: {error}", error=e)) from e
        return wsp.config.user.to_dict()

    # ---------------------------------------------------------------- файлы

    def yaml_path(raw: str) -> Path:
        path = wsp.resolve(raw)
        if path.suffix.lower() not in (".yaml", ".yml"):
            path = path.with_name(path.name + ".yaml")
        return path

    @app.get("/api/fs/list")
    async def fs_list(dir: str = "") -> dict:
        return list_dir(wsp.resolve(dir) if dir else wsp.cwd)

    @app.post("/api/file/open")
    async def file_open(body: OpenBody) -> dict:
        async with lock:
            path = wsp.resolve(body.path)
            if not path.is_file():
                raise AppError(404, "not-found", _("файл не найден: {path}", path=path))
            wsp.check_unsaved(body.force)
            try:
                wsp.open(path)
            except (OSError, UnicodeDecodeError) as e:
                raise AppError(400, "read",
                               _("не удалось прочитать {name}: {error}", name=path.name, error=e)) from e
            return await session_changed()

    async def create_file(raw_path: str, force: bool, overwrite: bool, make_text: Callable[[Path], str],
                          extra: dict[str, str] | None = None) -> dict:
        """Создать карту и открыть её; ``extra`` — файлы рядом с ней (путь относительно карты → текст)."""
        writable()
        async with lock:
            path = yaml_path(raw_path)
            others = {(path.parent / name).resolve(): text for name, text in (extra or {}).items()}
            for target in [path, *others]:
                if target.exists() and not overwrite:
                    raise AppError(409, "exists", _("файл уже существует: {path}", path=target))
            wsp.check_unsaved(force)
            try:
                text = make_text(path)
            except ValueError as e:
                raise AppError(400, "template", str(e)) from e
            try:
                for target, other in others.items():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(other, encoding="utf-8", newline="\n")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
            except OSError as e:
                raise AppError(400, "write", _("не удалось создать {path}: {error}", path=path, error=e)) from e
            wsp.open(path)
            return await session_changed()

    @app.post("/api/file/new")
    async def file_new(body: NewBody) -> dict:
        user = wsp.config.user
        return await create_file(body.path, body.force, body.overwrite, lambda path: new_map_text(
            body.template, body.title or path.stem, user.name, user.github, lang=body.language))

    @app.post("/api/file/example")
    async def file_example(body: ExampleBody) -> dict:
        try:
            included = example_includes(body.name)
        except ValueError as e:
            raise AppError(400, "template", str(e)) from e
        return await create_file(body.path, body.force, body.overwrite, lambda _path: example_text(body.name),
                                 included)

    @app.post("/api/file/save_as")
    async def file_save_as(body: SaveAsBody) -> dict:
        writable()
        async with lock:
            s = wsp.require()
            path = yaml_path(body.path)
            try:
                s.save_as(path, body.overwrite)
            except FileExistsError as e:
                raise AppError(409, "exists", str(e)) from e
            except OSError as e:
                raise AppError(400, "write", _("не удалось сохранить {path}: {error}", path=path, error=e)) from e
            wsp.generation += 1
            wsp.remember(path)
            return await session_changed()

    @app.post("/api/file/close")
    async def file_close(body: CloseBody) -> dict:
        async with lock:
            wsp.check_unsaved(body.force)
            wsp.session = None
            wsp.generation += 1
            return await session_changed()

    # ---------------------------------------------------------------- state & edit

    @app.get("/api/state")
    async def get_state() -> dict:
        return state()

    @app.post("/api/ops")
    async def post_ops(body: OpsBody) -> dict:
        async with lock:
            wsp.require().apply(body.ops)
            return await changed()

    @app.post("/api/text")
    async def post_text(body: TextBody) -> dict:
        async with lock:
            wsp.require().set_text(body.text, body.live)
            return await changed()

    @app.post("/api/check")
    async def post_check(body: TextBody) -> dict:
        s = wsp.require()
        return {"diagnostics": await run_in_threadpool(s.check_text, body.text)}

    @app.post("/api/undo")
    async def post_undo() -> dict:
        async with lock:
            wsp.require().undo()
            return await changed()

    @app.post("/api/redo")
    async def post_redo() -> dict:
        async with lock:
            wsp.require().redo()
            return await changed()

    @app.post("/api/save")
    async def post_save(body: SaveBody) -> dict:
        async with lock:
            wsp.require().save(body.force)
            return await changed()

    @app.post("/api/reload")
    async def post_reload() -> dict:
        async with lock:
            wsp.require().reload()
            return await changed()

    # ---------------------------------------------------------------- export

    @app.get("/api/schema")
    async def get_schema() -> dict:
        """JSON Schema формата — для подсказок во вкладке YAML."""
        from ..schema import json_schema

        return json_schema()

    @app.get("/api/templates")
    async def get_templates() -> dict:
        from ..export.pdf import DEFAULT_TEMPLATE_NAME, PDF_TEMPLATES

        return {"pdf": [{"name": t.name, "title": _(t.title), "description": _(t.description), "lang": t.lang}
                        for t in PDF_TEMPLATES.values()],
                "default": DEFAULT_TEMPLATE_NAME}

    @app.get("/api/export/{fmt}")
    async def get_export(fmt: str, lang: str | None = None, download: bool = False,
                         template: str | None = None) -> Response:
        from ..export.pdf import DEFAULT_TEMPLATE_NAME, PDF_TEMPLATE_ALIASES, PDF_TEMPLATES

        if template is not None:
            template = PDF_TEMPLATE_ALIASES.get(template, template)
        if fmt not in EXPORT_FORMATS:
            raise HTTPException(404, _("неизвестный формат: {fmt}", fmt=fmt))
        if template is not None and template not in PDF_TEMPLATES:
            raise HTTPException(400, _("неизвестный шаблон PDF: {template}", template=template))
        if lang:
            norm = normalize_language(lang)
            if norm is None:
                raise HTTPException(400, _("неизвестный язык: {language}", language=lang))
            lang = norm
        s = wsp.require()
        cmap = s.map
        if cmap is None:
            raise HTTPException(409, _("карта содержит ошибки структуры — экспорт невозможен"))
        media, ext = EXPORT_FORMATS[fmt]
        stem = s.path.stem
        try:
            data = await run_in_threadpool(build_export, cmap, fmt, stem, lang, template)
        except Exception as e:  # noqa: BLE001 — показать причину в UI
            raise HTTPException(500, _("ошибка экспорта {fmt}: {error}", fmt=fmt, error=e)) from e
        name = f"{stem}{ext}" if ext != ".zip" else f"{stem}-{fmt}.zip"
        if fmt == "pdf" and template and template != DEFAULT_TEMPLATE_NAME:
            name = f"{stem}-{template}.pdf"
        disp = "attachment" if download or ext == ".zip" or fmt == "xlsx" else "inline"
        return Response(data, media_type=media,
                        headers={"Content-Disposition": f'{disp}; filename="{name}"',
                                 "Cache-Control": "no-store"})

    # ---------------------------------------------------------------- логотип

    def logo_file() -> Path | None:
        s = wsp.require()
        doc = (s.doc or {}).get("document") or {}
        raw = doc.get("logo") if isinstance(doc, dict) else None
        if not raw:
            return None
        p = Path(str(raw)).expanduser()
        return p if p.is_absolute() else s.path.parent / p

    @app.get("/api/logo")
    async def get_logo() -> Response:
        p = logo_file()
        if p is None or not p.is_file():
            raise AppError(404, "no-logo", _("логотип не задан или файл не найден"))
        return FileResponse(p, headers={"Cache-Control": "no-store"})

    @app.post("/api/logo")
    async def post_logo(file: UploadFile = File(...)) -> dict:
        from ..model import LOGO_FORMATS

        writable()
        ext = Path(file.filename or "").suffix.lower()
        if ext not in LOGO_FORMATS:
            raise AppError(400, "logo-format", _("поддерживаются {formats}", formats=", ".join(LOGO_FORMATS)))
        data = await file.read()
        if len(data) > LOGO_MAX_BYTES:
            raise AppError(400, "logo-size", _("файл больше {mb} МБ", mb=LOGO_MAX_BYTES // (1024 * 1024)))
        async with lock:
            s = wsp.require()
            target = s.path.parent / f"{s.path.stem}-logo{ext}"
            try:
                target.write_bytes(data)
            except OSError as e:
                raise AppError(400, "write", _("не удалось сохранить логотип: {error}", error=e)) from e
            s.apply([{"op": "set", "path": ["document", "logo"], "value": target.name}])
            return await changed()

    # ---------------------------------------------------------------- diff

    def _diff_against(old_text: str, label: str) -> dict:
        old = loads(old_text, label)
        if old.map is None:
            raise HTTPException(400, _("{label}: карта не загружается: {errors}", label=label,
                                  errors="; ".join(d.message for d in old.report.diagnostics[:3])))
        new = wsp.require().map
        if new is None:
            raise HTTPException(409, _("текущая карта содержит ошибки структуры"))
        d = diff_maps(old.map, new)
        return {**d.to_dict(), "lines": changelog_lines(d, new.lang), "label": label}

    # ---------------------------------------------------------------- git: версии карты

    def git_extra(s: EditorSession) -> list[str]:
        """Логотип карты внутри репозитория — путь для git относительно папки карты (или пусто)."""
        logo = logo_file()
        if logo is None or not logo.is_file():
            return []
        cwd = s.path.parent.resolve()
        try:
            top = Path(_git(["rev-parse", "--show-toplevel"], cwd).strip()).resolve()
        except (HTTPException, OSError, subprocess.SubprocessError):
            return []
        logo = logo.resolve()
        if not logo.is_relative_to(top):
            return []
        return [Path(os.path.relpath(logo, cwd)).as_posix()]

    async def git_state(s: EditorSession) -> dict:
        return await run_in_threadpool(lambda: _git_status(s.path, git_extra(s)))

    def git_show(s: EditorSession, rev: str) -> str:
        """Текст карты в ревизии ``rev``."""
        cwd = s.path.parent
        try:
            return _git(["show", f"{rev}:./{s.path.name}"], cwd)
        except HTTPException:
            if _git_ok(["rev-parse", "-q", "--verify", f"{rev}^{{commit}}"], cwd):
                raise AppError(404, "git-no-file", _("в ревизии {rev} нет файла карты", rev=rev)) from None
            raise

    @app.get("/api/git/revs")
    async def git_revs() -> dict:
        s = wsp.require()
        cwd = s.path.parent
        name = s.path.name
        none = {"available": False, "tags": [], "all_tags": [], "branches": [], "commits": []}
        try:
            _git(["rev-parse", "--git-dir"], cwd)
        except (OSError, subprocess.SubprocessError):
            return {**none, "reason": "no-git"}
        except HTTPException:
            return {**none, "reason": "no-repo"}
        try:
            log = _git(["log", "-n", "100", "--format=%h%x09%ad%x09%an%x09%D%x09%s", "--date=short", "--", name], cwd)
        except (HTTPException, OSError, subprocess.SubprocessError):
            return {**none, "reason": "untracked"}      # например, в репозитории ещё нет коммитов
        commits = []
        for line in log.splitlines():
            parts = line.split("\t", 4)
            if len(parts) == 5:
                rev, date, author, refs, subject = parts
                tags = [r.removeprefix("tag: ") for r in refs.split(", ") if r.startswith("tag: ")]
                commits.append({"rev": rev, "subject": subject, "date": date, "author": author, "tags": tags})
        if not commits:
            # Файл ещё не закоммичен — версий для сравнения в git нет
            return {**none, "reason": "untracked"}
        all_tags = _git(["tag", "--sort=-creatordate"], cwd).split()
        # Ветки, кроме текущей; upstream — первой (сравнить с тем, что придёт при pull)
        current = _git(["branch", "--show-current"], cwd).strip()
        try:
            upstream = _git(["rev-parse", "--abbrev-ref", "@{upstream}"], cwd).strip()
        except HTTPException:
            upstream = ""
        branches: list[str] = [upstream] if upstream else []
        for ref in _git(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"], cwd).split():
            short = ref.removeprefix("refs/heads/").removeprefix("refs/remotes/")
            if ref.endswith("/HEAD") or short in (current, upstream):
                continue
            branches.append(short)
        return {"available": True, "tags": _refs_with_file(cwd, name, all_tags), "all_tags": all_tags,
                "branches": _refs_with_file(cwd, name, branches[:50]), "commits": commits}

    @app.post("/api/diff/git")
    async def diff_git(body: GitDiffBody) -> dict:
        s = wsp.require()
        rev = _check_rev(body.rev)
        return _diff_against(await run_in_threadpool(git_show, s, rev), rev)

    @app.post("/api/git/restore")
    async def git_restore(body: GitDiffBody) -> dict:
        """Загрузить версию карты из git в редактор — как несохранённую правку (отменяется Ctrl+Z)."""
        writable()
        s = wsp.require()
        text = await run_in_threadpool(git_show, s, _check_rev(body.rev))
        async with lock:
            s.set_text(text)
            return await changed()

    # ---------------------------------------------------------------- git: коммит, тег, push/pull

    def git_session() -> EditorSession:
        """Карта для операций git: редактор не только для чтения, правки сохранены."""
        writable()
        s = wsp.require()
        if s.text != s.saved_text:
            raise AppError(409, "unsaved", _("сначала сохраните карту"))
        return s

    def git_tag_name(raw: str) -> str:
        name = raw.strip()
        if not name or name.startswith("-"):
            raise AppError(400, "git-tag", _("недопустимое имя тега: {name}", name=name))
        cwd = wsp.require().path.parent
        try:
            _git(["check-ref-format", f"refs/tags/{name}"], cwd)
        except HTTPException as e:
            raise AppError(400, "git-tag", _("недопустимое имя тега: {name}", name=name)) from e
        if _git_ok(["rev-parse", "-q", "--verify", f"refs/tags/{name}"], cwd):
            raise AppError(409, "git-tag-exists", _("тег {name} уже существует", name=name))
        return name

    def git_author(args: list[str], cwd: Path, timeout: float = 60) -> str:
        """Команда, которой нужен автор (коммит, аннотированный тег).

        Если в git не заданы user.name/user.email, берём их из профиля: имя и адрес
        <логин>@users.noreply.github.com. Тайм-аут больше обычного — у коммита бывают хуки.
        """
        user = wsp.config.user
        ident: list[str] = []
        if user.name.strip() and not _git_ok(["config", "user.name"], cwd):
            ident += ["-c", f"user.name={user.name.strip()}"]
        if user.github and not _git_ok(["config", "user.email"], cwd):
            ident += ["-c", f"user.email={user.github}@users.noreply.github.com"]
        try:
            return _git([*ident, *args], cwd, timeout)
        except HTTPException as e:
            if "user.email" in str(e.detail) or "user.name" in str(e.detail):
                raise AppError(400, "git-identity", _(
                    "git не знает автора коммита: укажите имя и GitHub в профиле mapcan "
                    "или выполните git config --global user.name / user.email")) from e
            raise

    def make_tag(cwd: Path, name: str, message: str) -> None:
        # Всегда аннотированный: push --follow-tags отправляет только такие
        git_author(["tag", "-a", name, "-m", message.strip() or name], cwd)

    @app.get("/api/git/status")
    async def git_status() -> dict:
        s = wsp.require()
        try:
            return await git_state(s)
        except HTTPException as e:
            return {"available": False, "reason": "error", "error": e.detail}

    @app.post("/api/git/init")
    async def git_init() -> dict:
        writable()
        s = wsp.require()
        if (await git_state(s))["available"]:
            raise AppError(409, "git-exists", _("папка уже в репозитории git"))
        _git(["init"], s.path.parent)
        return await git_state(s)

    @app.post("/api/git/commit")
    async def git_commit(body: GitCommitBody) -> dict:
        s = git_session()
        cwd = s.path.parent
        message = body.message.strip()
        if not message:
            raise AppError(400, "git-message", _("укажите описание коммита"))
        tag = git_tag_name(body.tag) if body.tag.strip() else ""
        st = await git_state(s)
        if st.get("file") == "ignored":
            raise AppError(409, "git-ignored", _("файл карты исключён через .gitignore — уберите его оттуда"))
        # Коммитим только карту и её логотип, не трогая остальные изменения в репозитории
        files = [s.path.name, *await run_in_threadpool(git_extra, s)]
        _git(["add", "--", *files], cwd)
        if not _git(["diff", "--cached", "--name-only", "--", *files], cwd).strip():
            raise AppError(400, "git-nothing", _("нет изменений для коммита"))
        await run_in_threadpool(git_author, ["commit", "-m", message, "--", *files], cwd)
        if tag:
            make_tag(cwd, tag, message)
        return await git_state(s)

    @app.post("/api/git/tag")
    async def git_tag(body: GitTagBody) -> dict:
        s = git_session()
        make_tag(s.path.parent, git_tag_name(body.name), body.message)
        return await git_state(s)

    # ---------------------------------------------------------------- git: выпуск версии

    def release_base(s: EditorSession) -> str | None:
        """С чем сравнивать выпуск: последний тег ветки с файлом карты, иначе последний коммит; None —
        карта ещё не в git."""
        cwd = s.path.parent
        try:
            tag = _git(["describe", "--tags", "--abbrev=0", "HEAD"], cwd).strip()
        except HTTPException:
            tag = ""
        for rev in (tag, "HEAD"):
            if rev and _git_ok(["cat-file", "-e", f"{rev}:./{s.path.name}"], cwd):
                return rev
        return None

    @app.get("/api/git/release")
    async def git_release_draft() -> dict:
        """Черновик выпуска: следующая версия, изменения с прошлого выпуска (тега) или коммита, тег."""
        s = wsp.require()
        if s.map is None:
            raise AppError(409, "map", _("текущая карта содержит ошибки структуры"))
        st = await git_state(s)
        if not st.get("available"):
            raise AppError(409, "git-unavailable", _("папка карты не в репозитории git"))
        cwd = s.path.parent
        base = await run_in_threadpool(release_base, s)
        old = loads(await run_in_threadpool(git_show, s, base), base).map if base else None

        def tagged(v: str) -> bool:
            return _git_ok(["rev-parse", "-q", "--verify", f"refs/tags/v{v}"], cwd)

        return {**await run_in_threadpool(release_draft, s.map, old, tagged), "base": base}

    @app.post("/api/git/release")
    async def git_release(body: GitReleaseBody) -> dict:
        """Выпуск версии одним действием: запись в истории изменений, версия и дата документа, сохранение,
        коммит карты и аннотированный тег v<версия>."""
        import datetime

        writable()
        s = wsp.require()
        version = body.version.strip()
        if not version:
            raise AppError(400, "version", _("укажите версию"))
        tag = git_tag_name(f"v{version}")
        st = await git_state(s)
        if not st.get("available"):
            raise AppError(409, "git-unavailable", _("папка карты не в репозитории git"))
        if st.get("file") == "ignored":
            raise AppError(409, "git-ignored", _("файл карты исключён через .gitignore — уберите его оттуда"))
        changes = [c.strip() for c in body.changes if c.strip()]
        today = datetime.date.today().isoformat()
        entry: dict[str, Any] = {"version": version, "date": today}
        user = wsp.config.user
        if user.name.strip():
            entry["author"] = user.name.strip()
        if user.github:
            entry["github"] = user.github
        entry["changes"] = changes
        history = s.map.document.history if s.map is not None else []
        # Запись этой версии уже есть (добавлена раньше) — вторую не добавляем
        recorded = bool(history) and history[0].version == version
        ops: list[dict] = [] if recorded else [
            {"op": "insert", "path": ["document", "history"], "index": 0, "value": entry}]
        async with lock:
            s.apply([*ops, {"op": "set", "path": ["document", "version"], "value": version},
                     {"op": "set", "path": ["document", "date"], "value": today}])
            s.save()
            await changed()
        cwd = s.path.parent
        message = release_message(version, changes)
        files = [s.path.name, *await run_in_threadpool(git_extra, s)]
        _git(["add", "--", *files], cwd)
        await run_in_threadpool(git_author, ["commit", "-m", message, "--", *files], cwd)
        make_tag(cwd, tag, message)
        return {"git": await git_state(s), "tag": tag}

    @app.post("/api/git/fetch")
    async def git_fetch() -> dict:
        """Узнать, что нового на сервере (для счётчика «не получено»), ничего не меняя в рабочей копии."""
        writable()
        s = wsp.require()
        if (await git_state(s)).get("remote"):
            await run_in_threadpool(_git_remote, ["fetch", "--quiet"], s.path.parent)
        return await git_state(s)

    @app.post("/api/git/push")
    async def git_push() -> dict:
        s = git_session()
        st = await git_state(s)
        if not st["available"]:
            raise AppError(409, "no-repo", _("папка карты не в репозитории git"))
        if not st["remote"]:
            raise AppError(409, "no-remote", _("у репозитория нет удалённого репозитория (remote)"))
        if not st["branch"]:
            raise AppError(409, "git-detached",
                           _("HEAD не на ветке: переключитесь на ветку, чтобы отправить изменения"))
        if st["upstream"]:
            args = ["push", "--follow-tags"]
        else:
            # Первая отправка ветки: заодно запоминаем upstream
            args = ["push", "--follow-tags", "-u", st["remote"], st["branch"]]
        try:
            await run_in_threadpool(_git_remote, args, s.path.parent)
        except HTTPException as e:
            raise _remote_error(e, st["upstream"]) from e
        return await git_state(s)

    @app.post("/api/git/pull")
    async def git_pull() -> dict:
        s = git_session()
        st = await git_state(s)
        async with lock:
            try:
                await run_in_threadpool(_git_remote, ["pull", "--ff-only"], s.path.parent)
            except HTTPException as e:
                raise _remote_error(e, st.get("upstream")) from e
            if s.disk_changed():
                s.reload()
                await changed()
        return await git_state(s)

    # ---------------------------------------------------------------- GitHub CLI (gh)

    @app.get("/api/gh/status")
    async def gh_status() -> dict:
        """Установлен ли gh и под каким пользователем он вошёл в GitHub."""
        s = wsp.require()
        if not shutil.which("gh"):
            return {"installed": False, "user": None}
        try:
            user = (await run_in_threadpool(_gh, ["api", "user", "--jq", ".login"], s.path.parent)).strip()
        except HTTPException:
            user = ""                                   # не выполнен gh auth login
        return {"installed": True, "user": user or None}

    @app.post("/api/gh/create")
    async def gh_create(body: GhCreateBody) -> dict:
        """Создать репозиторий на GitHub, добавить его как origin и отправить коммиты."""
        s = git_session()
        name = body.name.strip()
        if not _GH_REPO.match(name):
            raise AppError(400, "gh-name", _("недопустимое имя репозитория: {name}", name=name))
        if not shutil.which("gh"):
            raise AppError(400, "no-gh", _("GitHub CLI (gh) не установлен"))
        st = await git_state(s)
        if not st["available"]:
            raise AppError(409, "no-repo", _("папка карты не в репозитории git"))
        if st["remote"]:
            raise AppError(409, "gh-remote", _("у репозитория уже есть remote «{remote}»", remote=st["remote"]))
        if not st["last"]:
            raise AppError(409, "gh-empty", _("сначала закоммитьте карту"))
        top = _git(["rev-parse", "--show-toplevel"], s.path.parent).strip()
        args = ["repo", "create", name, "--private" if body.private else "--public",
                "--source", top, "--remote", "origin", "--push"]
        if body.description.strip():
            args += ["--description", body.description.strip()]
        out = await run_in_threadpool(_gh, args, Path(top), 120)
        st = await git_state(s)
        url = next((w for w in out.split() if w.startswith("https://")), None)
        return {**st, "url": url}

    @app.post("/api/diff/upload")
    async def diff_upload(file: UploadFile = File(...)) -> dict:
        raw = await file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise HTTPException(400, _("файл не в UTF-8")) from e
        return _diff_against(text, file.filename or "upload.yaml")

    # ---------------------------------------------------------------- websocket

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        hub.clients.add(ws)
        try:
            s = wsp.session
            await ws.send_json({"type": "hello", "version": s.version if s else 0, "app": __version__,
                                "session_id": wsp.generation})
            while True:
                await ws.receive_text()        # клиент ничего не шлёт; ждём закрытия
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(ws)

    # ---------------------------------------------------------------- static

    if (STATIC_DIR / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets", check_dir=False), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            candidate = (STATIC_DIR / full_path).resolve()
            if full_path and candidate.is_file() and STATIC_DIR in candidate.parents:
                return FileResponse(candidate)
            # index.html ссылается на бандл с хешем в имени: без no-cache браузер после
            # обновления mapcan может показать закэшированный интерфейс старой версии
            return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
    else:
        @app.get("/", include_in_schema=False)
        async def no_ui():
            return HTMLResponse("<h1>mapcan</h1><p>" + _(
                "Интерфейс не собран: выполните <code>npm run build</code> в каталоге <code>web/</code>. "
                "API доступно на <a href='/api/docs'>/api/docs</a>.") + "</p>")

    return app
