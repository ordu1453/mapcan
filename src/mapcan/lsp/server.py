"""Language server of mapcan (LSP over stdio): ``mapcan lsp``.

It works with YAML documents that have the top-level key ``mapcan:``;
other YAML files are skipped.
"""

from __future__ import annotations

import asyncio

from lsprotocol import types as T
from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path

from .. import __version__
from ..i18n import _
from . import analysis as A
from . import edits as E

SEVERITY = {"error": T.DiagnosticSeverity.Error, "warning": T.DiagnosticSeverity.Warning,
            "info": T.DiagnosticSeverity.Information}
SYMBOL_KIND = {"bus": T.SymbolKind.Namespace, "device": T.SymbolKind.Module, "frame": T.SymbolKind.Struct,
               "signal": T.SymbolKind.Field, "flag": T.SymbolKind.Boolean}


def _pos(p: A.Pos) -> T.Position:
    return T.Position(line=p[0], character=p[1])


def _range(a: A.Pos, b: A.Pos) -> T.Range:
    return T.Range(start=_pos(a), end=_pos(b))


def _text_edit(e: E.Edit) -> T.TextEdit:
    return T.TextEdit(range=_range(e.start, e.end), new_text=e.text)


def _arg(args) -> dict:
    """Argument of a command: pygls passes the arguments as a list or one by one."""
    if len(args) == 1 and isinstance(args[0], list):
        args = args[0]
    return args[0] if args and isinstance(args[0], dict) else {}


# Pause after the last change before the map is analysed again: fast typing does not queue a full analysis
# per keystroke (a large map takes seconds).
DEBOUNCE = 0.3


class MapcanServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("mapcan", __version__)
        # The last analysis of each document (for completion while the text does not parse).
        self.analyses: dict[str, A.Analysis] = {}
        self.pending: dict[str, asyncio.Task] = {}     # the analysis waiting for the typing to pause

    def analysis(self, uri: str) -> A.Analysis | None:
        """The analysis of the current text: for edits, which must start from what is in the editor."""
        doc = self.workspace.get_text_document(uri)
        last = self.analyses.get(uri)
        if last is not None and last.text == doc.source:
            return last
        if not A.is_mapcan(doc.source):
            self.analyses.pop(uri, None)
            return None
        a = A.analyze(doc.source, to_fs_path(uri) or uri)
        self.analyses[uri] = a
        return a

    def latest(self, uri: str) -> A.Analysis | None:
        """The last finished analysis, even of a slightly older text: for completion and inlay hints, which come
        with every keystroke and should not wait for a new analysis. Without one, the current text."""
        last = self.analyses.get(uri)
        if last is not None and A.is_mapcan(self.workspace.get_text_document(uri).source):
            return last
        return self.analysis(uri)

    async def publish_later(self, uri: str) -> None:
        """Analyse in a worker thread once the typing pauses; a newer change cancels this run, and a result
        for an outdated text is dropped."""
        await asyncio.sleep(DEBOUNCE)
        doc = self.workspace.get_text_document(uri)
        text = doc.source
        if not A.is_mapcan(text):
            self.publish(uri)
            return
        last = self.analyses.get(uri)
        if last is None or last.text != text:
            last = await asyncio.to_thread(A.analyze, text, to_fs_path(uri) or uri)
            if self.workspace.get_text_document(uri).source != text:
                return          # changed meanwhile: the run of that change publishes
            self.analyses[uri] = last
        self.publish(uri)
        caps = self.client_capabilities.workspace
        if caps and caps.inlay_hint and caps.inlay_hint.refresh_support:
            self.workspace_inlay_hint_refresh(None)

    def schedule(self, uri: str) -> None:
        old = self.pending.pop(uri, None)
        if old is not None:
            old.cancel()
        task = asyncio.ensure_future(self.publish_later(uri))
        self.pending[uri] = task
        task.add_done_callback(lambda t: self.pending.pop(uri, None) if self.pending.get(uri) is t else None)

    def publish(self, uri: str) -> None:
        a = self.analysis(uri)
        diags = []
        for d in a.diagnostics if a else ():
            start, end = A.diagnostic_range(a, d)
            diags.append(T.Diagnostic(range=_range(start, end), message=d.message, severity=SEVERITY[d.level],
                                      code=d.code, source="mapcan", data={"node": d.node}))
        self.text_document_publish_diagnostics(T.PublishDiagnosticsParams(uri=uri, diagnostics=diags))


