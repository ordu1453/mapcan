"""FastAPI application of the web editor (`mapcan serve`)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import html
import io
import os
import platform
import re
import shutil
import string
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Collection
from http.cookies import CookieError, SimpleCookie
from pathlib import Path, PurePath
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
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


class DeviceFileBody(BaseModel):
    bus: list[Any]                     # path of the bus: ["buses", i]
    device: dict[str, Any]
    file: str                          # the new file, relative to the map


class TextBody(BaseModel):
    text: str
    live: bool = False                 # applied while typing (see EditorSession.set_text)
    file: str | None = None            # the text of an included file (relative to the map); None: of the map


class SaveBody(BaseModel):
    force: bool = False


class GitDiffBody(BaseModel):
    rev: str = "HEAD"


class GitCommitBody(BaseModel):
    message: str
    tag: str = ""                 # put a tag on the new commit


class GitTagBody(BaseModel):
    name: str
    message: str = ""             # non-empty: an annotated tag


class GitReleaseBody(BaseModel):
    version: str
    changes: list[str] = []


class GhCreateBody(BaseModel):
    name: str                     # "repo" or "owner/repo"
    private: bool = True
    description: str = ""


class OpenBody(BaseModel):
    path: str
    force: bool = False           # open even if there are unsaved edits


class NewBody(BaseModel):
    path: str
    template: str = "canopen"
    title: str = ""
    language: str = "en"          # document language of the new map
    force: bool = False
    overwrite: bool = False


class ExampleBody(BaseModel):
    name: str
    path: str
    force: bool = False
    overwrite: bool = False


class ImportBody(BaseModel):
    source: str                   # the DBC file
    path: str = ""                # the new map; next to the DBC, with its name, by default
    language: str = "en"          # document language of the new map
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
    path: str | None = None       # the file asked to be opened (a double click on a .yaml)


class AppError(Exception):
    """API error with a machine-readable code (for the dialogs of the UI)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Hub:
    """Connected browser tabs."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, message: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 — the tab is closed
                self.clients.discard(ws)


def _hostname(netloc: str) -> str | None:
    try:
        return urlsplit("//" + netloc).hostname
    except ValueError:
        return None


class RequestGuard:
    """Protection of the local server from other pages in the browser.

    * ``Host`` must be one of ``allowed_hosts`` (if given): otherwise a page from a domain that
      points to 127.0.0.1 after DNS rebinding could read and change files as a "same" site;
    * ``Origin`` of changing requests and of WebSocket must match ``Host``: another site cannot
      post a form or open a socket to the editor (CSRF). Requests without ``Origin`` (curl,
      mapcan run again) pass.
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
                return await self._reject(scope, receive, send, _("invalid Host header"))
            origin = headers.get("origin")
            unsafe = scope["type"] == "websocket" or scope["method"] not in self.SAFE_METHODS
            if unsafe and origin is not None and urlsplit(origin).netloc.lower() != host.lower():
                return await self._reject(scope, receive, send, _("request from another site rejected"))
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(scope, receive, send, message: str) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await JSONResponse({"detail": message, "code": "forbidden"}, status_code=403)(scope, receive, send)


