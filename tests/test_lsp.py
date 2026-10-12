"""Language server: text analysis (diagnostics, outline, hover, inlay hints, completion) and the protocol."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from mapcan.lsp import analysis as A

from .conftest import ROOT, one_bus

MINIMAL = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8")
LINES = MINIMAL.splitlines()


def at(sub: str, offset: int = 1) -> A.Pos:
    i = next(i for i, line in enumerate(LINES) if sub in line)
    return i, LINES[i].index(sub) + offset


@pytest.fixture(scope="module")
def minimal() -> A.Analysis:
    return A.analyze(MINIMAL, "minimal.yaml")


def test_is_mapcan():
    assert A.is_mapcan(MINIMAL)
    assert not A.is_mapcan("canmap: 1\n")
    assert not A.is_mapcan("name: build\non: push\n")


def test_diagnostics_have_ranges():
    text = one_bus("""
        - name: st
          type: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: raw, byte: 0, bit_length: 99999}
    """)
    a = A.analyze(text, "t.yaml")
    d = next(d for d in a.diagnostics if d.code == "schema")
    start, end = A.diagnostic_range(a, d)
    assert a.lines[start[0]][start[1]:end[1]] == "99999"


def test_yaml_error_is_reported():
    a = A.analyze(MINIMAL.replace("cycle_ms: 100", "cycle_ms: [100"), "t.yaml")
    assert [d.code for d in a.diagnostics] == ["yaml"]
    assert a.map is None and A.inlay_hints(a) == []


def test_symbols(minimal):
    (bus,) = A.symbols(minimal)
    assert (bus.kind, bus.name, bus.detail) == ("bus", "demo", "canopen")
    frame = bus.children[0].children[0]
    assert (frame.kind, frame.name, frame.detail) == ("frame", "pump_state", "0x1A1")
    assert frame.children[2].detail == "scaled · bits 16–31"
    assert [s.name for s in frame.children] == ["mode", "alarms", "pressure", "temperature", "speed", "counter"]
    assert [f.name for f in frame.children[1].children] == ["overheat", "dry_run", "sensor_state"]
    sel = frame.selection
    assert LINES[sel[0][0]][sel[0][1]:sel[1][1]] == "pump_state"


def _flat(nodes: list[dict], depth: int = 0) -> list[tuple]:
    out = []
    for n in nodes:
        out.append((depth, n["kind"], n.get("dir"), n["label"], n["description"], n.get("from")))
        out.extend(_flat(n["children"], depth + 1))
    return out


def test_map_tree_matches_web_editor(minimal):
    rows = _flat(A.map_tree(minimal))
    assert rows[:5] == [
        (0, "bus", None, "Demo bus", "", None),
        (1, "device", None, "PMP · Pump", "0x21", None),
        (2, "frame", "tx", "pump_state", "0x1A1", None),
        (3, "signal", None, "mode", "0–7", None),
        (3, "signal", None, "alarms", "8–15", None),
    ]
    assert (4, "flag", None, "sensor_state", "bit 4", None) in rows
    assert (3, "signal", None, "speed", "40–55", None) in rows


def _selected(a: A.Analysis, node: dict) -> str:
    sl, sc, el, ec = node["selection"]
    if sl == el:
        return a.lines[sl][sc:ec]
    return "\n".join([a.lines[sl][sc:], *a.lines[sl + 1:el], a.lines[el][:ec]])


def test_map_tree_selects_whole_blocks():
    text = MINIMAL.replace("                bit_length: 4\n", (
        "                bit_length: 4   # last\n\n"
        "          # next frame\n"
        "          - name: f2\n"
        "            id: 0x300\n"
        "            signals: [{name: a, encoding: raw, byte: 0, byte_length: 1},\n"
        "                      {name: b, encoding: raw, byte: 1, byte_length: 1}]\n"
        "            sdo:\n"
        "              - {name: x, command: 0x40, index: 0x1000}\n"))
    a = A.analyze(text, "t.yaml")
    device = A.map_tree(a)[0]["children"][0]
    frame, f2 = device["children"]
    block = _selected(a, frame)
    assert block.startswith("name: pump_state") and block.endswith("bit_length: 4")
    sig = _selected(a, frame["children"][0])
    assert sig.startswith("name: mode") and sig.endswith("{name: FAULT, description: fault}")
    flag = frame["children"][1]["children"][2]
    assert _selected(a, flag) == ("{bit: 4, bit_length: 2, name: sensor_state,\n"
                                  "                     values: {0: OK, 1: OPEN, 2: SHORT}}")
    assert [_selected(a, s) for s in f2["children"]] == [
        "{name: a, encoding: raw, byte: 0, byte_length: 1}", "{name: b, encoding: raw, byte: 1, byte_length: 1}",
        "{name: x, command: 0x40, index: 0x1000}"]
    assert frame["range"][1] == 0   # the cursor on the "- " before the frame is inside the node too


def test_map_tree_received_frames_and_pgn():
    a = A.analyze((ROOT / "examples" / "j1939.yaml").read_text(encoding="utf-8"), "j1939.yaml")
    rows = _flat(A.map_tree(a))
    # Labels are titles for people, as in the web editor; a received frame shows its sender
    assert (2, "frame", "tx", "EEC1", "PGN 0xF004", None) in rows
    assert (2, "frame", "rx", "ECU · EEC1", "0x0CF00400", "ECU") in rows
    assert (1, "device", None, "ECU · Engine control unit", "SA 0x00", None) in rows
    assert A.map_tree(a)[0]["children"][0]["ident"] == "engine"


def test_symbols_survive_model_errors():
    a = A.analyze(MINIMAL.replace("byte: 4\n", "byte: 4\n                bit_length: 99\n"), "t.yaml")
    assert a.map is None
    assert A.symbols(a)[0].children[0].children[0].name == "pump_state"


def test_hover_field_description(minimal):
    assert A.hover(minimal, at("node_id")) == ("**node_id** — CANopen node address 1..127 (0x01..0x7F). Added to the "
                                               "base ID of PDO, SDO, EMCY and Heartbeat frames.")
    assert A.hover(minimal, at("start_bit")).startswith("**start_bit** — ")


def test_hover_signal_and_frame(minimal):
    sig = A.hover(minimal, at("name: pressure", 8))
    assert sig.startswith("**pressure** · `scaled` · bits 16–31 · 16 bit")
    assert "phys = raw × 0.01 + 0" in sig and "unit: bar" in sig
    frame = A.hover(minimal, at("name: pump_state", 8))
    assert frame.startswith("**pump_state** · `0x1A1` · DLC 8")
    assert "| 7 | · | · | · | · | 6 | 6 | 6 | 6 |" in frame
    assert "5. `speed` — bits 47…48 (BE)" in frame


def test_hover_enum_values(minimal):
    md = A.hover(minimal, at("name: mode", 8))
    assert "| 0 | OFF |" in md and "| 2 | FAULT |" in md


def test_inlay_hints(minimal):
    hints = {(LINES[h.pos[0]][:h.pos[1]].strip(), h.label) for h in A.inlay_hints(minimal)}
    assert ("- name: pump_state", "→ 0x1A1") in hints
    assert ("- name: mode", "bits 0–7") in hints
    assert ("- name: counter", "bits 56–59") in hints


def test_inlay_hint_skips_explicit_id():
    a = A.analyze(one_bus("""
        - name: st
          id: 0x123
          length: 8
          signals: [{name: a, encoding: raw, byte: 0, byte_length: 1}]
    """), "t.yaml")
    assert [h.label for h in A.inlay_hints(a)] == ["bits 0–7"]


@pytest.mark.parametrize(("line", "key", "expected"), [
    ("    encoding: ", "encoding", "bitfield"),
    ("    byte_order: b", "byte_order", "big_endian"),
    ("    - {name: a, encoding: ", "encoding", "float"),
    ("    protocol: ", "protocol", "j1939"),
    ("    receivers: [pump, ", "receivers", "pump"),
    ("    sender: ", "sender", "pump"),
])
def test_completions(minimal, line, key, expected):
    found = A.completions("x:\n" + line, (1, len(line)), minimal)
    assert found is not None and found[0] == key and expected in found[1]


def test_completions_block_receivers(minimal):
    text = "x:\n    receivers:\n      - vcu\n      - "
    assert A.completions(text, (3, 8), minimal) == ("receivers", ["pump"])


def test_no_completion_for_free_text(minimal):
    assert A.completions("x:\n    description: ", (1, 17), minimal) is None


def test_export_unsaved_text(tmp_path):
    from mapcan.lsp.exports import export

    text = MINIMAL.replace("title: Example map", "title: Edited in the editor")
    files, warnings = export(text, str(tmp_path / "pump.yaml"), ["md", "dbc", "c"], tmp_path / "build")
    names = sorted(f.relative_to(tmp_path / "build").as_posix() for f in files)
    assert names == ["c/demo.c", "c/demo.h", "dbc/demo.dbc", "pump.md"]
    assert "Edited in the editor" in (tmp_path / "build" / "pump.md").read_text(encoding="utf-8")
    assert warnings == []


def test_export_refuses_invalid_map(tmp_path):
    from mapcan.lsp.exports import ExportError, export

    with pytest.raises(ExportError, match="errors"):
        export(MINIMAL.replace("byte: 4\n", "byte: 4\n                bit_length: 99\n"),
               str(tmp_path / "m.yaml"), ["md"], tmp_path)
    with pytest.raises(ExportError, match="unknown formats"):
        export(MINIMAL, str(tmp_path / "m.yaml"), ["docx"], tmp_path)


def _frame(payload: dict) -> bytes:
    body = json.dumps(payload).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


def _read(stream) -> dict:
    length = 0
    while (line := stream.readline().strip()):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":")[1])
    return json.loads(stream.read(length))


def test_server_protocol(tmp_path):
    pytest.importorskip("pygls")
    uri = (tmp_path / "m.yaml").as_uri()
    text = MINIMAL.replace("byte: 4\n", "byte: 4\n                bit_length: 99\n")
    proc = subprocess.Popen([sys.executable, "-m", "mapcan.cli", "lsp"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, cwd=ROOT)
    try:
        send = proc.stdin.write
        send(_frame({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"processId": None, "rootUri": None, "capabilities": {}}}))
        send(_frame({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
        send(_frame({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {
            "textDocument": {"uri": uri, "languageId": "yaml", "version": 1, "text": text}}}))
        send(_frame({"jsonrpc": "2.0", "id": 2, "method": "textDocument/hover", "params": {
            "textDocument": {"uri": uri}, "position": {"line": at("node_id")[0], "character": at("node_id")[1]}}}))
        proc.stdin.flush()
        msgs: list[dict] = []
        while not {1, 2} <= {m.get("id") for m in msgs} and len(msgs) < 10:
            msgs.append(_read(proc.stdout))
        init = next(m for m in msgs if m.get("id") == 1)
        caps = init["result"]["capabilities"]
        assert caps["hoverProvider"] and caps["documentSymbolProvider"] and caps["inlayHintProvider"]
        diags = next(m for m in msgs if m.get("method") == "textDocument/publishDiagnostics")["params"]
        assert diags["uri"] == uri and diags["diagnostics"][0]["code"] == "schema"
        hover = next(m for m in msgs if m.get("id") == 2)["result"]["contents"]["value"]
        assert hover.startswith("**node_id**")
    finally:
        proc.kill()
        proc.wait()


def test_diff_command_compares_two_versions():
    pytest.importorskip("pygls")
    from mapcan.lsp.server import diff_command

    old = MINIMAL.replace("name: pressure", "name: pressure_old")
    assert "pressure" in diff_command(None, {"oldText": old, "newText": MINIMAL})["text"]
    assert "error" in diff_command(None, {"oldText": "mapcan: [", "newText": MINIMAL})


class _Server:
    """A server with one open document, to call the commands without the protocol."""

    def __init__(self, text: str):
        self.a = A.analyze(text, "m.yaml")

    def analysis(self, uri: str):
        return self.a if uri == "file:///m.yaml" else None


def test_ops_and_changes_commands():
    pytest.importorskip("pygls")
    from mapcan.lsp.server import changes_command, ops_command, release_draft_command

    ls = _Server(MINIMAL)
    frame = ["buses", 0, "devices", 0, "frames", 0]
    r = ops_command(ls, {"uri": "file:///m.yaml", "ops": [
        {"op": "set", "path": [*frame, "signals", 0, "values", "3"], "value": "SERVICE"}]})
    (sl, _, el, _), text = r["edit"]["range"], r["edit"]["text"]
    assert sl == el and text.strip() == "3: SERVICE"
    assert ops_command(ls, {"uri": "file:///m.yaml", "ops": []}) == {}
    assert "error" in ops_command(ls, {"uri": "file:///m.yaml", "ops": [{"op": "remove", "path": ["nope"]}]})
    assert "error" in ops_command(ls, {"uri": "file:///other.yaml", "ops": []})

    old = MINIMAL.replace("{name: RUN, description: running}", "{name: RUNNING, description: running}")
    nodes = changes_command(ls, {"uri": "file:///m.yaml", "oldText": old})["nodes"]
    assert nodes == [{"path": [*frame, "signals", 0], "status": "modified"}]
    assert changes_command(ls, {"uri": "file:///m.yaml", "oldText": MINIMAL})["nodes"] == []
    assert "error" in changes_command(ls, {"uri": "file:///m.yaml", "oldText": "mapcan: ["})

    d = release_draft_command(ls, {"uri": "file:///m.yaml", "oldText": old, "tags": []})
    assert d["changes"] and d["date"] and not d["recorded"]