server = MapcanServer()


@server.feature(T.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: MapcanServer, params: T.DidOpenTextDocumentParams) -> None:
    ls.publish(params.text_document.uri)


@server.feature(T.TEXT_DOCUMENT_DID_CHANGE)
async def did_change(ls: MapcanServer, params: T.DidChangeTextDocumentParams) -> None:
    ls.schedule(params.text_document.uri)


@server.feature(T.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: MapcanServer, params: T.DidCloseTextDocumentParams) -> None:
    uri = params.text_document.uri
    task = ls.pending.pop(uri, None)
    if task is not None:
        task.cancel()
    ls.analyses.pop(uri, None)
    ls.text_document_publish_diagnostics(T.PublishDiagnosticsParams(uri=uri, diagnostics=[]))


@server.feature(T.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(ls: MapcanServer, params: T.DocumentSymbolParams) -> list[T.DocumentSymbol] | None:
    a = ls.analysis(params.text_document.uri)
    if a is None:
        return None

    def conv(s: A.Symbol) -> T.DocumentSymbol:
        return T.DocumentSymbol(name=s.name, detail=s.detail, kind=SYMBOL_KIND[s.kind],
                                range=_range(*s.range), selection_range=_range(*s.selection),
                                children=[conv(c) for c in s.children])

    return [conv(s) for s in A.symbols(a)]


@server.feature(T.TEXT_DOCUMENT_HOVER)
def hover(ls: MapcanServer, params: T.HoverParams) -> T.Hover | None:
    a = ls.analysis(params.text_document.uri)
    if a is None:
        return None
    md = A.hover(a, (params.position.line, params.position.character))
    if not md:
        return None
    return T.Hover(contents=T.MarkupContent(kind=T.MarkupKind.Markdown, value=md))


@server.feature(T.TEXT_DOCUMENT_INLAY_HINT, T.InlayHintOptions(resolve_provider=False))
def inlay_hint(ls: MapcanServer, params: T.InlayHintParams) -> list[T.InlayHint] | None:
    a = ls.latest(params.text_document.uri)
    if a is None:
        return None
    # Hints of an older text would stand at wrong places: none until the new analysis (it asks to refresh)
    if a.text != ls.workspace.get_text_document(params.text_document.uri).source:
        return []
    lo, hi = params.range.start.line, params.range.end.line
    return [T.InlayHint(position=_pos(h.pos), label=h.label, padding_left=True)
            for h in A.inlay_hints(a) if lo <= h.pos[0] <= hi]


@server.feature(T.TEXT_DOCUMENT_COMPLETION, T.CompletionOptions(trigger_characters=[" ", ",", "["]))
def completion(ls: MapcanServer, params: T.CompletionParams) -> T.CompletionList | None:
    uri = params.text_document.uri
    doc = ls.workspace.get_text_document(uri)
    if not A.is_mapcan(doc.source):
        return None
    ls.latest(uri)      # completion reads the text itself; the analysis only gives names and choices
    pos = (params.position.line, params.position.character)
    found = A.completions(doc.source, pos, ls.analyses.get(uri))
    if not found:
        return _snippets(doc.source, pos)
    key, choices = found
    kind = T.CompletionItemKind.Reference if key in A.DEVICE_KEYS else T.CompletionItemKind.EnumMember
    return T.CompletionList(is_incomplete=False,
                            items=[T.CompletionItem(label=c, kind=kind, detail=key) for c in choices])


def _snippets(text: str, pos: A.Pos) -> T.CompletionList | None:
    """Snippets of list items after "- " (the "- " itself is typed already and not part of the snippet)."""
    lines = text.splitlines()
    before = (lines[pos[0]] if pos[0] < len(lines) else "")[:pos[1]]
    m = A.SNIPPET_CTX.match(before)
    if not m:
        return None
    word = _range((pos[0], pos[1] - len(m.group(2))), pos)
    items = []
    for label, detail, body in A.SNIPPETS:
        items.append(T.CompletionItem(
            label=label, kind=T.CompletionItemKind.Snippet, detail=detail, filter_text=label,
            insert_text_format=T.InsertTextFormat.Snippet,
            text_edit=T.TextEdit(range=word, new_text=body.removeprefix("- "))))
    return T.CompletionList(is_incomplete=False, items=items)


@server.feature(T.TEXT_DOCUMENT_CODE_ACTION,
                T.CodeActionOptions(code_action_kinds=[T.CodeActionKind.QuickFix]))
def code_action(ls: MapcanServer, params: T.CodeActionParams) -> list[T.CodeAction] | None:
    uri = params.text_document.uri
    a = ls.analysis(uri)
    if a is None:
        return None
    diags = [d for d in params.context.diagnostics if d.source == "mapcan"]
    keys = [(str(d.code), (d.data or {}).get("node") or [], (d.range.start.line, d.range.start.character))
            for d in diags]
    out = []
    for act in E.quick_fixes(a, keys):
        out.append(T.CodeAction(
            title=act.title, kind=T.CodeActionKind.QuickFix, is_preferred=act.preferred,
            diagnostics=[diags[i] for i in act.diagnostics],
            edit=T.WorkspaceEdit(changes={uri: [_text_edit(e) for e in act.edits]})))
    return out


@server.feature(T.TEXT_DOCUMENT_DEFINITION)
def definition(ls: MapcanServer, params: T.DefinitionParams) -> T.Location | None:
    uri = params.text_document.uri
    a = ls.analysis(uri)
    found = E.definition(a, (params.position.line, params.position.character)) if a else None
    return T.Location(uri=uri, range=_range(*found)) if found else None


@server.feature(T.TEXT_DOCUMENT_REFERENCES)
def references(ls: MapcanServer, params: T.ReferenceParams) -> list[T.Location] | None:
    uri = params.text_document.uri
    a = ls.analysis(uri)
    if a is None:
        return None
    found = E.references(a, (params.position.line, params.position.character),
                         params.context.include_declaration)
    return [T.Location(uri=uri, range=_range(*r)) for r in found]


@server.feature(T.TEXT_DOCUMENT_PREPARE_RENAME)
def prepare_rename(ls: MapcanServer, params: T.PrepareRenameParams):
    a = ls.analysis(params.text_document.uri)
    path = E.name_at(a, (params.position.line, params.position.character)) if a else None
    if path is None:
        return None
    start, end = E.value_range(a, path)
    return T.PrepareRenamePlaceholder(range=_range(start, end), placeholder=str(E.raw_at(a, path)))


@server.feature(T.TEXT_DOCUMENT_RENAME)
def rename(ls: MapcanServer, params: T.RenameParams) -> T.WorkspaceEdit | None:
    uri = params.text_document.uri
    a = ls.analysis(uri)
    path = E.name_at(a, (params.position.line, params.position.character)) if a else None
    if path is None or not params.new_name.strip():
        return None
    edits = E.rename_edits(a, path, params.new_name.strip())
    return T.WorkspaceEdit(changes={uri: [_text_edit(e) for e in edits]})


@server.feature("mapcan/tree")
def map_tree(ls: MapcanServer, params) -> list[dict]:
    """Nodes of the map tree for the side bar. Parameter: {textDocument: {uri}}."""
    doc = params.get("textDocument") if isinstance(params, dict) else getattr(params, "textDocument", None)
    uri = doc.get("uri") if isinstance(doc, dict) else getattr(doc, "uri", None)
    a = ls.analysis(uri) if uri else None
    return A.map_tree(a) if a else []


@server.command("mapcan.lsp.export")
@server.thread()
def export_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, formats: [...], outDir}. Response: {files: [...], warnings: [...]} or {error}."""
    from .exports import ExportError, export

    params = _arg(args)
    uri = params.get("uri", "")
    path = to_fs_path(uri)
    if not path or not uri.startswith("file:"):
        return {"error": _("Save the map to a file before exporting.")}
    try:
        files, warnings = export(ls.workspace.get_text_document(uri).source, path,
                                 list(params.get("formats") or []), params.get("outDir") or "build")
    except ExportError as e:
        return {"error": str(e)}
    except Exception as e:   # noqa: BLE001 — the export error is shown to the user, the server keeps working
        ls.window_log_message(T.LogMessageParams(type=T.MessageType.Error, message=repr(e)))
        return {"error": _("Export failed: {error}", error=e)}
    return {"files": [str(f) for f in files], "warnings": warnings}


@server.command("mapcan.lsp.edit")
def edit_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, action: add|duplicate|delete, path, kind}. Response: {edit: {range, text}, cursor} or {}."""
    params = _arg(args)
    uri = params.get("uri", "")
    a = ls.analysis(uri) if uri else None
    path = tuple(params.get("path") or ())
    action = params.get("action")
    # An empty path: only a new bus (added to the map)
    if a is None or not (path or (action == "add" and params.get("kind") == "bus")):
        return {}
    if action == "add":
        change = E.add_node(a, path, params.get("kind", ""))
    elif action == "duplicate":
        change = E.duplicate_node(a, path)
    elif action == "delete":
        change = E.delete_node(a, path)
    else:
        change = None
    if change is None:
        return {}
    e = E.minimal_edit(a.text, change.text)
    return {"edit": {"range": [*e.start, *e.end], "text": e.text}, "cursor": list(change.cursor)}