class TokenAuth:
    """Token authentication of a server on the network (``mapcan serve --host 0.0.0.0``), as in Jupyter.

    A request passes with the cookie ``mapcan_token`` or the header ``Authorization: Bearer <token>``.
    The address printed by ``serve`` carries ``?token=…``: a GET with the right token sets the cookie
    (HttpOnly, SameSite=Strict) and redirects to the same address without it, so the token does not stay in
    the address bar or the history.
    """

    COOKIE = "mapcan_token"

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    def _ok(self, value: str | None) -> bool:
        return value is not None and hmac.compare_digest(value.encode(), self.token.encode())

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        cookies = SimpleCookie()
        with contextlib.suppress(CookieError):
            cookies.load(headers.get("cookie", ""))
        cookie = cookies[self.COOKIE].value if self.COOKIE in cookies else None
        auth = headers.get("authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else None
        if self._ok(cookie) or self._ok(bearer):
            return await self.app(scope, receive, send)
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        if scope["type"] == "http" and scope["method"] == "GET" and self._ok((query.get("token") or [None])[0]):
            rest = urlencode([(k, v) for k, vs in query.items() if k != "token" for v in vs], doseq=True)
            target = scope.get("path", "/") + (f"?{rest}" if rest else "")
            response = RedirectResponse(target, status_code=303)
            response.set_cookie(self.COOKIE, self.token, httponly=True, samesite="strict", path="/")
            return await response(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        message = _("mapcan: open the address with the token that `mapcan serve` printed (…/?token=…)")
        if scope.get("path", "").startswith("/api/"):
            response = JSONResponse({"detail": message, "code": "auth"}, status_code=401)
        else:
            response = HTMLResponse(f"<h1>mapcan</h1><p>{html.escape(message)}</p>", status_code=401)
        await response(scope, receive, send)


class Workspace:
    """The open map (there may be none), the workspace folder, the user settings."""

    def __init__(self, session: EditorSession | None, cwd: Path, readonly: bool, mode: str = "serve"):
        self.session = session
        self.cwd = cwd
        self.readonly = readonly
        self.mode = mode
        self.generation = 1 if session else 0
        self.config = UserConfig.load()
        if session:
            self.remember(session.path)

    def require(self) -> EditorSession:
        if self.session is None:
            raise AppError(409, "no-session", _("no map is open"))
        return self.session

    def resolve(self, raw: str) -> Path:
        p = Path(raw.strip().strip('"')).expanduser()
        return (p if p.is_absolute() else self.cwd / p).resolve()

    def check_unsaved(self, force: bool) -> None:
        s = self.session
        if s is not None and not force and s.dirty:
            raise AppError(409, "unsaved", _("“{name}” has unsaved changes", name=s.path.name))

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
            # For a bug report: how mapcan runs (the app window or mapcan serve) and on what
            "mode": self.mode,
            "system": f"{platform.system()} {platform.release()}, Python {platform.python_version()}",
        }


FILE_KINDS = {"yaml": (".yaml", ".yml"), "dbc": (".dbc",)}


def list_dir(d: Path, kind: str = "yaml") -> dict:
    """Contents of a folder for the file dialog: subfolders and the files of ``kind`` (FILE_KINDS)."""
    suffixes = FILE_KINDS.get(kind, FILE_KINDS["yaml"])
    if not d.is_dir():
        raise AppError(404, "not-found", _("folder not found: {path}", path=d))
    try:
        items = list(d.iterdir())
    except PermissionError as e:
        raise AppError(403, "denied", _("access denied to folder: {path}", path=d)) from e
    entries = []
    for it in items:
        if it.name.startswith(".") or it.name in ("node_modules", "__pycache__"):
            continue
        try:
            is_dir = it.is_dir()
            if not is_dir and it.suffix.lower() not in suffixes:
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
    from ..export.text import render
    from ..extras import MissingExtra, require

    try:
        require(*{"xlsx": ("xlsx",), "pdf": ("pdf",)}.get(fmt, ()))
    except MissingExtra as e:
        raise AppError(400, "missing-extra", str(e)) from e
    if fmt == "md":
        return render(cmap, "md", lang=lang).encode("utf-8")
    if fmt == "html":
        return render(cmap, "html", lang=lang).encode("utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if fmt == "xlsx":
            from ..export.xlsx import export_xlsx

            return export_xlsx(cmap, root / f"{stem}.xlsx", lang=lang).read_bytes()
        if fmt == "pdf":
            from ..export.pdf import export_pdf

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


# In the windowed build on Windows every run of console git opens a terminal window.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_tool(cmd: list[str], cwd: Path, timeout: float, *, input: str | None = None,
              env: dict[str, str] | None = None) -> str:
    # A password prompt in a terminal would hang the server: without a window there is no one to answer it.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1",
           **(env or {})}
    try:
        r = subprocess.run(cmd, cwd=cwd, input=input, stdin=None if input is not None else subprocess.DEVNULL,
                           capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                           creationflags=_NO_WINDOW, env=env)
    except subprocess.TimeoutExpired as e:
        raise HTTPException(504, _(
            "{tool} did not respond within {seconds} s", tool=cmd[0], seconds=int(timeout))) from e
    if r.returncode != 0:
        raise HTTPException(400, (r.stderr.strip() or r.stdout.strip()) or _("{tool} error", tool=cmd[0]))
    return r.stdout


