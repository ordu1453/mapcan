"""Language server of mapcan (LSP over stdio): ``mapcan lsp``.

It works with YAML documents that have the top-level key ``mapcan:``;
other YAML files are skipped.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

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


def _file_uri(file: str) -> str:
    """URI of another file of the map (an included file, or the main file of an included one)."""
    return Path(file).resolve().as_uri()


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
        # The analysis running in a worker thread for a text: requests for that text wait for it
        self.running: dict[str, tuple[str, asyncio.Future]] = {}

    def read(self, path: str) -> str | None:
        """Text of a file of the map: the editor's if it is open (with unsaved changes), else the disk's."""
        target = Path(path).resolve()
        for doc in list(self.workspace.text_documents.values()):
            p = to_fs_path(doc.uri)
            if p and Path(p).resolve() == target:
                return doc.source
        return A.read_disk(path)

    def _fresh(self, a: A.Analysis, text: str) -> bool:
        return a.text == text and all(self.read(f) == t for f, t in a.deps.items())

    def _analyze(self, uri: str, text: str) -> A.Analysis:
        path = to_fs_path(uri) or uri
        if A.is_part(text) and uri.startswith("file:"):
            return A.analyze_part(text, path, self.read)
        return A.analyze(text, path, self.read)

    def analysis(self, uri: str) -> A.Analysis | None:
        """The analysis of the current text: for edits, which must start from what is in the editor."""
        doc = self.workspace.get_text_document(uri)
        last = self.analyses.get(uri)
        if last is not None and self._fresh(last, doc.source):
            return last
        if not A.handled(doc.source):
            self.analyses.pop(uri, None)
            return None
        a = self._analyze(uri, doc.source)
        self.analyses[uri] = a
        return a

    async def current(self, uri: str) -> A.Analysis | None:
        """The analysis of the current text without holding up the server: a fresh one as it is, otherwise one
        made in a worker thread (a request that comes meanwhile waits for the same run). Hover, the outline and
        the tree answer from it, so other requests and notifications are handled while a large map is read."""
        text = self.workspace.get_text_document(uri).source
        last = self.analyses.get(uri)
        if last is not None and self._fresh(last, text):
            return last
        if not A.handled(text):
            self.analyses.pop(uri, None)
            return None
        run = self.running.get(uri)
        if run is None or run[0] != text:
            run = (text, asyncio.ensure_future(asyncio.to_thread(self._analyze, uri, text)))
            self.running[uri] = run
            run[1].add_done_callback(lambda f: self.running.pop(uri, None) if self.running.get(uri) is run else None)
        a = await asyncio.shield(run[1])
        if self.workspace.get_text_document(uri).source == text:
            self.analyses[uri] = a
        return a

    def editable(self, uri: str) -> A.Analysis | None:
        """The analysis for an edit of the main file's own data (the revision history): none for an included
        file."""
        a = self.analysis(uri)
        return a if a is not None and not a.own_file else None

    def latest(self, uri: str) -> A.Analysis | None:
        """The last finished analysis, even of a slightly older text: for completion and inlay hints, which come
        with every keystroke and should not wait for a new analysis. Without one, the current text."""
        last = self.analyses.get(uri)
        if last is not None and A.handled(self.workspace.get_text_document(uri).source):
            return last
        return self.analysis(uri)

    def routed(self, a: A.Analysis, ops: list[dict], style: str) -> dict:
        """Operations applied to the files of the map they change (E.routed_ops) as an answer to the client:
        the edit of this document (``style``: "edits", a list, or "edit", one) and ``others``: [{uri, edit}]."""
        text, others = E.routed_ops(a, ops, self.read)

        def one(old: str, new: str) -> dict:
            e = E.minimal_edit(old, new)
            return {"range": [*e.start, *e.end], "text": e.text}

        own = [one(a.text, text)] if text != a.text else []
        out: dict = {"edits": own} if style == "edits" else ({"edit": own[0]} if own else {})
        rest = [{"uri": Path(f).as_uri(), "edit": one(self.read(f) or "", t)} for f, t in others.items()
                if t != (self.read(f) or "")]
        if rest:
            out["others"] = rest
        return out

    def dependents(self, uri: str) -> list[str]:
        """Open documents whose analysis read this one: a map and the files it includes depend on each other."""
        path = to_fs_path(uri)
        if not path:
            return []
        key = str(Path(path).resolve())
        return [u for u, a in list(self.analyses.items()) if u != uri and key in a.deps]

    async def publish_later(self, uri: str, delay: float = DEBOUNCE) -> None:
        """Analyse in a worker thread once the typing pauses; a newer change cancels this run, and a result
        for an outdated text is dropped."""
        await asyncio.sleep(delay)
        text = self.workspace.get_text_document(uri).source
        await self.current(uri)
        if self.workspace.get_text_document(uri).source != text:
            return          # changed meanwhile: the run of that change publishes
        self.publish(uri)
        caps = self.client_capabilities.workspace
        if caps and caps.inlay_hint and caps.inlay_hint.refresh_support:
            self.workspace_inlay_hint_refresh(None)

    def schedule(self, uri: str, delay: float = DEBOUNCE) -> None:
        old = self.pending.pop(uri, None)
        if old is not None:
            old.cancel()
        task = asyncio.ensure_future(self.publish_later(uri, delay))
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
async def did_open(ls: MapcanServer, params: T.DidOpenTextDocumentParams) -> None:
    # Analysed in a worker thread at once: opening a large map does not hold up the server
    ls.schedule(params.text_document.uri, 0)


@server.feature(T.TEXT_DOCUMENT_DID_CHANGE)
async def did_change(ls: MapcanServer, params: T.DidChangeTextDocumentParams) -> None:
    uri = params.text_document.uri
    # The map and its included files open in the editor are checked again too
    for u in [uri, *ls.dependents(uri)]:
        ls.schedule(u)


@server.feature(T.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: MapcanServer, params: T.DidCloseTextDocumentParams) -> None:
    uri = params.text_document.uri
    task = ls.pending.pop(uri, None)
    if task is not None:
        task.cancel()
    ls.analyses.pop(uri, None)
    ls.text_document_publish_diagnostics(T.PublishDiagnosticsParams(uri=uri, diagnostics=[]))


@server.feature(T.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
async def document_symbol(ls: MapcanServer, params: T.DocumentSymbolParams) -> list[T.DocumentSymbol] | None:
    a = await ls.current(params.text_document.uri)
    if a is None:
        return None

    def conv(s: A.Symbol) -> T.DocumentSymbol:
        return T.DocumentSymbol(name=s.name, detail=s.detail, kind=SYMBOL_KIND[s.kind],
                                range=_range(*s.range), selection_range=_range(*s.selection),
                                children=[conv(c) for c in s.children])

    return [conv(s) for s in A.symbols(a)]


@server.feature(T.TEXT_DOCUMENT_HOVER)
async def hover(ls: MapcanServer, params: T.HoverParams) -> T.Hover | None:
    a = await ls.current(params.text_document.uri)
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
    if not A.handled(doc.source):
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
async def code_action(ls: MapcanServer, params: T.CodeActionParams) -> list[T.CodeAction] | None:
    uri = params.text_document.uri
    a = await ls.current(uri)
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
async def definition(ls: MapcanServer, params: T.DefinitionParams) -> T.Location | None:
    uri = params.text_document.uri
    a = await ls.current(uri)
    found = E.definition_location(a, (params.position.line, params.position.character)) if a else None
    if not found:
        return None
    file, rng = found
    return T.Location(uri=_file_uri(file) if file else uri, range=_range(*rng))


@server.feature(T.TEXT_DOCUMENT_REFERENCES)
async def references(ls: MapcanServer, params: T.ReferenceParams) -> list[T.Location] | None:
    uri = params.text_document.uri
    a = await ls.current(uri)
    if a is None:
        return None
    found = E.reference_locations(a, (params.position.line, params.position.character),
                                  params.context.include_declaration)
    return [T.Location(uri=_file_uri(f) if f else uri, range=_range(*r)) for f, r in found]


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
    # A device is renamed with its references in every file of the map: the main file and the included ones
    files = E.rename_files(a, path, params.new_name.strip())
    return T.WorkspaceEdit(changes={_file_uri(f) if f else uri: [_text_edit(e) for e in edits]
                                    for f, edits in files.items()})


@server.feature("mapcan/tree")
async def map_tree(ls: MapcanServer, params) -> list[dict]:
    """Nodes of the map tree for the side bar. Parameter: {textDocument: {uri}}."""
    doc = params.get("textDocument") if isinstance(params, dict) else getattr(params, "textDocument", None)
    uri = doc.get("uri") if isinstance(doc, dict) else getattr(doc, "uri", None)
    a = await ls.current(uri) if uri else None
    return A.map_tree(a) if a else []


@server.command("mapcan.lsp.export")
@server.thread()
def export_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, formats: [...], outDir}. Response: {files: [...], warnings: [...], map} or {error}.
    For a file included by a map (``part_of``) the map is exported; ``outDir`` is relative to the map's folder."""
    from .exports import ExportError, export

    params = _arg(args)
    uri = params.get("uri", "")
    path = to_fs_path(uri)
    if not path or not uri.startswith("file:"):
        return {"error": _("Save the map to a file before exporting.")}
    try:
        files, warnings, map_file = export(ls.workspace.get_text_document(uri).source, path,
                                           list(params.get("formats") or []), params.get("outDir") or "build",
                                           ls.read)
    except ExportError as e:
        return {"error": str(e)}
    except Exception as e:   # noqa: BLE001 — the export error is shown to the user, the server keeps working
        ls.window_log_message(T.LogMessageParams(type=T.MessageType.Error, message=repr(e)))
        return {"error": _("Export failed: {error}", error=e)}
    return {"files": [str(f) for f in files], "warnings": warnings, "map": str(map_file)}