def _params(params) -> tuple[str, tuple]:
    """(uri, path) from the request parameters {textDocument: {uri}, path}."""
    get = (lambda o, k: o.get(k)) if isinstance(params, dict) else (lambda o, k: getattr(o, k, None))
    doc = get(params, "textDocument")
    uri = (doc.get("uri") if isinstance(doc, dict) else getattr(doc, "uri", None)) if doc else None
    return uri or "", tuple(get(params, "path") or ())


@server.feature("mapcan/node")
def node_request(ls: MapcanServer, params) -> dict | None:
    """Fields of the node for the form. Parameter: {textDocument: {uri}, path}."""
    uri, path = _params(params)
    a = ls.analysis(uri) if uri else None
    return E.node_fields(a, path) if a else None


@server.command("mapcan.lsp.set")
def set_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, path, value}: the path of the field and its new value (null to remove it).
    Response: {edits: [{range, text}]}."""
    params = _arg(args)
    uri = params.get("uri", "")
    a = ls.analysis(uri) if uri else None
    path = tuple(params.get("path") or ())
    if a is None or not path:
        return {"edits": []}
    edits = E.set_field(a, path, params.get("value"))
    return {"edits": [{"range": [*e.start, *e.end], "text": e.text} for e in edits]}


@server.command("mapcan.lsp.ops")
def ops_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, ops}: operations of the web editor (set, remove, insert, move, rename_key, set_layout)
    as one edit. Response: {edit: {range, text}}, {} if the text did not change, or {error}."""
    from ..web.yamlops import OpError

    params = _arg(args)
    a = ls.analysis(params.get("uri", ""))
    if a is None:
        return {"error": _("The document is not a mapcan map.")}
    try:
        text = E.apply_ops(a, list(params.get("ops") or []))
    except OpError as e:
        return {"error": str(e)}
    if text == a.text:
        return {}
    e = E.minimal_edit(a.text, text)
    return {"edit": {"range": [*e.start, *e.end], "text": e.text}}


