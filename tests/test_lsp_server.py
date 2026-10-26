"""Language server: the protocol handlers and commands on a server with documents in memory."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("pygls")

from lsprotocol import types as T  # noqa: E402
from pygls.workspace import Workspace  # noqa: E402

from mapcan.lsp import edits as E  # noqa: E402
from mapcan.lsp import server as S  # noqa: E402

from .conftest import ROOT  # noqa: E402

MINIMAL = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8")
VEHICLE = (ROOT / "examples" / "vehicle-can.yaml").read_text(encoding="utf-8")
TRACTOR = ROOT / "examples" / "tractor"
FRAME = ["buses", 0, "devices", 0, "frames", 0]
NOT_MAP = "file:///not-a-map.yaml"


class Server(S.MapcanServer):
    """The server without a client: documents in an in-memory workspace, notifications recorded."""

    def __init__(self, refresh: bool = False) -> None:
        super().__init__()
        self._ws = Workspace(None, T.TextDocumentSyncKind.Full)
        self._caps = T.ClientCapabilities(workspace=T.WorkspaceClientCapabilities(
            inlay_hint=T.InlayHintWorkspaceClientCapabilities(refresh_support=refresh)))
        self.published: dict[str, list[T.Diagnostic]] = {}
        self.refreshed = 0
        self.logs: list[str] = []

    @property
    def workspace(self):
        return self._ws

    @property
    def client_capabilities(self):
        return self._caps

    def text_document_publish_diagnostics(self, params):
        self.published[params.uri] = params.diagnostics

    def workspace_inlay_hint_refresh(self, params):
        self.refreshed += 1

    def window_log_message(self, params):
        self.logs.append(params.message)

    def open(self, uri: str, text: str) -> str:
        self._ws.put_text_document(T.TextDocumentItem(uri=uri, language_id="yaml", version=1, text=text))
        return uri

    def change(self, uri: str, text: str) -> None:
        doc = self._ws.get_text_document(uri)
        self._ws.update_text_document(T.VersionedTextDocumentIdentifier(uri=uri, version=doc.version + 1),
                                      T.TextDocumentContentChangeWholeDocument(text=text))


def run(coro):
    return asyncio.run(coro)


def doc(uri: str) -> T.TextDocumentIdentifier:
    return T.TextDocumentIdentifier(uri=uri)


def pos(text: str, sub: str, offset: int = 1) -> T.Position:
    lines = text.splitlines()
    i = next(i for i, line in enumerate(lines) if sub in line)
    return T.Position(line=i, character=lines[i].index(sub) + offset)


def apply(text: str, edit: dict) -> str:
    """Apply one edit of a command's answer: {range: [line, col, line, col], text}."""
    lines = text.splitlines(keepends=True)
    sl, sc, el, ec = edit["range"]

    def offset(line, col):
        return sum(len(x) for x in lines[:line]) + col

    return text[:offset(sl, sc)] + edit["text"] + text[offset(el, ec):]


@pytest.fixture
def ls():
    ls = Server()
    ls.open(NOT_MAP, "name: build\n")
    return ls


