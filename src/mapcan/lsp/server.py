"""Языковой сервер mapcan (LSP поверх stdio): ``mapcan lsp``.

Работает с YAML-документами, у которых есть ключ верхнего уровня ``mapcan:``;
остальные YAML-файлы пропускает.
"""

from __future__ import annotations

import re

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
    """Аргумент команды: pygls передаёт аргументы списком или по одному."""
    if len(args) == 1 and isinstance(args[0], list):
        args = args[0]
    return args[0] if args and isinstance(args[0], dict) else {}


class MapcanServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("mapcan", __version__)
        # Последний анализ каждого документа (для автодополнения, пока текст не разбирается).
        self.analyses: dict[str, A.Analysis] = {}

    def analysis(self, uri: str) -> A.Analysis | None:
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
def did_change(ls: MapcanServer, params: T.DidChangeTextDocumentParams) -> None:
    ls.publish(params.text_document.uri)


@server.feature(T.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: MapcanServer, params: T.DidCloseTextDocumentParams) -> None:
    uri = params.text_document.uri
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
    a = ls.analysis(params.text_document.uri)
    if a is None:
        return None
    lo, hi = params.range.start.line, params.range.end.line
    return [T.InlayHint(position=_pos(h.pos), label=h.label, padding_left=True)
            for h in A.inlay_hints(a) if lo <= h.pos[0] <= hi]


@server.feature(T.TEXT_DOCUMENT_COMPLETION, T.CompletionOptions(trigger_characters=[" ", ",", "["]))
def completion(ls: MapcanServer, params: T.CompletionParams) -> T.CompletionList | None:
    uri = params.text_document.uri
    doc = ls.workspace.get_text_document(uri)
    if not A.is_mapcan(doc.source):
        return None
    ls.analysis(uri)
    pos = (params.position.line, params.position.character)
    found = A.completions(doc.source, pos, ls.analyses.get(uri))
    if not found:
        return _snippets(doc.source, pos)
    key, choices = found
    kind = T.CompletionItemKind.Reference if key in A.DEVICE_KEYS else T.CompletionItemKind.EnumMember
    return T.CompletionList(is_incomplete=False,
                            items=[T.CompletionItem(label=c, kind=kind, detail=key) for c in choices])


def _snippets(text: str, pos: A.Pos) -> T.CompletionList | None:
    """Заготовки элементов списков после «- » (сам «- » уже набран, в заготовку не входит)."""
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
    """Узлы дерева карты для боковой панели. Параметр: {textDocument: {uri}}."""
    doc = params.get("textDocument") if isinstance(params, dict) else getattr(params, "textDocument", None)
    uri = doc.get("uri") if isinstance(doc, dict) else getattr(doc, "uri", None)
    a = ls.analysis(uri) if uri else None
    return A.map_tree(a) if a else []


@server.command("mapcan.lsp.export")
@server.thread()
def export_command(ls: MapcanServer, *args) -> dict:
    """Аргумент: {uri, formats: [...], outDir}. Ответ: {files: [...], warnings: [...]} или {error}."""
    from .exports import ExportError, export

    params = _arg(args)
    uri = params.get("uri", "")
    path = to_fs_path(uri)
    if not path or not uri.startswith("file:"):
        return {"error": _("Сохраните карту в файл перед экспортом.")}
    try:
        files, warnings = export(ls.workspace.get_text_document(uri).source, path,
                                 list(params.get("formats") or []), params.get("outDir") or "build")
    except ExportError as e:
        return {"error": str(e)}
    except Exception as e:   # noqa: BLE001 — ошибку экспорта показываем пользователю, сервер продолжает работу
        ls.window_log_message(T.LogMessageParams(type=T.MessageType.Error, message=repr(e)))
        return {"error": _("Ошибка экспорта: {error}", error=e)}
    return {"files": [str(f) for f in files], "warnings": warnings}


@server.command("mapcan.lsp.edit")
def edit_command(ls: MapcanServer, *args) -> dict:
    """Аргумент: {uri, action: add|duplicate|delete, path, kind}. Ответ: {edit: {range, text}, cursor} или {}."""
    params = _arg(args)
    uri = params.get("uri", "")
    a = ls.analysis(uri) if uri else None
    path = tuple(params.get("path") or ())
    action = params.get("action")
    # Пустой путь — только у новой шины (добавляется в карту)
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
    """(uri, path) из параметров запроса {textDocument: {uri}, path}."""
    get = (lambda o, k: o.get(k)) if isinstance(params, dict) else (lambda o, k: getattr(o, k, None))
    doc = get(params, "textDocument")
    uri = (doc.get("uri") if isinstance(doc, dict) else getattr(doc, "uri", None)) if doc else None
    return uri or "", tuple(get(params, "path") or ())