@server.command("mapcan.lsp.starters")
def starters_command(ls: MapcanServer, *args) -> dict:
    """The templates of a new map and the example maps, as on the web editor's start screen.
    Response: {templates: [{id, label}], examples: [{name, title}]}."""
    from ..web.examples import list_examples
    from ..web.newmap import template_labels

    return {"templates": [{"id": k, "label": v} for k, v in template_labels().items()],
            "examples": list_examples()}


@server.command("mapcan.lsp.newMap")
def new_map_command(ls: MapcanServer, *args) -> dict:
    """Argument: {template, title, language}. Response: {text} or {error}."""
    from ..web.newmap import new_map_text

    params = _arg(args)
    try:
        return {"text": new_map_text(str(params.get("template") or ""), str(params.get("title") or ""),
                                     lang=str(params.get("language") or "en"))}
    except ValueError as e:
        return {"error": str(e)}


@server.command("mapcan.lsp.importDbc")
@server.thread()
def import_dbc_command(ls: MapcanServer, *args) -> dict:
    """Argument: {path, title, language}: a DBC file. Response: {text, warnings} (the YAML of the map and what the
    import could not bring over) or {error}."""
    from ..i18n import normalize_language
    from ..importers.dbc import import_dbc

    params = _arg(args)
    path = Path(str(params.get("path") or ""))
    if not path.is_file():
        return {"error": _("file not found: {path}", path=path)}
    try:
        text, warnings = import_dbc(path, params.get("title") or None,
                                    normalize_language(str(params.get("language") or "en")) or "en")
    except Exception as e:  # noqa: BLE001 — cantools raises many kinds of errors on a broken DBC
        return {"error": _("could not import {name}: {error}", name=path.name, error=e)}
    return {"text": text, "warnings": warnings}