@pytest.fixture
def minimal(ls, tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(MINIMAL, encoding="utf-8")
    return ls.open(p.as_uri(), MINIMAL)


# --------------------------------------------------------------------------- helpers


def test_conversions():
    assert S._pos((2, 5)) == T.Position(line=2, character=5)
    assert S._range((1, 0), (1, 4)) == T.Range(start=T.Position(line=1, character=0),
                                               end=T.Position(line=1, character=4))
    assert S._file_uri(str(TRACTOR / "tractor.yaml")) == (TRACTOR / "tractor.yaml").resolve().as_uri()
    # pygls passes the arguments of a command as a list, or one by one
    assert S._arg(([{"uri": "u"}],)) == {"uri": "u"}
    assert S._arg(({"uri": "u"},)) == {"uri": "u"}
    assert S._arg(()) == S._arg(("text",)) == S._arg(([],)) == {}
    assert S._params({"textDocument": {"uri": "u"}, "path": ["buses", 0]}) == ("u", ("buses", 0))
    assert S._params(T.TextDocumentPositionParams(text_document=doc("u"), position=T.Position(line=0, character=0))
                     ) == ("", ())
    assert S._params({}) == ("", ())


def test_read_prefers_the_open_document(ls, tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("on disk\n", encoding="utf-8")
    assert ls.read(str(p)) == "on disk\n"
    ls.open(p.as_uri(), "in the editor\n")
    assert ls.read(str(p)) == "in the editor\n"
    assert ls.read(str(tmp_path / "missing.yaml")) is None


# --------------------------------------------------------------------------- analysis and diagnostics


def test_analysis_is_reused_until_the_text_changes(ls, minimal):
    a = ls.analysis(minimal)
    assert a is not None and ls.analysis(minimal) is a and ls.latest(minimal) is a
    assert run(ls.current(minimal)) is a
    ls.change(minimal, MINIMAL.replace("factor: 0.01", "factor: 0.1"))
    # latest answers with the older analysis at once, analysis and current read the new text
    assert ls.latest(minimal) is a
    b = run(ls.current(minimal))
    assert b is not a and "factor: 0.1\n" in b.text and ls.analysis(minimal) is b


def test_documents_that_are_not_maps(ls):
    uri = ls.open("file:///other.yaml", "name: build\non: push\n")
    assert ls.analysis(uri) is None and run(ls.current(uri)) is None and ls.latest(uri) is None
    assert ls.editable(uri) is None
    run(S.did_open(ls, T.DidOpenTextDocumentParams(text_document=T.TextDocumentItem(
        uri=uri, language_id="yaml", version=1, text="name: build\n"))))
    assert run(S.document_symbol(ls, T.DocumentSymbolParams(text_document=doc(uri)))) is None
    assert run(S.hover(ls, T.HoverParams(text_document=doc(uri), position=T.Position(line=0, character=0)))) is None
    assert S.inlay_hint(ls, T.InlayHintParams(text_document=doc(uri), range=T.Range(
        start=T.Position(line=0, character=0), end=T.Position(line=9, character=0)))) is None
    assert S.completion(ls, T.CompletionParams(text_document=doc(uri), position=T.Position(line=0, character=0))
                        ) is None
    assert run(S.code_action(ls, T.CodeActionParams(text_document=doc(uri), range=T.Range(
        start=T.Position(line=0, character=0), end=T.Position(line=0, character=0)),
        context=T.CodeActionContext(diagnostics=[])))) is None
    assert run(S.definition(ls, T.DefinitionParams(text_document=doc(uri),
                                                   position=T.Position(line=0, character=0)))) is None
    assert run(S.references(ls, T.ReferenceParams(text_document=doc(uri), position=T.Position(line=0, character=0),
                                                  context=T.ReferenceContext(include_declaration=True)))) is None
    assert S.prepare_rename(ls, T.PrepareRenameParams(text_document=doc(uri),
                                                      position=T.Position(line=0, character=0))) is None
    assert run(S.map_tree(ls, {"textDocument": {"uri": uri}})) == []
    assert run(S.map_tree(ls, {})) == []
    assert run(S.node_request(ls, {"textDocument": {"uri": uri}, "path": []})) is None


def test_publish_diagnostics(ls, minimal):
    ls.change(minimal, MINIMAL.replace("factor: 0.01", "factor: 0"))
    ls.publish(minimal)
    [d] = [d for d in ls.published[minimal] if d.code == "zero-factor"]
    assert d.source == "mapcan" and d.severity in S.SEVERITY.values()
    assert d.range.start.line == pos(MINIMAL, "factor: 0.01").line and d.data["node"]
    # Not a map: the diagnostics are cleared
    ls.change(minimal, "name: build\n")
    ls.publish(minimal)
    assert ls.published[minimal] == []


def test_open_change_and_close(tmp_path):
    ls = Server(refresh=True)

    async def scenario():
        uri = ls.open((tmp_path / "m.yaml").as_uri(), MINIMAL)
        await S.did_open(ls, T.DidOpenTextDocumentParams(text_document=T.TextDocumentItem(
            uri=uri, language_id="yaml", version=1, text=MINIMAL)))
        await asyncio.gather(*ls.pending.values())
        assert uri in ls.published and ls.refreshed == 1
        # Changes in a row: the earlier run is cancelled, only the last text is analysed and published
        for factor in ("0", "0.5", "0"):
            ls.change(uri, MINIMAL.replace("factor: 0.01", f"factor: {factor}"))
            await S.did_change(ls, T.DidChangeTextDocumentParams(
                text_document=T.VersionedTextDocumentIdentifier(uri=uri, version=2), content_changes=[]))
        await asyncio.gather(*ls.pending.values())
        assert any(d.code == "zero-factor" for d in ls.published[uri]) and ls.refreshed == 2
        # A change waiting for the pause is cancelled when the document is closed
        ls.schedule(uri, 10)
        task = ls.pending[uri]
        S.did_close(ls, T.DidCloseTextDocumentParams(text_document=doc(uri)))
        await asyncio.sleep(0)
        assert task.cancelled() and uri not in ls.analyses and ls.published[uri] == []
        S.did_close(ls, T.DidCloseTextDocumentParams(text_document=doc(uri)))

    run(scenario())


def test_publish_later_drops_an_outdated_text(ls, minimal, monkeypatch):
    analyse = ls.current

    async def current(uri):
        a = await analyse(uri)
        ls.change(minimal, MINIMAL + "\n")      # typed while the analysis ran
        return a

    monkeypatch.setattr(ls, "current", current)
    run(ls.publish_later(minimal, 0))
    assert minimal not in ls.published


def test_dependents(ls):
    main = ls.open((TRACTOR / "tractor.yaml").as_uri(), (TRACTOR / "tractor.yaml").read_text(encoding="utf-8"))
    part = ls.open((TRACTOR / "powertrain.yaml").as_uri(),
                   (TRACTOR / "powertrain.yaml").read_text(encoding="utf-8"))
    assert ls.analysis(main) is not None and ls.analysis(part) is not None
    # The map and its included file depend on each other
    assert ls.dependents(part) == [main] and ls.dependents(main) == [part]
    assert ls.dependents("untitled:1") == []


# --------------------------------------------------------------------------- requests


def test_document_symbol_and_hover(ls, minimal):
    [bus] = run(S.document_symbol(ls, T.DocumentSymbolParams(text_document=doc(minimal))))
    assert (bus.name, bus.kind) == ("demo", T.SymbolKind.Namespace)
    [device] = bus.children
    [frame] = device.children
    assert (device.kind, frame.name, frame.kind) == (T.SymbolKind.Module, "pump_state", T.SymbolKind.Struct)
    assert [s.kind for s in frame.children][:2] == [T.SymbolKind.Field, T.SymbolKind.Field]

    h = run(S.hover(ls, T.HoverParams(text_document=doc(minimal), position=pos(MINIMAL, "node_id"))))
    assert h.contents.kind == T.MarkupKind.Markdown and h.contents.value.startswith("**node_id**")
    assert run(S.hover(ls, T.HoverParams(text_document=doc(minimal), position=T.Position(line=2, character=0)))
               ) is None


def test_inlay_hints(ls, minimal):
    def hints(lo, hi):
        return S.inlay_hint(ls, T.InlayHintParams(text_document=doc(minimal), range=T.Range(
            start=T.Position(line=lo, character=0), end=T.Position(line=hi, character=0))))

    every = hints(0, 1000)
    assert every and all(h.padding_left for h in every)
    line = pos(MINIMAL, "name: pressure").line
    assert [h.position.line for h in hints(line, line + 10)] == [h.position.line for h in every
                                                                  if line <= h.position.line <= line + 10]
    # The text changed since the analysis: no hints until the new one
    ls.change(minimal, MINIMAL + "\n")
    assert hints(0, 1000) == []


def test_completion(ls):
    uri = ls.open("file:///v.yaml", VEHICLE)
    p = pos(VEHICLE, "receivers: [vcu, ", len("receivers: [vcu, "))
    found = S.completion(ls, T.CompletionParams(text_document=doc(uri), position=p))
    assert "dashboard" in [i.label for i in found.items]
    assert {(i.kind, i.detail) for i in found.items} == {(T.CompletionItemKind.Reference, "receivers")}

    text = MINIMAL
    uri = ls.open("file:///c.yaml", text)

    p = pos(text, "encoding: enum", len("encoding: "))
    found = S.completion(ls, T.CompletionParams(text_document=doc(uri), position=p))
    assert found.items[0].kind == T.CompletionItemKind.EnumMember and "number" in [i.label for i in found.items]

    # After "- " in a list: snippets, which replace the word typed so far
    text = MINIMAL + "              - na"
    ls.change(uri, text)
    last = len(text.splitlines()) - 1
    found = S.completion(ls, T.CompletionParams(text_document=doc(uri), position=T.Position(line=last, character=18)))
    assert found.items and all(i.kind == T.CompletionItemKind.Snippet for i in found.items)
    assert found.items[0].text_edit.range == T.Range(start=T.Position(line=last, character=16),
                                                     end=T.Position(line=last, character=18))
    assert not found.items[0].text_edit.new_text.startswith("- ")
    # Free text: nothing
    assert S.completion(ls, T.CompletionParams(text_document=doc(uri), position=pos(MINIMAL, "title: Pump", 12))
                        ) is None


def test_snippets_past_the_end():
    assert S._snippets("mapcan: 2\n", (5, 0)) is None


def test_code_action(ls):
    text = MINIMAL.replace("factor: 0.01", "factor: 0,01")
    uri = ls.open("file:///q.yaml", text)
    ls.publish(uri)
    diags = ls.published[uri]
    [comma] = [d for d in diags if d.code == "number-comma"]
    other = T.Diagnostic(range=comma.range, message="other", source="yaml-ls")
    [act] = run(S.code_action(ls, T.CodeActionParams(text_document=doc(uri), range=comma.range,
                                                     context=T.CodeActionContext(diagnostics=[other, comma]))))
    assert act.kind == T.CodeActionKind.QuickFix and act.diagnostics == [comma]
    [edit] = act.edit.changes[uri]
    assert edit.new_text == "0.01"
    assert run(S.code_action(ls, T.CodeActionParams(text_document=doc(uri), range=comma.range,
                                                    context=T.CodeActionContext(diagnostics=[other])))) == []


def test_definition_references_and_rename(ls):
    uri = ls.open("file:///v.yaml", VEHICLE)
    p = pos(VEHICLE, "receivers: [vcu", len("receivers: [") + 1)
    loc = run(S.definition(ls, T.DefinitionParams(text_document=doc(uri), position=p)))
    assert loc.uri == uri and "- name: vcu" in VEHICLE.splitlines()[loc.range.start.line]
    assert run(S.definition(ls, T.DefinitionParams(text_document=doc(uri), position=T.Position(line=0, character=0)))
               ) is None

    decl = pos(VEHICLE, "- name: vcu", 9)
    refs = run(S.references(ls, T.ReferenceParams(text_document=doc(uri), position=decl,
                                                  context=T.ReferenceContext(include_declaration=True))))
    without = run(S.references(ls, T.ReferenceParams(text_document=doc(uri), position=decl,
                                                     context=T.ReferenceContext(include_declaration=False))))
    assert len(refs) == len(without) + 1 >= 3 and all(r.uri == uri for r in refs)

    ph = S.prepare_rename(ls, T.PrepareRenameParams(text_document=doc(uri), position=decl))
    assert ph.placeholder == "vcu" and ph.range.start.line == decl.line
    edit = S.rename(ls, T.RenameParams(text_document=doc(uri), position=decl, new_name=" ecu "))
    assert list(edit.changes) == [uri]
    assert {e.new_text for e in edit.changes[uri]} == {"ecu"} and len(edit.changes[uri]) == len(refs)
    assert S.rename(ls, T.RenameParams(text_document=doc(uri), position=decl, new_name="  ")) is None
    assert S.rename(ls, T.RenameParams(text_document=doc(uri), position=T.Position(line=0, character=0),
                                       new_name="x")) is None


def test_definition_in_an_included_file(ls):
    text = (TRACTOR / "powertrain.yaml").read_text(encoding="utf-8")
    uri = ls.open((TRACTOR / "powertrain.yaml").as_uri(), text)
    loc = run(S.definition(ls, T.DefinitionParams(text_document=doc(uri),
                                                  position=pos(text, "receivers: [cab_ctrl]", 13))))
    assert loc.uri == (TRACTOR / "tractor.yaml").resolve().as_uri()


def test_tree_and_node(ls, minimal):
    [bus] = run(S.map_tree(ls, {"textDocument": {"uri": minimal}}))
    assert bus["kind"] == "bus"
    params = T.TextDocumentIdentifier(uri=minimal)
    assert run(S.map_tree(ls, type("P", (), {"textDocument": params})())) == [bus]
    node = run(S.node_request(ls, {"textDocument": {"uri": minimal}, "path": FRAME}))
    assert node["kind"] == "frame"


# --------------------------------------------------------------------------- commands


def test_export_command(ls, minimal, tmp_path):
    r = S.export_command(ls, {"uri": minimal, "formats": ["md", "dbc"], "outDir": "out"})
    assert Path(r["map"]).name == "m.yaml" and r["warnings"] == []
    assert {Path(f).suffix for f in r["files"]} == {".md", ".dbc"}
    assert all(Path(f).is_relative_to(tmp_path / "out") for f in r["files"])
    assert "error" in S.export_command(ls, {"uri": minimal, "formats": ["nope"]})
    assert "error" in S.export_command(ls, {"uri": "untitled:1", "formats": ["md"]})


def test_export_command_unexpected_error(ls, minimal, monkeypatch):
    from mapcan.lsp import exports

    def boom(*args, **kw):
        raise KeyError("boom")

    monkeypatch.setattr(exports, "export", boom)
    r = S.export_command(ls, {"uri": minimal, "formats": ["md"]})
    assert "boom" in r["error"] and ls.logs == ["KeyError('boom')"]


def test_starters_and_new_map():
    r = S.starters_command(None)
    assert {"canopen", "empty"} <= {t["id"] for t in r["templates"]}
    assert "minimal" in {e["name"] for e in r["examples"]}
    text = S.new_map_command(None, {"template": "canopen", "title": "My map", "language": "ru"})["text"]
    assert "My map" in text and "language: ru" in text
    assert "language: en" in S.new_map_command(None, {"template": "empty"})["text"]
    assert "error" in S.new_map_command(None, {"template": "nope"})


def test_example_command():
    r = S.example_command(None, {"name": "minimal"})
    assert "pump_state" in r["text"] and r["includes"] == {}
    r = S.example_command(None, {"name": "tractor", "mapFile": "copy.yaml"})
    assert list(r["includes"]) == ["powertrain.yaml"] and "copy.yaml" in r["includes"]["powertrain.yaml"]
    assert "error" in S.example_command(None, {"name": "nope"})


def test_edit_command(ls, minimal):
    def edit(**kw):
        return S.edit_command(ls, {"uri": minimal, **kw})

    r = edit(action="add", path=FRAME, kind="signal")
    assert "- name: signal" in r["edit"]["text"] and "uri" not in r
    r = edit(action="add", path=[], kind="bus")
    new = apply(MINIMAL, r["edit"])
    assert new.count("  - name: ") == MINIMAL.count("  - name: ") + 1 and "uri" not in r
    r = edit(action="duplicate", path=FRAME)
    assert "pump_state" in r["edit"]["text"] and len(r["cursor"]) == 2
    r = edit(action="delete", path=[*FRAME, "signals", 5])
    assert "counter" not in apply(MINIMAL, r["edit"])
    assert edit(action="rename", path=FRAME) == {}
    assert edit(action="add", path=[]) == {}
    assert edit(action="delete", path=["buses", 7]) == {}
    assert S.edit_command(ls, {"action": "add", "kind": "bus"}) == {}
    assert "error" in S.device_file_command(ls, {"uri": NOT_MAP, "path": ["buses", 0]})
    # No free bits left in the frame: refused with the reason
    full = ls.open("file:///full.yaml", MINIMAL.replace("bit_length: 4", "bit_length: 8"))
    assert "error" in S.edit_command(ls, {"uri": full, "action": "add", "path": FRAME, "kind": "signal"})


def test_edit_command_in_an_included_file(ls):
    main = ls.open((TRACTOR / "tractor.yaml").as_uri(), (TRACTOR / "tractor.yaml").read_text(encoding="utf-8"))
    assert ls.analysis(main).included_file(("buses", 0, "devices", 1))      # the gateway, on the cab bus
    r = S.edit_command(ls, {"uri": main, "action": "duplicate", "path": ["buses", 0, "devices", 1]})
    # The device is written in the included file: the edit goes there
    assert r["uri"] == (TRACTOR / "powertrain.yaml").resolve().as_uri()


def test_set_command(ls, minimal):
    r = S.set_command(ls, {"uri": minimal, "path": [*FRAME, "cycle_ms"], "value": 50})
    assert "cycle_ms: 50" in apply(MINIMAL, r["edits"][0])
    assert S.set_command(ls, {"uri": minimal, "path": []}) == {"edits": []}
    assert S.set_command(ls, {"uri": minimal, "path": [*FRAME, "signals", 0]}) == {"edits": []}
    assert S.set_command(ls, {"uri": NOT_MAP, "path": ["x"]}) == {"edits": []}


def test_set_command_in_an_included_file(ls):
    text = (TRACTOR / "powertrain.yaml").read_text(encoding="utf-8")
    part = ls.open((TRACTOR / "powertrain.yaml").as_uri(), text)
    a = ls.analysis(part)
    title = next(p for p in a.nodes if len(p) == 5 and p[2] == "devices" and p[-1] == "title")
    r = S.set_command(ls, {"uri": part, "path": list(title), "value": "New title"})
    assert "New title" in apply(text, r["edits"][0])
    r = S.set_command(ls, {"uri": part, "path": ["buses", 9, "title"], "value": "x"})
    assert r["edits"] == [] and r["error"]


def test_ops_command_in_an_included_file(ls):
    text = (TRACTOR / "powertrain.yaml").read_text(encoding="utf-8")
    part = ls.open((TRACTOR / "powertrain.yaml").as_uri(), text)
    a = ls.analysis(part)
    title = next(p for p in a.nodes if len(p) == 5 and p[2] == "devices" and p[-1] == "title")
    r = S.ops_command(ls, {"uri": part, "ops": [{"op": "set", "path": list(title), "value": "New title"}]})
    assert "New title" in apply(text, r["edit"])
    # The same value again: nothing to change
    assert S.ops_command(ls, {"uri": part, "ops": [{"op": "set", "path": list(title),
                                                    "value": E.raw_at(a, title)}]}) == {}


def test_render_and_drafts(ls, minimal, monkeypatch):
    assert S.render_command(ls, {"uri": minimal})["text"].startswith("#")
    assert "error" in S.render_command(ls, {"uri": NOT_MAP})

    old = MINIMAL.replace("name: pressure", "name: pressure_old")
    assert "pressure" in S.diff_command(ls, {"uri": minimal, "oldText": old})["text"]
    assert "error" in S.diff_command(ls, {"uri": NOT_MAP, "oldText": old})

    d = S.history_draft_command(ls, {"uri": minimal, "oldText": old})
    assert d["version"] == "0.1.1" and d["changes"] and d["date"]
    newer = MINIMAL.replace("version: 0.1.0", "version: 0.2.0")
    ls.change(minimal, newer)
    assert S.history_draft_command(ls, {"uri": minimal, "oldText": old})["version"] == "0.2.0"
    assert "error" in S.history_draft_command(ls, {"uri": minimal, "oldText": "mapcan: ["})
    assert "error" in S.history_draft_command(ls, {"uri": NOT_MAP, "oldText": old})

    d = S.release_draft_command(ls, {"uri": minimal, "oldText": None, "tags": ["v0.2.0"]})
    assert d["version"] == "0.2.1" and d["changes"] == []
    assert "error" in S.release_draft_command(ls, {"uri": minimal, "oldText": "mapcan: ["})
    assert "error" in S.release_draft_command(ls, {"uri": NOT_MAP})

    assert "error" in S.changes_command(ls, {"uri": NOT_MAP, "oldText": old})


def test_add_history_command(ls, minimal):
    r = S.add_history_command(ls, {"uri": minimal, "version": "0.2.0", "date": "2026-10-26",
                                   "author": "Me", "changes": ["One change"]})
    new = apply(MINIMAL, r["edit"])
    assert "version: 0.2.0" in new and "One change" in new and len(r["cursor"]) == 2
    assert "error" in S.add_history_command(ls, {"uri": NOT_MAP})
    one_line = MINIMAL.replace("  version: 0.1.0\n", "  history: [{version: 0.1.0, date: 2026-01-01, changes: [x]}]\n")
    ls.change(minimal, one_line)
    assert "error" in S.add_history_command(ls, {"uri": minimal, "version": "0.2.0", "changes": ["y"]})


def test_main_starts_the_server(monkeypatch):
    calls = []
    monkeypatch.setattr(S.server, "start_io", lambda: calls.append("io"))
    S.main()
    assert calls == ["io"]
