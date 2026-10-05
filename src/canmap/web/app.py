"""FastAPI-приложение веб-редактора (`canmap serve`)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import os
import string
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import __version__, updates
from ..diff import changelog_lines, diff_maps
from ..loader import loads
from ..model import CanMap
from ..userconfig import UserConfig, normalize_github
from .newmap import TEMPLATES, new_map_text
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
    "c": ("application/zip", ".zip"),
    "py": ("application/zip", ".zip"),
}


class OpsBody(BaseModel):
    ops: list[dict[str, Any]]


class TextBody(BaseModel):
    text: str


class SaveBody(BaseModel):
    force: bool = False


class GitDiffBody(BaseModel):
    rev: str = "HEAD"


class OpenBody(BaseModel):
    path: str
    force: bool = False           # открыть, даже если есть несохранённые правки


class NewBody(BaseModel):
    path: str
    template: str = "canopen"
    title: str = ""
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
            raise AppError(409, "no-session", "карта не открыта")
        return self.session

    def resolve(self, raw: str) -> Path:
        p = Path(raw.strip().strip('"')).expanduser()
        return (p if p.is_absolute() else self.cwd / p).resolve()

    def check_unsaved(self, force: bool) -> None:
        s = self.session
        if s is not None and not force and s.text != s.saved_text:
            raise AppError(409, "unsaved", f"в «{s.path.name}» есть несохранённые изменения")

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
            "templates": TEMPLATES,
            "open": s is not None,
            "file": str(s.path) if s else None,
            "session_id": self.generation,
        }


def list_dir(d: Path) -> dict:
    """Содержимое папки для диалога файлов: подпапки и YAML-файлы."""
    if not d.is_dir():
        raise AppError(404, "not-found", f"папка не найдена: {d}")
    try:
        items = list(d.iterdir())
    except PermissionError as e:
        raise AppError(403, "denied", f"нет доступа к папке: {d}") from e
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


def build_export(cmap: CanMap, fmt: str, stem: str, lang: str | None, template: str | None = None) -> bytes:
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
        if fmt == "c":
            return _zip(generate_c(cmap, root), root)
        if fmt == "py":
            return _zip(generate_py(cmap, root), root)
    raise ValueError(fmt)


# В оконной сборке под Windows каждый запуск консольного git открывает окно терминала.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(args: list[str], cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, encoding="utf-8", timeout=15, creationflags=_NO_WINDOW)
    if r.returncode != 0:
        raise HTTPException(400, r.stderr.strip() or "ошибка git")
    return r.stdout


def create_app(session: EditorSession | None = None, poll_interval: float = 1.0,
               cwd: Path | None = None, readonly: bool | None = None, *,
               check_updates: bool = False, instance_token: str | None = None,
               on_activate: Callable[[], None] | None = None) -> FastAPI:
    """Приложение редактора.

    ``check_updates`` — отвечать на /api/update сведениями с GitHub Releases;
    ``instance_token`` — разрешить /api/instance/activate (повторный запуск canmap
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

    app = FastAPI(title="canmap editor", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", redoc_url=None)
    app.state.workspace = wsp
    app.state.hub = hub

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
            raise AppError(403, "readonly", "редактор запущен в режиме только для чтения")

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
            raise AppError(403, "token", "неверный токен экземпляра")
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
                        raise AppError(400, "read", f"не удалось прочитать {path.name}: {e}") from e
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
            raise AppError(500, "config", f"не удалось сохранить настройки: {e}") from e
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
                raise AppError(404, "not-found", f"файл не найден: {path}")
            wsp.check_unsaved(body.force)
            try:
                wsp.open(path)
            except (OSError, UnicodeDecodeError) as e:
                raise AppError(400, "read", f"не удалось прочитать {path.name}: {e}") from e
            return await session_changed()

    @app.post("/api/file/new")
    async def file_new(body: NewBody) -> dict:
        writable()
        async with lock:
            path = yaml_path(body.path)
            if path.exists() and not body.overwrite:
                raise AppError(409, "exists", f"файл уже существует: {path}")
            wsp.check_unsaved(body.force)
            user = wsp.config.user
            try:
                text = new_map_text(body.template, body.title or path.stem, user.name, user.github)
            except ValueError as e:
                raise AppError(400, "template", str(e)) from e
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
            except OSError as e:
                raise AppError(400, "write", f"не удалось создать {path}: {e}") from e
            wsp.open(path)
            return await session_changed()

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
                raise AppError(400, "write", f"не удалось сохранить {path}: {e}") from e
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
            wsp.require().set_text(body.text)
            return await changed()

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

    @app.get("/api/templates")
    async def get_templates() -> dict:
        from ..export.pdf import DEFAULT_TEMPLATE_NAME, PDF_TEMPLATES

        return {"pdf": [{"name": t.name, "title": t.title, "description": t.description}
                        for t in PDF_TEMPLATES.values()],
                "default": DEFAULT_TEMPLATE_NAME}

    @app.get("/api/export/{fmt}")
    async def get_export(fmt: str, lang: str | None = None, download: bool = False,
                         template: str | None = None) -> Response:
        from ..export.pdf import PDF_TEMPLATES

        if fmt not in EXPORT_FORMATS:
            raise HTTPException(404, f"неизвестный формат: {fmt}")
        if template is not None and template not in PDF_TEMPLATES:
            raise HTTPException(400, f"неизвестный шаблон PDF: {template}")
        s = wsp.require()
        cmap = s.map
        if cmap is None:
            raise HTTPException(409, "карта содержит ошибки структуры — экспорт невозможен")
        media, ext = EXPORT_FORMATS[fmt]
        stem = s.path.stem
        try:
            data = await run_in_threadpool(build_export, cmap, fmt, stem, lang, template)
        except Exception as e:  # noqa: BLE001 — показать причину в UI
            raise HTTPException(500, f"ошибка экспорта {fmt}: {e}") from e
        name = f"{stem}{ext}" if ext != ".zip" else f"{stem}-{fmt}.zip"
        if fmt == "pdf" and template and template != "canmap":
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
            raise AppError(404, "no-logo", "логотип не задан или файл не найден")
        return FileResponse(p, headers={"Cache-Control": "no-store"})

    @app.post("/api/logo")
    async def post_logo(file: UploadFile = File(...)) -> dict:
        from ..model import LOGO_FORMATS

        writable()
        ext = Path(file.filename or "").suffix.lower()
        if ext not in LOGO_FORMATS:
            raise AppError(400, "logo-format", "поддерживаются " + ", ".join(LOGO_FORMATS))
        data = await file.read()
        if len(data) > LOGO_MAX_BYTES:
            raise AppError(400, "logo-size", f"файл больше {LOGO_MAX_BYTES // (1024 * 1024)} МБ")
        async with lock:
            s = wsp.require()
            target = s.path.parent / f"{s.path.stem}-logo{ext}"
            try:
                target.write_bytes(data)
            except OSError as e:
                raise AppError(400, "write", f"не удалось сохранить логотип: {e}") from e
            s.apply([{"op": "set", "path": ["document", "logo"], "value": target.name}])
            return await changed()

    # ---------------------------------------------------------------- diff

    def _diff_against(old_text: str, label: str) -> dict:
        old = loads(old_text, label)
        if old.map is None:
            raise HTTPException(400, f"{label}: карта не загружается: "
                                + "; ".join(d.message for d in old.report.diagnostics[:3]))
        new = wsp.require().map
        if new is None:
            raise HTTPException(409, "текущая карта содержит ошибки структуры")
        d = diff_maps(old.map, new)
        return {**d.to_dict(), "lines": changelog_lines(d, new.lang), "label": label}

    @app.get("/api/git/revs")
    async def git_revs() -> dict:
        s = wsp.require()
        cwd = s.path.parent
        none = {"available": False, "tags": [], "commits": []}
        try:
            _git(["rev-parse", "--git-dir"], cwd)
        except (OSError, subprocess.SubprocessError):
            return {**none, "reason": "no-git"}
        except HTTPException:
            return {**none, "reason": "no-repo"}
        try:
            tags = _git(["tag", "--sort=-creatordate"], cwd).split()
            log = _git(["log", "-n", "20", "--format=%h%x09%s%x09%ad", "--date=short", "--",
                        s.path.name], cwd)
        except (HTTPException, OSError, subprocess.SubprocessError):
            return {**none, "reason": "untracked"}      # например, в репозитории ещё нет коммитов
        commits = []
        for line in log.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                commits.append({"rev": parts[0], "subject": parts[1], "date": parts[2]})
        if not commits:
            # Файл ещё не закоммичен — версий для сравнения в git нет
            return {**none, "reason": "untracked"}
        return {"available": True, "tags": tags, "commits": commits}

    @app.post("/api/diff/git")
    async def diff_git(body: GitDiffBody) -> dict:
        s = wsp.require()
        cwd = s.path.parent
        top = Path(_git(["rev-parse", "--show-toplevel"], cwd).strip())
        rel = s.path.relative_to(top.resolve()).as_posix()
        old_text = _git(["show", f"{body.rev}:{rel}"], cwd)
        return _diff_against(old_text, body.rev)

    @app.post("/api/diff/upload")
    async def diff_upload(file: UploadFile = File(...)) -> dict:
        raw = await file.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise HTTPException(400, "файл не в UTF-8") from e
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
            # обновления canmap может показать закэшированный интерфейс старой версии
            return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
    else:
        @app.get("/", include_in_schema=False)
        async def no_ui():
            return HTMLResponse("<h1>canmap</h1><p>Интерфейс не собран: выполните <code>npm run build</code> "
                                "в каталоге <code>web/</code>. API доступно на <a href='/api/docs'>/api/docs</a>.</p>")

    return app