@server.command("mapcan.lsp.changes")
@server.thread()
def changes_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, oldText}. Response: {nodes: [{path, status}]}, the nodes of the current map added
    (added) or changed (modified) since the version oldText, or {error}."""
    from ..diff import changed_paths, diff_maps
    from ..loader import loads

    params = _arg(args)
    a = ls.analysis(params.get("uri", ""))
    if a is None or a.map is None:
        return {"error": _("The map cannot be read: fix the errors to compare versions.")}
    old = loads(params.get("oldText") or "", "old.yaml").map
    if old is None:
        return {"error": _("A version of the map from the history cannot be read.")}
    paths = changed_paths(diff_maps(old, a.map), a.map)
    return {"nodes": [{"path": list(p), "status": s} for p, s in paths.items()]}


@server.command("mapcan.lsp.render")
@server.thread()
def render_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri}. Response: {text}, the map's document in Markdown, or {error}."""
    from ..export.text import render

    a = ls.analysis(_arg(args).get("uri", ""))
    if a is None or a.map is None:
        return {"error": _("The map cannot be read: fix the errors to see the document.")}
    return {"text": render(a.map, "md")}


@server.command("mapcan.lsp.diff")
@server.thread()
def diff_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, oldText, newText?}. Without newText the new version is the current text of the map.
    Response: {text}, the changes in Markdown, or {error}."""
    from ..diff import diff_maps, render_diff
    from ..loader import loads

    params = _arg(args)
    if params.get("newText") is not None:
        new = loads(params["newText"], "new.yaml").map
    else:
        a = ls.analysis(params.get("uri", ""))
        new = a.map if a else None
        if new is None:
            return {"error": _("The map cannot be read: fix the errors to compare versions.")}
    old = loads(params.get("oldText") or "", "old.yaml").map
    if old is None or new is None:
        return {"error": _("A version of the map from the history cannot be read.")}
    return {"text": render_diff(diff_maps(old, new), "md", new.lang)}


@server.command("mapcan.lsp.historyDraft")
@server.thread()
def history_draft_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, oldText}. Response: a draft revision history entry from the version oldText to the current
    text, {version, date, author, github, changes}, or {error}. The author comes from the mapcan profile."""
    import datetime

    from ..diff import bump_version, changelog_lines, diff_maps
    from ..loader import loads
    from ..userconfig import UserConfig

    params = _arg(args)
    a = ls.analysis(params.get("uri", ""))
    if a is None or a.map is None:
        return {"error": _("The map cannot be read: fix the errors to compare versions.")}
    old = loads(params.get("oldText") or "", "old.yaml").map
    if old is None:
        return {"error": _("A version of the map from the history cannot be read.")}
    d = diff_maps(old, a.map)
    current = a.map.document.version or ""
    user = UserConfig.load().user
    return {
        "version": bump_version(current) if d.old_version == current else current,
        "date": datetime.date.today().isoformat(),
        "author": user.name or None,
        "github": user.github,
        "changes": changelog_lines(d, a.map.lang),
    }