@server.feature("mapcan/node")
def node_request(ls: MapcanServer, params) -> dict | None:
    """Поля узла для формы. Параметр: {textDocument: {uri}, path}."""
    uri, path = _params(params)
    a = ls.analysis(uri) if uri else None
    return E.node_fields(a, path) if a else None


@server.command("mapcan.lsp.set")
def set_command(ls: MapcanServer, *args) -> dict:
    """Аргумент: {uri, path, value} — путь поля и новое значение (null — удалить).
    Ответ: {edits: [{range, text}]}."""
    params = _arg(args)
    uri = params.get("uri", "")
    a = ls.analysis(uri) if uri else None
    path = tuple(params.get("path") or ())
    if a is None or not path:
        return {"edits": []}
    edits = E.set_field(a, path, params.get("value"))
    return {"edits": [{"range": [*e.start, *e.end], "text": e.text} for e in edits]}


@server.command("mapcan.lsp.render")
@server.thread()
def render_command(ls: MapcanServer, *args) -> dict:
    """Аргумент: {uri}. Ответ: {text} — документ карты в Markdown — или {error}."""
    from ..export.text import render

    a = ls.analysis(_arg(args).get("uri", ""))
    if a is None or a.map is None:
        return {"error": _("Карта не разобрана: исправьте ошибки, чтобы увидеть документ.")}
    return {"text": render(a.map, "md")}


@server.command("mapcan.lsp.diff")
@server.thread()
def diff_command(ls: MapcanServer, *args) -> dict:
    """Аргумент: {uri, oldText, newText?}. Без newText новая версия — текущий текст карты.
    Ответ: {text} — изменения в Markdown — или {error}."""
    from ..diff import diff_maps, render_diff
    from ..loader import loads

    params = _arg(args)
    if params.get("newText") is not None:
        new = loads(params["newText"], "new.yaml").map
    else:
        a = ls.analysis(params.get("uri", ""))
        new = a.map if a else None
        if new is None:
            return {"error": _("Карта не разобрана: исправьте ошибки, чтобы сравнить версии.")}
    old = loads(params.get("oldText") or "", "old.yaml").map
    if old is None or new is None:
        return {"error": _("Версия карты из истории не разобрана.")}
    return {"text": render_diff(diff_maps(old, new), "md", new.lang)}


def _bump(version: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", version or "")
    return f"{m[1]}.{m[2]}.{int(m[3]) + 1}" if m else version or "0.1.0"


@server.command("mapcan.lsp.historyDraft")
@server.thread()
def history_draft_command(ls: MapcanServer, *args) -> dict:
    """Аргумент: {uri, oldText}. Ответ: черновик записи истории изменений с версии oldText до текущего
    текста — {version, date, author, github, changes} — или {error}. Автор — из профиля mapcan."""
    import datetime

    from ..diff import changelog_lines, diff_maps
    from ..loader import loads
    from ..userconfig import UserConfig

    params = _arg(args)
    a = ls.analysis(params.get("uri", ""))
    if a is None or a.map is None:
        return {"error": _("Карта не разобрана: исправьте ошибки, чтобы сравнить версии.")}
    old = loads(params.get("oldText") or "", "old.yaml").map
    if old is None:
        return {"error": _("Версия карты из истории не разобрана.")}
    d = diff_maps(old, a.map)
    current = a.map.document.version or ""
    user = UserConfig.load().user
    return {
        "version": _bump(current) if d.old_version == current else current,
        "date": datetime.date.today().isoformat(),
        "author": user.name or None,
        "github": user.github,
        "changes": changelog_lines(d, a.map.lang),
    }


@server.command("mapcan.lsp.addHistory")
def add_history_command(ls: MapcanServer, *args) -> dict:
    """Аргумент: {uri, version, date, author, github, changes}. Новая запись — первой в истории
    изменений, версия и дата документа — из неё. Ответ: {edit: {range, text}, cursor} или {error}."""
    params = _arg(args)
    a = ls.analysis(params.get("uri", ""))
    if a is None or a.result.raw is None:
        return {"error": _("Карта не разобрана: исправьте ошибки, чтобы сравнить версии.")}
    entry = {k: params.get(k) for k in ("version", "date", "author", "github")}
    change = E.add_history(a, entry, [str(c) for c in params.get("changes") or []])
    if change is None:
        return {"error": _("Историю изменений, записанную в одну строку, нельзя дополнить.")}
    e = E.minimal_edit(a.text, change.text)
    return {"edit": {"range": [*e.start, *e.end], "text": e.text}, "cursor": list(change.cursor)}


def main() -> None:
    server.start_io()
