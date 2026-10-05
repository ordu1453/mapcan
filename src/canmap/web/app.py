"""FastAPI-приложение веб-редактора (`canmap serve`)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..diff import changelog_lines, diff_maps
from ..loader import loads
from ..model import CanMap
from .session import ConflictError, EditorSession, ReadOnlyError
from .yamlops import OpError

STATIC_DIR = Path(__file__).resolve().parent / "static"

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


def _zip(paths: list[Path], root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(p, p.relative_to(root).as_posix())
    return buf.getvalue()


def build_export(cmap: CanMap, fmt: str, stem: str, lang: str | None) -> bytes:
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
            return export_pdf(cmap, root / f"{stem}.pdf", lang=lang).read_bytes()
        if fmt == "dbc":
            return _zip(export_dbc(cmap, root), root)
        if fmt == "c":
            return _zip(generate_c(cmap, root), root)
        if fmt == "py":
            return _zip(generate_py(cmap, root), root)
    raise ValueError(fmt)


def _git(args: list[str], cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=15)
    if r.returncode != 0:
        raise HTTPException(400, r.stderr.strip() or "ошибка git")
    return r.stdout


def create_app(session: EditorSession, poll_interval: float = 1.0) -> FastAPI:
    hub = Hub()
    lock = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async def watch() -> None:
            notified = None
            while True:
                await asyncio.sleep(poll_interval)
                try:
                    changed = await run_in_threadpool(session.disk_changed)
                    if changed:
                        mark = hashlib.sha256(session.path.read_bytes()).hexdigest()
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

    app = FastAPI(title="canmap editor", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
    app.state.session = session
    app.state.hub = hub

    @app.exception_handler(OpError)
    async def _op_error(_: Request, e: OpError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, e: ConflictError):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(ReadOnlyError)
    async def _readonly(_: Request, e: ReadOnlyError):
        return JSONResponse({"detail": str(e)}, status_code=403)

    async def changed() -> dict:
        state = session.state()
        await hub.broadcast({"type": "state", "version": state["version"]})
        return state

    # ---------------------------------------------------------------- state & edit

    @app.get("/api/state")
    async def get_state() -> dict:
        return session.state()

    @app.post("/api/ops")
    async def post_ops(body: OpsBody) -> dict:
        async with lock:
            session.apply(body.ops)
            return await changed()

    @app.post("/api/text")
    async def post_text(body: TextBody) -> dict:
        async with lock:
            session.set_text(body.text)
            return await changed()

    @app.post("/api/undo")
    async def post_undo() -> dict:
        async with lock:
            session.undo()
            return await changed()

    @app.post("/api/redo")
    async def post_redo() -> dict:
        async with lock:
            session.redo()
            return await changed()

    @app.post("/api/save")
    async def post_save(body: SaveBody) -> dict:
        async with lock:
            session.save(body.force)
            return await changed()

    @app.post("/api/reload")
    async def post_reload() -> dict:
        async with lock:
            session.reload()
            return await changed()

    # ---------------------------------------------------------------- export

    @app.get("/api/export/{fmt}")
    async def get_export(fmt: str, lang: str | None = None, download: bool = False) -> Response:
        if fmt not in EXPORT_FORMATS:
            raise HTTPException(404, f"неизвестный формат: {fmt}")
        cmap = session.map
        if cmap is None:
            raise HTTPException(409, "карта содержит ошибки структуры — экспорт невозможен")
        media, ext = EXPORT_FORMATS[fmt]
        stem = session.path.stem
        try:
            data = await run_in_threadpool(build_export, cmap, fmt, stem, lang)
        except Exception as e:  # noqa: BLE001 — показать причину в UI
            raise HTTPException(500, f"ошибка экспорта {fmt}: {e}") from e
        name = f"{stem}{ext}" if ext != ".zip" else f"{stem}-{fmt}.zip"
        disp = "attachment" if download or ext == ".zip" or fmt == "xlsx" else "inline"
        return Response(data, media_type=media,
                        headers={"Content-Disposition": f'{disp}; filename="{name}"',
                                 "Cache-Control": "no-store"})

    # ---------------------------------------------------------------- diff

    def _diff_against(old_text: str, label: str) -> dict:
        old = loads(old_text, label)
        if old.map is None:
            raise HTTPException(400, f"{label}: карта не загружается: "
                                + "; ".join(d.message for d in old.report.diagnostics[:3]))
        new = session.map
        if new is None:
            raise HTTPException(409, "текущая карта содержит ошибки структуры")
        d = diff_maps(old.map, new)
        return {**d.to_dict(), "lines": changelog_lines(d, new.lang), "label": label}

    @app.get("/api/git/revs")
    async def git_revs() -> dict:
        cwd = session.path.parent
        try:
            tags = _git(["tag", "--sort=-creatordate"], cwd).split()
            log = _git(["log", "-n", "20", "--format=%h%x09%s%x09%ad", "--date=short", "--",
                        session.path.name], cwd)
        except (HTTPException, OSError, subprocess.SubprocessError):
            return {"available": False, "tags": [], "commits": []}
        commits = []
        for line in log.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                commits.append({"rev": parts[0], "subject": parts[1], "date": parts[2]})
        return {"available": True, "tags": tags, "commits": commits}

    @app.post("/api/diff/git")
    async def diff_git(body: GitDiffBody) -> dict:
        cwd = session.path.parent
        top = Path(_git(["rev-parse", "--show-toplevel"], cwd).strip())
        rel = session.path.relative_to(top.resolve()).as_posix()
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
            await ws.send_json({"type": "hello", "version": session.version})
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
            return FileResponse(STATIC_DIR / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        async def no_ui():
            return HTMLResponse("<h1>canmap</h1><p>Интерфейс не собран: выполните <code>npm run build</code> "
                                "в каталоге <code>web/</code>. API доступно на <a href='/api/docs'>/api/docs</a>.</p>")

    return app