@server.command("mapcan.lsp.example")
def example_command(ls: MapcanServer, *args) -> dict:
    """Argument: {name, mapFile}: an example and the file name of its copy. Response: {text, includes: {path
    relative to the map: text}} or {error}; an included file's part_of names the copy."""
    from ..web.examples import example_includes, example_text

    params = _arg(args)
    name = str(params.get("name") or "")
    try:
        return {"text": example_text(name), "includes": example_includes(name, params.get("mapFile") or None)}
    except (ValueError, OSError) as e:
        return {"error": str(e)}


@server.command("mapcan.lsp.edit")
def edit_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, action: add|duplicate|delete, path, kind}. Response: {edit: {range, text}, cursor, uri},
    {error} (a signal that has no room in its frame) or {}.

    The edit goes to the file the node is written in (for a new node, its owner's; a new bus goes to the main
    file): ``uri`` is there when that is another file of the map than the document. An included file that a
    delete leaves adding nothing to the map (a device's own file, #136) goes instead: {delete: its uri, edits,
    others}, the edits removing it from ``include`` (as mapcan.lsp.ops)."""
    from ..web.devicefile import exclude_ops, part_is_empty

    params = _arg(args)
    uri = params.get("uri", "")
    a = ls.analysis(uri) if uri else None
    path = tuple(params.get("path") or ())
    action = params.get("action")
    # An empty path: only a new bus (added to the map)
    if a is None or not (path or (action == "add" and params.get("kind") == "bus")):
        return {}
    view = a.view_of(path)
    if view is None:
        return {}
    if action == "add":
        try:
            change = E.add_node(view, path, params.get("kind", ""))
        except E.EditRefused as e:
            return {"error": str(e)}
    elif action == "duplicate":
        change = E.duplicate_node(view, path)
    elif action == "delete":
        change = E.delete_node(view, path)
    else:
        change = None
    if change is None:
        return {}
    if action == "delete" and view.own_file and part_is_empty(change.text):
        from ..web.yamlops import OpError

        raw = a.result.raw if isinstance(a.result.raw, dict) else {}
        main = Path(a.result.source.file or "")
        try:
            out = ls.routed(a, exclude_ops(raw.get("include"), main, Path(view.own_file)), "edits")
        except OpError:
            out = {}
        if out.get("edits") or out.get("others"):
            return {**out, "delete": _file_uri(view.own_file)}
    e = E.minimal_edit(view.text, change.text)
    out = {"edit": {"range": [*e.start, *e.end], "text": e.text}, "cursor": list(change.cursor)}
    if view is not a:
        out["uri"] = _file_uri(view.own_file or view.result.source.file)
    return out


@server.command("mapcan.lsp.deviceFile")
def device_file_command(ls: MapcanServer, *args) -> dict:
    """A new device of a bus in a file of its own (#136). Argument: {uri, path: path of the bus, file}.
    Without ``file``: {file}, the default name of the file relative to the map. With it: {create: {uri, text},
    cursor: the device's name in the new file, edits and others: the line of ``include`` (as mapcan.lsp.ops)},
    or {error}."""
    from ..web.yamlops import OpError

    params = _arg(args)
    a = ls.analysis(params.get("uri", ""))
    if a is None:
        return {"error": _("The document is not a mapcan map.")}
    file = params.get("file")
    try:
        made = E.device_file(a, tuple(params.get("path") or ()), None if file is None else str(file))
        if file is None:
            return made
        out = ls.routed(a, made["ops"], "edits")
    except (ValueError, OpError) as e:
        return {"error": str(e)}
    lines = made["text"].splitlines()
    # The device is the last named item: the bus comes before it
    line = max(i for i, ln in enumerate(lines) if ln.lstrip().startswith("- name:"))
    return {**out, "create": {"uri": made["target"].as_uri(), "text": made["text"]},
            "cursor": [line, lines[line].index("name:") + len("name: ")]}


def _params(params) -> tuple[str, tuple]:
    """(uri, path) from the request parameters {textDocument: {uri}, path}."""
    get = (lambda o, k: o.get(k)) if isinstance(params, dict) else (lambda o, k: getattr(o, k, None))
    doc = get(params, "textDocument")
    uri = (doc.get("uri") if isinstance(doc, dict) else getattr(doc, "uri", None)) if doc else None
    return uri or "", tuple(get(params, "path") or ())


@server.feature("mapcan/node")
async def node_request(ls: MapcanServer, params) -> dict | None:
    """Fields of the node for the form. Parameter: {textDocument: {uri}, path}."""
    uri, path = _params(params)
    a = await ls.current(uri) if uri else None
    return E.node_fields(a, path) if a else None


@server.command("mapcan.lsp.set")
def set_command(ls: MapcanServer, *args) -> dict:
    """Argument: {uri, path, value}: the path of the field and its new value (null to remove it).
    Response: {edits: [{range, text}]}."""
    params = _arg(args)
    uri = params.get("uri", "")
    a = ls.analysis(uri) if uri else None
    path = tuple(params.get("path") or ())
    if a is None or not path or not isinstance(path[-1], str):
        return {"edits": []}
    if E.in_other_file(a, path):
        # A node of another file of the map (or this text is a file included by it): edited in its own file
        from ..web.yamlops import OpError

        try:
            return ls.routed(a, E.field_ops(a, path, params.get("value")), "edits")
        except OpError as e:
            return {"edits": [], "error": str(e)}
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
    ops = list(params.get("ops") or [])
    try:
        if a.own_file or any(isinstance(o.get("path"), list) and a.result.source.is_included(tuple(o["path"]))
                             for o in ops):
            out = ls.routed(a, ops, "edit")
            return out if out.get("edit") or out.get("others") else {}
        text = E.apply_ops(a, ops)
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
    a = ls.editable(params.get("uri", ""))
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