@server.command("mapcan.lsp.releaseDraft")
@server.thread()
def release_draft_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, oldText, tags}: oldText is the map of the previous release or of the last commit (null:
    no releases yet), tags are the repository's tags. Response: {version, recorded, changes, date, author, github}
    or {error}; recorded tells that the entry of this version is already in the revision history."""
    import datetime

    from ..diff import release_draft
    from ..loader import loads
    from ..userconfig import UserConfig

    params = _arg(args)
    a = ls.analysis(params.get("uri", ""))
    if a is None or a.map is None:
        return {"error": _("The map cannot be read: fix the errors to compare versions.")}
    old = None
    if params.get("oldText") is not None:
        old = loads(params["oldText"], "old.yaml").map
        if old is None:
            return {"error": _("A version of the map from the history cannot be read.")}
    tags = set(params.get("tags") or [])
    user = UserConfig.load().user
    return {**release_draft(a.map, old, lambda v: f"v{v}" in tags),
            "date": datetime.date.today().isoformat(), "author": user.name or None, "github": user.github}


@server.command("mapcan.lsp.addHistory")
def add_history_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, version, date, author, github, changes}. The new entry goes first in the revision
    history, and the document's version and date come from it. Response: {edit: {range, text}, cursor} or {error}."""
    params = _arg(args)
    a = ls.analysis(params.get("uri", ""))
    if a is None or a.result.raw is None:
        return {"error": _("The map cannot be read: fix the errors to compare versions.")}
    entry = {k: params.get(k) for k in ("version", "date", "author", "github")}
    change = E.add_history(a, entry, [str(c) for c in params.get("changes") or []])
    if change is None:
        return {"error": _("The revision history is written on one line and cannot be extended.")}
    e = E.minimal_edit(a.text, change.text)
    return {"edit": {"range": [*e.start, *e.end], "text": e.text}, "cursor": list(change.cursor)}


def main() -> None:
    server.start_io()
