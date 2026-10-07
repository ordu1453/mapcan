"""Языковой сервер mapcan (LSP поверх stdio): ``mapcan lsp``.

Работает с YAML-документами, у которых есть ключ верхнего уровня ``mapcan:``;
остальные YAML-файлы пропускает.
"""

from __future__ import annotations

from lsprotocol import types as T
from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path

from .. import __version__
from ..i18n import _
from . import analysis as A

SEVERITY = {"error": T.DiagnosticSeverity.Error, "warning": T.DiagnosticSeverity.Warning,
            "info": T.DiagnosticSeverity.Information}
SYMBOL_KIND = {"bus": T.SymbolKind.Namespace, "device": T.SymbolKind.Module, "frame": T.SymbolKind.Struct,
               "signal": T.SymbolKind.Field, "flag": T.SymbolKind.Boolean}


def _pos(p: A.Pos) -> T.Position:
    return T.Position(line=p[0], character=p[1])


def _range(a: A.Pos, b: A.Pos) -> T.Range:
    return T.Range(start=_pos(a), end=_pos(b))


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
                                      code=d.code, source="mapcan"))
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
    found = A.completions(doc.source, (params.position.line, params.position.character), ls.analyses.get(uri))
    if not found:
        return None
    key, choices = found
    kind = T.CompletionItemKind.Reference if key in A.DEVICE_KEYS else T.CompletionItemKind.EnumMember
    return T.CompletionList(is_incomplete=False,
                            items=[T.CompletionItem(label=c, kind=kind, detail=key) for c in choices])


@server.command("mapcan.lsp.export")
@server.thread()
def export_command(ls: MapcanServer, *args) -> dict:
    """Аргумент: {uri, formats: [...], outDir}. Ответ: {files: [...], warnings: [...]} или {error}."""
    from .exports import ExportError, export

    params = args[0] if args and isinstance(args[0], dict) else {}
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


def main() -> None:
    server.start_io()