def _git(args: list[str], cwd: Path, timeout: float = 15, **kw: Any) -> str:
    return _run_tool(["git", *args], cwd, timeout, **kw)


def _git_ok(args: list[str], cwd: Path) -> bool:
    """A git check command: True on exit code 0."""
    try:
        _git(args, cwd)
    except HTTPException:
        return False
    return True


def _gh(args: list[str], cwd: Path, timeout: float = 15) -> str:
    return _run_tool(["gh", *args], cwd, timeout)


def _git_remote(args: list[str], cwd: Path) -> str:
    """push/pull/fetch: for github.com, the GitHub CLI (gh) credentials if it is installed."""
    auth: list[str] = []
    if shutil.which("gh"):
        auth = ["-c", "credential.https://github.com.helper=",
                "-c", "credential.https://github.com.helper=!gh auth git-credential"]
    # git messages in English, to recognize the typical pull/push errors
    return _git([*auth, *args], cwd, timeout=120, env={"LC_ALL": "C", "LANGUAGE": "C"})


# Name of a GitHub repository: "repo" or "owner/repo"
_GH_REPO = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9-]*/)?[A-Za-z0-9._][A-Za-z0-9._-]*$")


def _check_rev(rev: str) -> str:
    """Revision from a request: not empty and not starting with "-" (git would take it for an option)."""
    rev = rev.strip()
    if not rev or rev.startswith("-") or any(c.isspace() for c in rev):
        raise AppError(400, "git-rev", _("invalid revision: {rev}", rev=rev))
    return rev


def _web_url(remote_url: str) -> str | None:
    """Repository address for the browser: from https://… or git@host:owner/repo.git; otherwise None."""
    u = remote_url.strip()
    m = re.match(r"^(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?/?$", u)
    if m:
        return f"https://{m[1]}/{m[2]}"
    parts = urlsplit(u)
    if parts.scheme in ("http", "https") and parts.hostname:
        port = f":{parts.port}" if parts.port else ""       # the login and token of the address are not shown
        return f"{parts.scheme}://{parts.hostname}{port}{parts.path.rstrip('/').removesuffix('.git')}"
    return None


def _refs_with_file(cwd: Path, name: str, refs: list[str]) -> list[str]:
    """Refs (tags, branches) that have the map file, with one run of git cat-file."""
    if not refs:
        return []
    out = _git(["cat-file", "--batch-check"], cwd, input="".join(f"{r}:./{name}\n" for r in refs))
    return [r for r, line in zip(refs, out.splitlines(), strict=True) if not line.endswith(" missing")]


def _git_status(path: Path, extra: Collection[str] = ()) -> dict:
    """Branch, divergence from upstream and the git state of the map file and of ``extra`` (the logo)."""
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
        st["file"] = "ignored"                      # not tracked and excluded by .gitignore
    try:
        log = _git(["log", "-1", "--format=%h%x09%s%x09%ad", "--date=short", "--", path.name], cwd)
    except HTTPException:
        log = ""                                    # the repository has no commits yet
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
    """A clear message for the typical pull/push failures (git output is in English, see _git_remote)."""
    text = str(e.detail)
    if "Not possible to fast-forward" in text or "diverging" in text or "divergent" in text:
        return AppError(409, "git-diverged", _(
            "the branch has diverged from {upstream}: both this copy and the server have their own commits. Combine "
            "them in a terminal (git pull --rebase or git merge) and try again.", upstream=upstream or "upstream"))
    if "would be overwritten" in text or "commit your changes or stash them" in text:
        return AppError(409, "git-local-changes", _(
            "pulling would overwrite uncommitted changes; commit them first"))
    if "[rejected]" in text or "non-fast-forward" in text or "fetch first" in text:
        return AppError(409, "git-push-rejected", _(
            "the server has commits that are not here; pull the changes first"))
    return e


def create_app(session: EditorSession | None = None, poll_interval: float = 1.0,
               cwd: Path | None = None, readonly: bool | None = None, *,
               check_updates: bool = False, instance_token: str | None = None,
               on_activate: Callable[[], None] | None = None,
               allowed_hosts: Collection[str] | None = None, auth_token: str | None = None,
               mode: str = "serve") -> FastAPI:
    """The editor application.

    ``allowed_hosts`` are the names allowed in the ``Host`` header (for a server on localhost),
    None allows any (the server listens on the network);
    ``auth_token``: every request needs this token (see :class:`TokenAuth`), for a server on the network;
    ``check_updates``: answer /api/update with information from GitHub Releases;
    ``instance_token`` allows /api/instance/activate (mapcan run again
    passes the file to the running instance), ``on_activate`` brings the window to the front;
    ``mode``: "app" (the app window) or "serve" (for a bug report).
    """
    hub = Hub()
    lock = asyncio.Lock()
    root = cwd or (session.path.parent if session else Path.cwd())
    wsp = Workspace(session, root.resolve(),
                    readonly if readonly is not None else bool(session and session.readonly), mode)

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
    if auth_token:
        # Added last, so it runs first: nothing reaches the editor without the token
        app.add_middleware(TokenAuth, token=auth_token)

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
            raise AppError(403, "readonly", _("the editor is running in read-only mode"))

    # ---------------------------------------------------------------- metadata, profile

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
            raise AppError(403, "token", _("invalid instance token"))
        if on_activate is not None:
            await run_in_threadpool(on_activate)
        if body.path:
            path = wsp.resolve(body.path)
            s = wsp.session
            async with lock:
                if s is not None and s.dirty:
                    # There are unsaved edits: the tab opens it after asking the user.
                    await hub.broadcast({"type": "open-request", "path": str(path)})
                    return {"ok": True}
                if path.is_file() and (s is None or s.path != path):
                    try:
                        wsp.open(path)
                    except (OSError, UnicodeDecodeError) as e:
                        raise AppError(400, "read",
                                       _("could not read {name}: {error}", name=path.name, error=e)) from e
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
            raise AppError(500, "config", _("could not save settings: {error}", error=e)) from e
        return wsp.config.user.to_dict()

    # ---------------------------------------------------------------- files

    def yaml_path(raw: str) -> Path:
        path = wsp.resolve(raw)
        if path.suffix.lower() not in (".yaml", ".yml"):
            path = path.with_name(path.name + ".yaml")
        return path

    @app.get("/api/fs/list")
    async def fs_list(dir: str = "", kind: str = "yaml") -> dict:
        return list_dir(wsp.resolve(dir) if dir else wsp.cwd, kind)

    @app.post("/api/file/open")
    async def file_open(body: OpenBody) -> dict:
        async with lock:
            path = wsp.resolve(body.path)
            if not path.is_file():
                raise AppError(404, "not-found", _("file not found: {path}", path=path))
            wsp.check_unsaved(body.force)
            try:
                wsp.open(path)
            except (OSError, UnicodeDecodeError) as e:
                raise AppError(400, "read",
                               _("could not read {name}: {error}", name=path.name, error=e)) from e
            return await session_changed()

    async def create_file(raw_path: str, force: bool, overwrite: bool, make_text: Callable[[Path], str],
                          extra: dict[str, str] | None = None) -> dict:
        """Create a map and open it; ``extra`` are files next to it (path relative to the map → text)."""
        writable()
        async with lock:
            path = yaml_path(raw_path)
            others = {(path.parent / name).resolve(): text for name, text in (extra or {}).items()}
            for target in [path, *others]:
                if target.exists() and not overwrite:
                    raise AppError(409, "exists", _("file already exists: {path}", path=target))
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
                raise AppError(400, "write", _("could not create {path}: {error}", path=path, error=e)) from e
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
            included = example_includes(body.name, PurePath(body.path).name)
        except ValueError as e:
            raise AppError(400, "template", str(e)) from e
        return await create_file(body.path, body.force, body.overwrite, lambda _path: example_text(body.name),
                                 included)

    @app.post("/api/file/import_dbc")
    async def file_import_dbc(body: ImportBody) -> dict:
        from ..importers.dbc import import_dbc

        source = wsp.resolve(body.source)
        if not source.is_file():
            raise AppError(404, "not-found", _("file not found: {path}", path=source))
        warnings: list[str] = []

        def make_text(path: Path) -> str:
            try:
                text, found = import_dbc(source, path.stem, normalize_language(body.language) or "en")
            except Exception as e:  # noqa: BLE001 — cantools raises many kinds of errors on a broken DBC
                raise AppError(400, "import", _("could not import {name}: {error}", name=source.name, error=e)) from e
            warnings.extend(found)
            return text

        result = await create_file(body.path or str(source.with_suffix(".yaml")), body.force, body.overwrite,
                                   make_text)
        return {**result, "warnings": warnings}

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
                raise AppError(400, "write", _("could not save {path}: {error}", path=path, error=e)) from e
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

    @app.post("/api/device_file")
    async def post_device_file(body: DeviceFileBody) -> dict:
        async with lock:
            wsp.require().add_device_file(body.bus, body.device, body.file)
            return await changed()

    @app.post("/api/text")
    async def post_text(body: TextBody) -> dict:
        async with lock:
            await run_in_threadpool(wsp.require().set_text, body.text, body.live, body.file)
            return await changed()

    @app.post("/api/check")
    async def post_check(body: TextBody) -> dict:
        s = wsp.require()
        return {"diagnostics": await run_in_threadpool(s.check_text, body.text, body.file)}

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
        """JSON Schema of the format, for the hints of the YAML tab."""
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
            raise HTTPException(404, _("unknown format: {fmt}", fmt=fmt))
        if template is not None and template not in PDF_TEMPLATES:
            raise HTTPException(400, _("unknown PDF template: {template}", template=template))
        if lang:
            norm = normalize_language(lang)
            if norm is None:
                raise HTTPException(400, _("unknown language: {language}", language=lang))
            lang = norm
        s = wsp.require()
        cmap = s.map
        if cmap is None:
            raise HTTPException(409, _("the map has structural errors and cannot be exported"))
        media, ext = EXPORT_FORMATS[fmt]
        stem = s.path.stem
        try:
            data = await run_in_threadpool(build_export, cmap, fmt, stem, lang, template)
        except Exception as e:  # noqa: BLE001 — show the cause in the UI
            raise HTTPException(500, _("{fmt} export error: {error}", fmt=fmt, error=e)) from e
        name = f"{stem}{ext}" if ext != ".zip" else f"{stem}-{fmt}.zip"
        if fmt == "pdf" and template and template != DEFAULT_TEMPLATE_NAME:
            name = f"{stem}-{template}.pdf"
        disp = "attachment" if download or ext == ".zip" or fmt == "xlsx" else "inline"
        return Response(data, media_type=media,
                        headers={"Content-Disposition": f'{disp}; filename="{name}"',
                                 "Cache-Control": "no-store"})

    # ---------------------------------------------------------------- logo

    def logo_file() -> Path | None:
        s = wsp.require()
        doc = (s.doc or {}).get("document") or {}
        pr = doc.get("print") if isinstance(doc, dict) else None
        # A map not migrated yet has the logo under its former place, document.logo
        raw = pr.get("logo") if isinstance(pr, dict) else doc.get("logo") if isinstance(doc, dict) else None
        if not raw:
            return None
        p = Path(str(raw)).expanduser()
        return p if p.is_absolute() else s.path.parent / p

    @app.get("/api/logo")
    async def get_logo() -> Response:
        p = logo_file()
        if p is None or not p.is_file():
            raise AppError(404, "no-logo", _("no logo is set or the file was not found"))
        return FileResponse(p, headers={"Cache-Control": "no-store"})

    @app.post("/api/logo")
    async def post_logo(file: UploadFile = File(...)) -> dict:
        from ..model import LOGO_FORMATS

        writable()
        ext = Path(file.filename or "").suffix.lower()
        if ext not in LOGO_FORMATS:
            raise AppError(400, "logo-format", _("supported formats: {formats}", formats=", ".join(LOGO_FORMATS)))
        data = await file.read()
        if len(data) > LOGO_MAX_BYTES:
            raise AppError(400, "logo-size", _("the file is larger than {mb} MB", mb=LOGO_MAX_BYTES // (1024 * 1024)))
        async with lock:
            s = wsp.require()
            target = s.path.parent / f"{s.path.stem}-logo{ext}"
            try:
                target.write_bytes(data)
            except OSError as e:
                raise AppError(400, "write", _("could not save the logo: {error}", error=e)) from e
            s.apply([{"op": "set", "path": ["document", "print", "logo"], "value": target.name}])
            return await changed()

    # ---------------------------------------------------------------- diff

    def _diff_against(old_text: str, label: str) -> dict:
        old = loads(old_text, label)
        if old.map is None:
            raise HTTPException(400, _("{label}: the map failed to load: {errors}", label=label,
                                  errors="; ".join(d.message for d in old.report.diagnostics[:3])))
        new = wsp.require().map
        if new is None:
            raise HTTPException(409, _("the current map has structural errors"))
        d = diff_maps(old.map, new)
        return {**d.to_dict(), "lines": changelog_lines(d, new.lang), "label": label}

    # ---------------------------------------------------------------- git: versions of the map

    def git_extra(s: EditorSession) -> list[str]:
        """The logo and the included files of the map inside the repository: paths for git relative to the map's
        folder. A commit of the map takes them too."""
        logo = logo_file()
        files = [*s.part_paths(), *([logo] if logo is not None and logo.is_file() else [])]
        if not files:
            return []
        cwd = s.path.parent.resolve()
        try:
            top = Path(_git(["rev-parse", "--show-toplevel"], cwd).strip()).resolve()
        except (HTTPException, OSError, subprocess.SubprocessError):
            return []
        return [Path(os.path.relpath(f.resolve(), cwd)).as_posix() for f in files
                if f.resolve().is_relative_to(top)]

    async def git_state(s: EditorSession) -> dict:
        return await run_in_threadpool(lambda: _git_status(s.path, git_extra(s)))

    def git_show(s: EditorSession, rev: str) -> str:
        """Text of the map in revision ``rev``."""
        cwd = s.path.parent
        try:
            return _git(["show", f"{rev}:./{s.path.name}"], cwd)
        except HTTPException:
            if _git_ok(["rev-parse", "-q", "--verify", f"{rev}^{{commit}}"], cwd):
                raise AppError(404, "git-no-file", _(
                    "the map file does not exist in revision {rev}", rev=rev)) from None
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
            return {**none, "reason": "untracked"}      # e.g. the repository has no commits yet
        commits = []
        for line in log.splitlines():
            parts = line.split("\t", 4)
            if len(parts) == 5:
                rev, date, author, refs, subject = parts
                tags = [r.removeprefix("tag: ") for r in refs.split(", ") if r.startswith("tag: ")]
                commits.append({"rev": rev, "subject": subject, "date": date, "author": author, "tags": tags})
        if not commits:
            # The file is not committed yet: git has no versions to compare
            return {**none, "reason": "untracked"}
        all_tags = _git(["tag", "--sort=-creatordate"], cwd).split()
        # Branches other than the current one; upstream first (compare with what pull will bring)
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
        """Load a version of the map from git into the editor as an unsaved edit (undone with Ctrl+Z)."""
        writable()
        s = wsp.require()
        text = await run_in_threadpool(git_show, s, _check_rev(body.rev))
        async with lock:
            s.set_text(text)
            return await changed()

    # ---------------------------------------------------------------- git: commit, tag, push/pull

    def git_session() -> EditorSession:
        """The map for git operations: the editor is not read-only and the edits are saved."""
        writable()
        s = wsp.require()
        if s.dirty:
            raise AppError(409, "unsaved", _("save the map first"))
        return s

    def git_tag_name(raw: str) -> str:
        name = raw.strip()
        if not name or name.startswith("-"):
            raise AppError(400, "git-tag", _("invalid tag name: {name}", name=name))
        cwd = wsp.require().path.parent
        try:
            _git(["check-ref-format", f"refs/tags/{name}"], cwd)
        except HTTPException as e:
            raise AppError(400, "git-tag", _("invalid tag name: {name}", name=name)) from e
        if _git_ok(["rev-parse", "-q", "--verify", f"refs/tags/{name}"], cwd):
            raise AppError(409, "git-tag-exists", _("the tag {name} already exists", name=name))
        return name

    def git_author(args: list[str], cwd: Path, timeout: float = 60) -> str:
        """A command that needs an author (commit, annotated tag).

        If git has no user.name/user.email, they come from the profile: the name and the address
        <login>@users.noreply.github.com. The timeout is longer than usual: commits may have hooks.
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
                    "git does not know the commit author: enter your name and GitHub in the mapcan profile or run git "
                    "config --global user.name / user.email")) from e
            raise

    def make_tag(cwd: Path, name: str, message: str) -> None:
        # Always annotated: push --follow-tags sends only those
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
            raise AppError(409, "git-exists", _("the folder is already in a git repository"))
        _git(["init"], s.path.parent)
        return await git_state(s)

    @app.post("/api/git/commit")
    async def git_commit(body: GitCommitBody) -> dict:
        s = git_session()
        cwd = s.path.parent
        message = body.message.strip()
        if not message:
            raise AppError(400, "git-message", _("enter a commit message"))
        tag = git_tag_name(body.tag) if body.tag.strip() else ""
        st = await git_state(s)
        if st.get("file") == "ignored":
            raise AppError(409, "git-ignored", _("the map file is excluded by .gitignore; remove it from there"))
        # Commit only the map and its logo, leaving the other changes of the repository alone
        files = [s.path.name, *await run_in_threadpool(git_extra, s)]
        _git(["add", "--", *files], cwd)
        if not _git(["diff", "--cached", "--name-only", "--", *files], cwd).strip():
            raise AppError(400, "git-nothing", _("nothing to commit"))
        await run_in_threadpool(git_author, ["commit", "-m", message, "--", *files], cwd)
        if tag:
            make_tag(cwd, tag, message)
        return await git_state(s)

    @app.post("/api/git/tag")
    async def git_tag(body: GitTagBody) -> dict:
        s = git_session()
        make_tag(s.path.parent, git_tag_name(body.name), body.message)
        return await git_state(s)

    # ---------------------------------------------------------------- git: releasing a version

    def release_base(s: EditorSession) -> str | None:
        """What to compare a release with: the last tag of the branch with the map file, otherwise the last commit;
        None if the map is not in git yet."""
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
        """Draft of a release: the next version, the changes since the previous release (tag) or commit, the tag."""
        s = wsp.require()
        if s.map is None:
            raise AppError(409, "map", _("the current map has structural errors"))
        st = await git_state(s)
        if not st.get("available"):
            raise AppError(409, "git-unavailable", _("the map folder is not in a git repository"))
        cwd = s.path.parent
        base = await run_in_threadpool(release_base, s)
        old = loads(await run_in_threadpool(git_show, s, base), base).map if base else None

        def tagged(v: str) -> bool:
            return _git_ok(["rev-parse", "-q", "--verify", f"refs/tags/v{v}"], cwd)

        return {**await run_in_threadpool(release_draft, s.map, old, tagged), "base": base}

    @app.post("/api/git/release")
    async def git_release(body: GitReleaseBody) -> dict:
        """Release a version in one action: the revision history entry, the document's version and date, saving,
        a commit of the map and the annotated tag v<version>."""
        import datetime

        writable()
        s = wsp.require()
        version = body.version.strip()
        if not version:
            raise AppError(400, "version", _("enter a version"))
        tag = git_tag_name(f"v{version}")
        st = await git_state(s)
        if not st.get("available"):
            raise AppError(409, "git-unavailable", _("the map folder is not in a git repository"))
        if st.get("file") == "ignored":
            raise AppError(409, "git-ignored", _("the map file is excluded by .gitignore; remove it from there"))
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
        # The entry of this version is already there (added earlier): no second one
        recorded = bool(history) and history[0].version == version
        ops: list[dict] = [] if recorded else [
            {"op": "insert", "path": ["document", "history"], "index": 0, "value": entry}]
        # The document's version and date come from the entry: the ones written in the document are removed
        document = s.doc.get("document") if isinstance(s.doc, dict) else None
        ops += [{"op": "remove", "path": ["document", k]} for k in ("version", "date")
                if isinstance(document, dict) and k in document]
        async with lock:
            s.apply(ops)
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
        """Find out what is new on the server (for the "not pulled" counter) without changing the working copy."""
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
            raise AppError(409, "no-repo", _("the map folder is not in a git repository"))
        if not st["remote"]:
            raise AppError(409, "no-remote", _("the repository has no remote configured"))
        if not st["branch"]:
            raise AppError(409, "git-detached",
                           _("HEAD is detached; switch to a branch to push changes"))
        if st["upstream"]:
            args = ["push", "--follow-tags"]
        else:
            # First push of the branch: remember the upstream too
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
        """Whether gh is installed and as which user it is signed in to GitHub."""
        s = wsp.require()
        if not shutil.which("gh"):
            return {"installed": False, "user": None}
        try:
            user = (await run_in_threadpool(_gh, ["api", "user", "--jq", ".login"], s.path.parent)).strip()
        except HTTPException:
            user = ""                                   # gh auth login was not run
        return {"installed": True, "user": user or None}

    @app.post("/api/gh/create")
    async def gh_create(body: GhCreateBody) -> dict:
        """Create a repository on GitHub, add it as origin and push the commits."""
        s = git_session()
        name = body.name.strip()
        if not _GH_REPO.match(name):
            raise AppError(400, "gh-name", _("invalid repository name: {name}", name=name))
        if not shutil.which("gh"):
            raise AppError(400, "no-gh", _("GitHub CLI (gh) is not installed"))
        st = await git_state(s)
        if not st["available"]:
            raise AppError(409, "no-repo", _("the map folder is not in a git repository"))
        if st["remote"]:
            raise AppError(409, "gh-remote", _("the repository already has the remote “{remote}”", remote=st["remote"]))
        if not st["last"]:
            raise AppError(409, "gh-empty", _("commit the map first"))
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
            raise HTTPException(400, _("the file is not UTF-8 encoded")) from e
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
                await ws.receive_text()        # the client sends nothing; wait for it to close
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
            # index.html refers to a bundle with a hash in its name: without no-cache the browser could
            # show the cached interface of the old version after mapcan is updated
            return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
    else:
        @app.get("/", include_in_schema=False)
        async def no_ui():
            return HTMLResponse("<h1>mapcan</h1><p>" + _(
                "The interface is not built: run <code>npm run build</code> in <code>web/</code>. The API is available "
                "at <a href='/api/docs'>/api/docs</a>.") + "</p>")

    return app
