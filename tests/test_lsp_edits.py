"""Language server: quick fixes, references and renaming, edits of the map tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from mapcan.lsp import analysis as A
from mapcan.lsp import edits as E

from .conftest import ROOT

MINIMAL = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8")
VEHICLE = (ROOT / "examples" / "vehicle-can.yaml").read_text(encoding="utf-8")
DEV = ("buses", 0, "devices", 0)
FRAME = DEV + ("frames", 0)


def apply(text: str, edits: list[E.Edit]) -> str:
    """Apply the edits (in reverse order so that the positions do not shift)."""
    lines = text.splitlines(keepends=True)

    def offset(p: A.Pos) -> int:
        return sum(len(x) for x in lines[:p[0]]) + p[1] if p[0] < len(lines) else len(text)

    for e in sorted(edits, key=lambda e: offset(e.start), reverse=True):
        text = text[:offset(e.start)] + e.text + text[offset(e.end):]
    return text


def fixes(text: str) -> list[tuple[str, str, list[E.Edit]]]:
    a = A.analyze(text, "m.yaml")
    diags = [(d.code, d.node, (d.line - 1, (d.column or 1) - 1)) for d in a.diagnostics if d.line]
    return [(diags[act.diagnostics[0]][0], act.title, act.edits) for act in E.quick_fixes(a, diags)]


def fixed(text: str, code: str, title: str | None = None) -> str:
    for c, t, edits in fixes(text):
        if c == code and (title is None or t == title):
            return apply(text, edits)
    raise AssertionError(f"no fix for {code}: {[(c, t) for c, t, _ in fixes(text)]}")


def errors(text: str) -> list[str]:
    return [d.code for d in A.analyze(text, "m.yaml").diagnostics if d.level in ("error", "warning")]


# --------------------------------------------------------------------------- quick fixes


@pytest.mark.parametrize(("old", "new", "code"), [
    ("factor: 0.01", "factor: 0,01", "number-comma"),
    ("node_id: 0x21", "node_id: '0x21'", "number-quoted"),
    ("node_id: 0x21", "node_id: 0х21", "number-cyrillic-x"),
])
def test_number_fixes(old, new, code):
    assert fixed(MINIMAL.replace(old, new), code) == MINIMAL


def test_unknown_key_and_value_suggestions():
    text = MINIMAL.replace("representation: twos_complement", "representaton: twos_complement")
    assert fixed(text, "schema", "Change to 'representation'") == MINIMAL
    text = MINIMAL.replace("representation: twos_complement", "representation: twos_complemnt")
    assert fixed(text, "schema", "Change to 'twos_complement'") == MINIMAL


def test_dash_without_space():
    text = MINIMAL.replace("              - name: counter", "              -name: counter")
    assert fixed(text, "yaml", "Insert a space after '-'") == MINIMAL


def test_unknown_receiver_suggestion():
    text = VEHICLE.replace("receivers: [vcu, dashboard]", "receivers: [vcu, dashbord]")
    assert text != VEHICLE
    assert fixed(text, "unknown-receiver", "Change to 'dashboard'") == VEHICLE


def test_move_to_free_bits():
    text = MINIMAL.replace("start_bit: 56", "start_bit: 0")
    out = fixed(text, "bit-overlap", "Move to free bits: bits 56–59")
    assert out == MINIMAL


def test_extended_and_style_fixes():
    text = MINIMAL.replace("          - name: pump_state", (
        "          - name: Big_Frame\n            id: 0x900\n"
        "            signals: [{name: s, encoding: number, byte: 0, byte_length: 1}]\n"
        "          - name: pump_state"))
    out = fixed(fixed(text, "can-id-range"), "name-style")
    assert "extended: true" in out and "- name: big_frame" in out
    assert "can-id-range" not in errors(out) and "name-style" not in errors(out)


# --------------------------------------------------------------------------- references and renaming


def _pos(text: str, needle: str, offset: int = 0) -> A.Pos:
    lines = text.splitlines()
    i = next(i for i, line in enumerate(lines) if needle in line)
    return i, lines[i].index(needle) + offset


def test_definition_and_references_of_device():
    a = A.analyze(VEHICLE, "v.yaml")
    ref = _pos(VEHICLE, "receivers: [vcu", len("receivers: [") + 1)
    decl = E.definition(a, ref)
    assert a.lines[decl[0][0]].strip() == "- name: vcu"
    refs = E.references(a, ref)
    assert len(refs) >= 3 and decl in refs
    assert all(a.lines[s[0]][s[1]:e[1]] == "vcu" for s, e in refs)
    assert E.references(a, ref, include_declaration=False) == [r for r in refs if r != decl]


def test_rename_device_updates_references():
    a = A.analyze(VEHICLE, "v.yaml")
    out = apply(VEHICLE, E.rename_edits(a, E.name_at(a, _pos(VEHICLE, "- name: vcu", 9)), "ecu"))
    assert "vcu" not in out.replace("vcu_", "")
    assert errors(out) == errors(VEHICLE)


def test_rename_signal_is_local():
    a = A.analyze(MINIMAL, "m.yaml")
    path = E.name_at(a, _pos(MINIMAL, "- name: pressure", 9))
    assert path == FRAME + ("signals", 2, "name")
    out = apply(MINIMAL, E.rename_edits(a, path, "pressure out"))
    assert '- name: "pressure out"' in out


# --------------------------------------------------------------------------- edits of the tree


def _change(text: str, change: E.TextChange | None) -> str:
    assert change is not None
    e = E.minimal_edit(text, change.text)
    assert apply(text, [e]) == change.text
    return change.text


@pytest.mark.parametrize(("path", "kind", "line"), [
    (("buses", 0), "device", "      - name: device"),
    (DEV, "frame", "          - name: pump_frame"),
    (FRAME, "signal", "              - name: signal"),
])
def test_add_node(path, kind, line):
    a = A.analyze(MINIMAL, "m.yaml")
    change = E.add_node(a, path, kind)
    out = _change(MINIMAL, change)
    lines = out.splitlines()
    assert lines[change.cursor[0]].startswith(line)
    assert lines[change.cursor[0]][change.cursor[1]:] == line.split(": ")[1]
    assert [c for c in errors(out) if c not in errors(MINIMAL)] == []


def test_add_bus_and_device_get_titles():
    a = A.analyze(MINIMAL, "m.yaml")
    out = _change(MINIMAL, E.add_node(a, (), "bus"))
    assert out.endswith("  - name: bus\n    title: Bus 2\n    protocol: can\n")
    out = _change(MINIMAL, E.add_node(a, ("buses", 0), "device"))
    assert "      - name: device\n        title: Device 2\n        node_id: 0x01\n" in out
    assert "missing-title" not in [d.code for d in A.analyze(out, "m.yaml").diagnostics]


@pytest.mark.parametrize(("value", "text"), [
    ("Pump state", "Pump state"), ("Состояние насоса", "Состояние насоса"), ("on", '"on"'), ("0x10", '"0x10"'),
    ("a: b", '"a: b"'), ("x, y", '"x, y"'), ("- x", '"- x"'), ('say "hi"', 'say "hi"'), ("#1", '"#1"'),
])
def test_yaml_text(value, text):
    assert E.yaml_text(value) == text


def test_node_fields():
    a = A.analyze(MINIMAL, "m.yaml")
    f = E.node_fields(a, FRAME)
    assert (f["kind"], f["lang"], f["protocol"], f["owner"]) == ("frame", "en", "canopen", "pump")
    assert "frameDirection" not in f   # the form has no direction: it follows from the sender
    assert f["values"] == {"name": "pump_state", "canopen": "pdo_tx1", "description": "Pump state", "length": 8,
                           "cycle_ms": 100}
    assert f["devices"] == [{"name": "pump", "label": "PMP"}]
    assert E.node_fields(a, ("buses", 0))["values"]["title"] == "Demo bus"
    assert E.node_fields(a, FRAME + ("signals", 0))["units"][0] == ["В", "V"]
    assert E.node_fields(a, FRAME + ("signals",)) is None
    # Length of the signal from the parsed map (for the Byte order field) and whether the frame has a mux selector
    f = E.node_fields(a, FRAME + ("signals", 2))
    assert (f["bitLength"], f["hasSelector"]) == (16, False)
    pad = " " * 16
    b = A.analyze(MINIMAL.replace(f"{pad}byte: 0\n", f"{pad}byte: 0\n{pad}multiplexer: true\n", 1), "m.yaml")
    assert E.node_fields(b, FRAME + ("signals", 0))["hasSelector"] is False
    assert E.node_fields(b, FRAME + ("signals", 1))["hasSelector"] is True


def test_layout_and_tables():
    a = A.analyze(MINIMAL, "m.yaml")
    # The frame and its signal have one layout (as in the web editor): bits of the signals and flags
    frame = E.node_fields(a, FRAME)["frame"]
    assert (frame["name"], frame["length"], frame["path"]) == ("pump_state", 8, list(FRAME))
    assert [s["name"] for s in frame["signals"]][:3] == ["mode", "alarms", "pressure"]
    assert frame["signals"][1]["flags"][2]["occupied"] == [12, 13]
    f = E.node_fields(a, FRAME + ("signals", 0))
    assert f["frame"] == frame and f["palette"] and f["flags"] is None
    assert f["valueTable"][1] == {"key": "1", "value": 1, "name": "RUN", "description": "running",
                                  "raw": {"name": "RUN", "description": "running"}}
    f = E.node_fields(a, FRAME + ("signals", 1))
    assert f["valueTable"] is None
    assert [(x["bit"], x["bit_length"], x["name"]) for x in f["flags"]] == \
        [(0, None, "overheat"), (1, None, "dry_run"), (4, 2, "sensor_state")]
    # Value table of a flag
    flag = E.node_fields(a, FRAME + ("signals", 1, "flags", 2))
    assert [(r["value"], r["name"], r["raw"]) for r in flag["valueTable"]] == [(0, "OK", "OK"), (1, "OPEN", "OPEN"),
                                                                              (2, "SHORT", "SHORT")]
    assert E.node_fields(a, ("buses", 0))["frame"] is None


def test_apply_ops():
    a = A.analyze(MINIMAL, "m.yaml")
    sig = list(FRAME + ("signals", 0))
    out = E.apply_ops(a, [{"op": "set", "path": [*sig, "values", "3"], "value": "SERVICE"},
                          {"op": "rename_key", "path": [*sig, "values", "2"], "new_key": "5"}])
    assert "                  5: {name: FAULT, description: fault}\n                  3: SERVICE\n" in out
    # A new signal dragged on the grid: the insert and the position in one edit, the rest as it was
    n = len(E.raw_at(a, FRAME + ("signals",)))
    new = {"name": "extra", "encoding": "number"}
    out = E.apply_ops(a, [{"op": "insert", "path": [*FRAME, "signals"], "value": new},
                          {"op": "set_layout", "path": [*FRAME, "signals", n], "start_bit": 60, "bit_length": 4}])
    assert out.startswith(MINIMAL) and "              - name: extra\n" in out
    b = A.analyze(out, "m.yaml")
    assert errors(out) == errors(MINIMAL)
    extra = next(s for s in b.map.buses[0].devices[0].frames[0].signals if s.name == "extra")
    assert (extra.start_bit, extra.bit_length) == (60, 4)
    from mapcan.web.yamlops import OpError

    with pytest.raises(OpError):
        E.apply_ops(a, [{"op": "remove", "path": ["nope"]}])


def test_sdo_value_fields():
    text = (ROOT / "tests" / "data" / "reference.yaml").read_text(encoding="utf-8")
    a = A.analyze(text, "r.yaml")
    sdo = next(p for p in a.nodes if E.node_kind(p) == "sdo")
    f = E.node_fields(a, sdo)
    assert f["values"]["value.name"] == "alarm_resistance"
    assert (f["values"]["value.bit_length"], f["values"]["value.unit"]) == (16, "кОм")
    # A field of an existing value
    out = apply(text, E.set_field(a, sdo + ("value", "factor"), 0.1))
    # In its place in the canonical order (mapcan fmt): before the unit
    assert "bit_length: 16, factor: 0.1, unit: кОм," in out
    assert errors(out) == errors(text)
    # No value yet: the mapping is added together with the first field
    bare = next(p for p in a.nodes if E.node_kind(p) == "sdo" and E.raw_at(a, p + ("value",)) is None)
    out = apply(text, E.set_field(a, bare + ("value", "name"), "ack"))
    assert "value: {name: ack, encoding: number, bit_length: 32}" in out
    assert errors(out) == errors(text)
    assert E.set_field(a, bare + ("value", "name"), None) == []
    # The last field of the value is removed together with the mapping
    b = A.analyze(out, "r.yaml")
    assert apply(out, E.set_field(b, bare + ("value", "name"), None)) == text


def test_set_field():
    a = A.analyze(MINIMAL, "m.yaml")
    # A new field goes next to the other fields, before the list of signals
    out = apply(MINIMAL, E.set_field(a, FRAME + ("title",), "Pump state"))
    assert "            cycle_ms: 100\n            title: Pump state\n            signals:\n" in out
    out = apply(MINIMAL, E.set_field(a, FRAME + ("signals", 0, "unit"), "rpm"))
    assert "                byte_length: 1\n                unit: rpm\n                values:\n" in out
    out = apply(MINIMAL, E.set_field(a, DEV + ("node_id",), 0x22))
    assert "node_id: 0x22\n" in out
    out = apply(MINIMAL, E.set_field(a, FRAME + ("description",), None))
    assert "Pump state" not in out and errors(out) == errors(MINIMAL)
    out = apply(MINIMAL, E.set_field(a, FRAME + ("signals", 3, "representation"), "sign_magnitude"))
    assert "representation: sign_magnitude" in out
    out = apply(MINIMAL, E.set_field(a, FRAME + ("signals", 2, "factor"), 0.1))
    assert "factor: 0.1\n" in out
    # A device's name changes together with the references to it
    assert E.set_field(a, DEV + ("name",), "pump") == []
    assert [e.text for e in E.set_field(a, DEV + ("name",), "pump2")] == ["pump2"]
    # A text in several languages changes only in the document language
    text = MINIMAL.replace("    title: Demo bus", "    title: {ru: Шина, en: Demo bus}")
    b = A.analyze(text, "m.yaml")
    assert "    title: {ru: Шина, en: CAN 1}\n" in apply(text, E.set_field(b, ("buses", 0, "title"), "CAN 1"))
    # Receivers: a block list is replaced with "[…]"
    text = MINIMAL.replace("            cycle_ms: 100\n",
                           "            cycle_ms: 100\n            receivers:\n              - a\n")
    c = A.analyze(text, "m.yaml")
    out = apply(text, E.set_field(c, FRAME + ("receivers",), ["a", "b"]))
    assert "            receivers: [a, b]\n            signals:" in out


def test_add_signal_to_flow_list_and_empty_frame():
    text = MINIMAL.replace("          - name: pump_state", (
        "          - name: f2\n            id: 0x300\n"
        "            signals: [{name: a, encoding: number, byte: 0, byte_length: 1}]\n"
        "          - name: f3\n            id: 0x301\n            signals: []\n"
        "          - name: pump_state"))
    a = A.analyze(text, "m.yaml")
    out = _change(text, E.add_node(a, DEV + ("frames", 0), "signal"))
    assert ("signals: [{name: a, encoding: number, byte: 0, byte_length: 1}, "
            "{name: signal, encoding: number, byte: 1, byte_length: 1}]") in out
    out = _change(text, E.add_node(a, DEV + ("frames", 1), "signal"))
    assert ("            signals:\n              - name: signal\n                encoding: number\n"
            "                byte: 0\n                byte_length: 1\n") in out
    assert "empty-frame" not in [d.code for d in A.analyze(out, "m.yaml").diagnostics]


def test_add_signal_in_the_last_free_bits_by_bytes():
    """#117: a new signal within one byte is written by bytes, as the other editors write it."""
    a = A.analyze(MINIMAL, "m.yaml")
    out = _change(MINIMAL, E.add_node(a, FRAME, "signal"))
    assert ("              - name: signal\n                encoding: number\n"
            "                byte: 7\n                bit: 4\n                bit_length: 4\n") in out


def test_duplicate_and_delete():
    a = A.analyze(MINIMAL, "m.yaml")
    out = _change(MINIMAL, E.duplicate_node(a, DEV))
    assert "- name: pump_copy" in out and "node_id: 0x01" in out
    assert "duplicate-node-id" not in errors(out) and "duplicate-can-id" not in errors(out)
    out = _change(MINIMAL, E.duplicate_node(a, FRAME + ("signals", 1, "flags", 0)))
    assert "{name: overheat_copy, bit: 0" in out
    out = _change(MINIMAL, E.delete_node(a, FRAME + ("signals", 5)))
    assert "counter" not in out and errors(out) == errors(MINIMAL)
    out = _change(MINIMAL, E.delete_node(a, FRAME + ("signals", 1, "flags", 2)))
    assert "sensor_state" not in out and "dry_run" in out


def test_delete_last_item_leaves_empty_list():
    a = A.analyze(MINIMAL, "m.yaml")
    out = _change(MINIMAL, E.delete_node(a, FRAME))
    assert "        frames: []\n" in out and "schema" not in errors(out)


def test_edits_keep_crlf():
    text = MINIMAL.replace("\n", "\r\n")
    a = A.analyze(text, "m.yaml")
    change = E.add_node(a, FRAME, "signal")
    assert "\n" not in change.text.replace("\r\n", "")
    e = E.minimal_edit(text, change.text)
    assert e.start == e.end and e.text.endswith("\r\n")


def test_map_tree_nodes_have_paths():
    a = A.analyze(MINIMAL, "m.yaml")
    bus = A.map_tree(a)[0]
    assert bus["path"] == ["buses", 0]
    assert bus["children"][0]["children"][0]["path"] == list(FRAME)


def test_add_history_entry():
    entry = {"version": "0.2.0", "date": "2026-10-07", "author": "Jane Smith", "github": None}
    changes = ["0x1A1 pump_state: added signal speed (bits 40–55)"]
    # Without history: the list is created in document, the document's version and date come from the entry
    a = A.analyze(MINIMAL, "m.yaml")
    change = E.add_history(a, entry, changes)
    out = _change(MINIMAL, change)
    b = A.analyze(out, "r.yaml")
    assert b.map.document.version == "0.2.0" and str(b.map.document.date) == "2026-10-07"
    # ...and the version written in the document is removed
    assert not b.map.document._version_written and "version: 0.1.0" not in out
    first = b.map.document.history[0]
    assert (first.version, first.author, first.github) == ("0.2.0", "Jane Smith", None)
    assert first.changes == changes
    assert b.lines[change.cursor[0]].strip() == "- version: 0.2.0"
    # The new entry goes first, before the earlier ones
    entry2 = {**entry, "version": "0.3.0"}
    c = A.analyze(out, "r.yaml")
    out2 = _change(out, E.add_history(c, entry2, ["x"]))
    assert [h.version for h in A.analyze(out2, "r.yaml").map.document.history] == ["0.3.0", "0.2.0"]
    assert errors(out2) == errors(MINIMAL)
    # A one-line "[…]" entry is not extended
    flow = MINIMAL.replace("  version: 0.1.0\n", "  version: 0.1.0\n  history: [{version: 0.1.0}]\n")
    assert E.add_history(A.analyze(flow, "m.yaml"), entry, changes) is None


def test_new_frame_like_web_editor():
    # A frame of a CANopen device: the first free PDO type (pdo_tx1 is taken), the ID is computed
    a = A.analyze(MINIMAL, "m.yaml")
    out = _change(MINIMAL, E.add_node(a, DEV, "frame"))
    frame = A.analyze(out, "r.yaml").result.raw["buses"][0]["devices"][0]["frames"][-1]
    assert frame == {"name": "pump_frame", "canopen": "pdo_tx2", "length": 8, "cycle_ms": 100, "signals": []}
    # A frame of the bus: with an explicit ID
    bus_frame = _change(MINIMAL, E.add_node(a, ("buses", 0), "frame"))
    raw = A.analyze(bus_frame, "r.yaml").result.raw["buses"][0]["frames"][-1]
    assert raw["name"] == "frame" and isinstance(raw["id"], int) and "type" not in raw
    # J1939: a free PGN and a priority
    j1939 = (ROOT / "examples" / "j1939.yaml").read_text(encoding="utf-8")
    b = A.analyze(j1939, "j.yaml")
    dev = next(p for p in b.nodes if len(p) == 4 and p[2] == "devices")
    out = _change(j1939, E.add_node(b, dev, "frame"))
    raw = A.analyze(out, "r.yaml").result.raw
    frame = raw["buses"][dev[1]]["devices"][dev[3]]["frames"][-1]
    assert frame["pgn"] >= 0xFF00 and frame["priority"] == 6 and "id" not in frame


def test_frame_type_change_drops_invalid_dlc():
    text = MINIMAL.replace("            length: 8\n", "            length: 7\n", 1)
    a = A.analyze(text, "m.yaml")
    out = apply(text, E.set_field(a, FRAME + ("canopen",), "sdo_tx"))
    assert "canopen: sdo_tx\n" in out and "length: 7" not in out
    # An allowed DLC stays
    out = apply(text, E.set_field(a, FRAME + ("canopen",), "pdo_tx2"))
    assert "canopen: pdo_tx2\n" in out and "length: 7\n" in out


def test_frame_types_mark_taken_ids():
    a = A.analyze(MINIMAL, "m.yaml")
    types = {t["type"]: t["taken"] for t in E.frame_types(a, FRAME)}
    assert types["pdo_tx1"] is None             # the frame's own type is not taken by itself
    second = MINIMAL.replace("          - name: pump_state", (
        "          - name: other\n            canopen: pdo_tx2\n            signals: []\n          - name: pump_state"))
    b = A.analyze(second, "m.yaml")
    types = {t["type"]: t["taken"] for t in E.frame_types(b, DEV + ("frames", 1))}
    assert types["pdo_tx2"] == "other" and types["pdo_rx1"] is None
    # A frame of the bus has no node_id: only the types whose ID does not depend on the node
    bus_frame = E.frame_types(a, ("buses", 0, "frames", 0))
    assert [t["type"] for t in bus_frame] == ["", "nmt", "sync", "time"]


def test_duplicate_pdo_type_quick_fix():
    text = MINIMAL + ("          - name: pump_frame\n            canopen: pdo_tx1\n            length: 8\n"
                      "            signals: []\n")
    # The first (preferred) one is a free PDO of the same direction; PDO RX is not offered
    assert "            canopen: pdo_tx2\n            length: 8\n" in fixed(text, "duplicate-can-id")
    titles = [t for c, t, _ in fixes(text) if c == "duplicate-can-id"]
    assert titles and all("pdo_tx" in t for t in titles)


INCLUDING_MAIN = """mapcan: 2
document: {title: Example, language: en}
include: [devices/node.yaml]
buses:
  - name: can1
    title: CAN 1
    protocol: canopen
    bitrate: 500000
    devices: []
"""
INCLUDED_NODE = """mapcan: 2
part_of: ../main.yaml
buses:
  - name: can1
    devices:
      - name: node
        title: Node
        node_id: 0x10
        frames:
          - name: state
            canopen: pdo_tx1
            signals: []
"""


def test_frame_types_of_a_frame_in_an_included_file(tmp_path):
    """#133: the form offers all the CANopen functions to a frame of a device of an included file."""
    (tmp_path / "devices").mkdir()
    (tmp_path / "main.yaml").write_text(INCLUDING_MAIN, encoding="utf-8")
    (tmp_path / "devices" / "node.yaml").write_text(INCLUDED_NODE, encoding="utf-8")
    a = A.analyze(INCLUDING_MAIN, str(tmp_path / "main.yaml"))
    fields = E.node_fields(a, FRAME)
    assert fields["file"] and fields["values"]["canopen"] == "pdo_tx1"
    types = {t["type"]: t["taken"] for t in fields["frameTypes"]}
    assert {"nmt", "emcy", "pdo_tx1", "pdo_rx4", "sdo_tx", "heartbeat"} <= set(types)
    assert types["pdo_tx1"] is None
    # The same in the included file opened on its own
    part = A.analyze_part(INCLUDED_NODE, str(tmp_path / "devices" / "node.yaml"))
    assert {t["type"] for t in E.node_fields(part, FRAME)["frameTypes"]} == set(types)


def test_set_sender_leaves_the_receivers():
    """A device named as a frame's sender does not receive it: the form's Sender field takes it out of receivers."""
    from .conftest import one_bus

    text = one_bus("""
        - name: f
          id: 0x300
          length: 1
          receivers: [master, panel]
    """, protocol="can",
        devices_extra="      - name: master\n        frames: []\n      - name: panel\n        frames: []\n")
    a = A.analyze(text, "t.yaml")
    frame = ("buses", 0, "devices", 0, "frames", 0)
    out = apply(text, E.set_field(a, frame + ("sender",), "master"))
    assert "sender: master" in out and "receivers: [panel]" in out and errors(out) == []
    b = A.analyze(out, "t.yaml")
    out2 = apply(out, E.set_field(b, frame + ("sender",), "panel"))
    assert "sender: panel" in out2 and "receivers" not in out2
    # Back to the device itself: the key goes
    c = A.analyze(out2, "t.yaml")
    assert "sender" not in apply(out2, E.set_field(c, frame + ("sender",), None))


# --------------------------------------------------------------------------- more quick fixes

J1939 = (ROOT / "examples" / "j1939.yaml").read_text(encoding="utf-8")
FLAG = FRAME + ("signals", 1, "flags", 0)       # {name: overheat, bit: 0, description: overheating}


def test_remove_destination_of_a_pdu2_pgn():
    text = J1939.replace("pgn: 0xF004\n", "pgn: 0xF004\n            destination: 0x10\n", 1)
    assert fixed(text, "j1939-destination", "Remove destination") == J1939


def test_document_version_and_history_fixes():
    hist = "  history:\n    - version: 0.2.0\n      date: 2026-10-01\n      changes: [First]\n"
    text = MINIMAL.replace("  language: en\n", "  language: en\n" + hist)
    # The version differs from the latest entry: take the entry's
    out = fixed(text, "history-version")
    assert "  version: 0.2.0\n" in out and "history-version" not in errors(out)
    # Now it repeats the entry: remove it
    out = fixed(out, "version-redundant")
    assert "  version:" not in out.split("  history:")[0] and "version-redundant" not in errors(out)
    # Without a written version there is nothing to change to
    a = A.analyze(text.replace("  version: 0.1.0\n", ""), "m.yaml")
    assert E._fixes_for(a, "history-version", ("document", "version")) == []


def test_value_name_style_fixes():
    # The name of a value written as {name: …} and as the value's string itself
    assert fixed(MINIMAL.replace("name: RUN,", "name: Run,"), "name-style") == MINIMAL
    assert fixed(MINIMAL.replace("1: OPEN,", "1: Open,"), "name-style") == MINIMAL
    text = MINIMAL.replace("mapcan: 2\n", "mapcan: 2\nlint: {frame_name: PascalCase, signal_name: camelCase}\n")
    out = fixed(fixed(text, "name-style", "Rename to 'PumpState'"), "name-style", "Rename to 'dryRun'")
    assert "- name: PumpState" in out and "{name: dryRun," in out


def test_to_style():
    assert E.to_style("pumpState", "snake_case") == "pump_state"
    assert E.to_style("pump state", "UPPER_SNAKE") == "PUMP_STATE"
    assert E.to_style("Pump_State", "camelCase") == "pumpState"
    assert E.to_style("pump_state", "PascalCase") == "PumpState"
    assert E.to_style("---", "camelCase") == "---"
    assert E.to_style("pump_state", "any") == "pump_state"


def test_unknown_key_of_a_block_mapping():
    # The value of the key starts on the next line: the key is found above it
    assert fixed(MINIMAL.replace("                values:\n", "                valuez:\n"), "schema",
                 "Change to 'values'") == MINIMAL


def test_fixes_that_find_nothing_to_offer():
    a = A.analyze(MINIMAL, "m.yaml")
    sig = FRAME + ("signals", 0)
    assert E._fixes_for(a, "number-comma", sig + ("byte",)) == []          # the number is fine
    assert E._fixes_for(a, "unknown-receiver", sig) == []                 # not a name
    assert E._fixes_for(a, "schema", sig + ("encoding",)) == []           # a valid value
    assert E._fixes_for(a, "name-style", sig + ("name",)) == []           # already in style
    assert E._fixes_for(a, "deprecated-key", ()) == []                    # nothing to migrate
    assert E._fixes_for(a, "format-v1", ()) == []
    assert E._fixes_for(a, "direction-deprecated", ()) == []
    assert E._fixes_for(a, "version-redundant", ()) == []
    assert E._fixes_for(a, "j1939-destination", sig) == []
    assert E._fixes_for(a, "bit-overlap", sig + ("byte",)) == []           # not a signal
    assert E._yaml_fixes(a, (0, 0)) == [] and E._yaml_fixes(a, (999, 0)) == []


def test_move_to_free_bits_by_byte_and_bit():
    # Written with byte and bit: moved to the free bits, both fields rewritten
    text = MINIMAL.replace("                start_bit: 56\n", "                byte: 0\n                bit: 2\n")
    out = fixed(text, "bit-overlap")
    assert "                byte: 7\n                bit: 0\n" in out and "bit-overlap" not in errors(out)
    # Written with byte only: moved by whole bytes
    text = MINIMAL.replace("                byte: 5\n", "                byte: 4\n")
    assert fixed(text, "bit-overlap", "Move to free bits: bits 40–55") == MINIMAL


def test_free_start_with_multiplexed_signals():
    a = A.analyze(MINIMAL, "m.yaml")
    frame = E._find(a.map, FRAME)
    assert E.free_start(frame, 4, 1) == 60
    assert E.free_start(frame, 8, 8) is None
    one, other = frame.signals[0].model_copy(update={"mux": 1}), frame.signals[1].model_copy(update={"mux": 2})
    assert not E._coexist(one, other) and E._coexist(one, frame.signals[2])


def test_insert_and_delete_keys_of_a_flow_mapping():
    a = A.analyze(MINIMAL, "m.yaml")
    line = MINIMAL.splitlines().index("                  - {name: overheat, bit: 0, description: overheating}")

    def edited(edits):
        return apply(MINIMAL, edits).splitlines()[line].strip()

    # Before the key that follows it in the canonical order, or at the end of the braces
    assert edited(E.insert_key(a, FLAG, "bit_length", "1")) == \
        "- {name: overheat, bit: 0, bit_length: 1, description: overheating}"
    assert edited(E.insert_key(a, FLAG, "zzz", "1")) == "- {name: overheat, bit: 0, description: overheating, zzz: 1}"
    # The first key takes its comma with it, the last one the comma before it
    assert edited(E.delete_key(a, FLAG + ("name",))) == "- {bit: 0, description: overheating}"
    assert edited(E.delete_key(a, FLAG + ("description",))) == "- {name: overheat, bit: 0}"
    # A key on a "- " line, or one that is not written, is not deleted
    assert E.delete_key(a, FRAME + ("signals", 0, "name")) == []
    assert E.delete_key(a, FLAG + ("nope",)) == []
    assert E.insert_key(a, FRAME + ("nope",), "x", "1") == []


def test_insert_key_keeps_the_comment_above_its_neighbour():
    text = MINIMAL.replace("            canopen: pdo_tx1\n            length: 8\n",
                           "            # the full frame\n            length: 8\n")
    a = A.analyze(text, "m.yaml")
    out = apply(text, E.insert_key(a, FRAME, "canopen", "pdo_tx1"))
    assert out == MINIMAL.replace("            length: 8\n", "            # the full frame\n            length: 8\n")


# --------------------------------------------------------------------------- more edits of the tree and the form

FLOW = MINIMAL.replace("          - name: pump_state", (
    "          - name: aux\n            canopen: pdo_tx2\n            length: 2\n"
    "            signals: [{name: a, encoding: number, byte: 0, byte_length: 1},"
    " {name: b, encoding: number, byte: 1, byte_length: 1}]\n"
    "          - name: pump_state"))
AUX = DEV + ("frames", 0)


def _line_of(text: str, needle: str) -> str:
    return next(line for line in text.splitlines() if needle in line).strip()


def test_duplicate_and_delete_in_a_flow_list():
    a = A.analyze(FLOW, "m.yaml")
    copy = _change(FLOW, E.duplicate_node(a, AUX + ("signals", 0)))
    assert _line_of(copy, "signals: [").startswith(
        "signals: [{name: a, encoding: number, byte: 0, byte_length: 1}, {name: a_copy, ")
    first = _change(FLOW, E.delete_node(a, AUX + ("signals", 0)))
    assert _line_of(first, "signals: [") == "signals: [{name: b, encoding: number, byte: 1, byte_length: 1}]"
    last = _change(FLOW, E.delete_node(a, AUX + ("signals", 1)))
    assert _line_of(last, "signals: [") == "signals: [{name: a, encoding: number, byte: 0, byte_length: 1}]"


def test_duplicates_get_free_numbers():
    a = A.analyze(MINIMAL, "m.yaml")
    copy = _change(MINIMAL, E.duplicate_node(a, DEV))
    assert "      - name: pump_copy\n        short: PMP\n        title: Pump\n        node_id: 0x01\n" in copy
    v = A.analyze(VEHICLE, "v.yaml")
    copy = _change(VEHICLE, E.duplicate_node(v, ("buses", 0, "devices", 0, "frames", 0)))
    # A frame with an explicit ID gets the next free one after the highest 11-bit ID of the bus
    used = {f.can_id for f in v.map.buses[0].all_frames()}
    new_id = int(_line_of(copy.split("_copy\n", 1)[1], "id: 0x").split()[1], 16)
    assert new_id == max(i for i in used if i <= 0x7FF) + 1 and new_id not in used
    # Not a list item, or not a node: nothing
    assert E.duplicate_node(a, FRAME + ("name",)) is None and E.duplicate_node(a, ("buses", 9)) is None
    assert E.delete_node(a, ("buses", 9)) is None


def test_add_node_refuses_what_does_not_belong():
    a = A.analyze(MINIMAL, "m.yaml")
    assert E.add_node(a, FRAME, "bus") is None
    assert E.add_node(a, FRAME, "device") is None
    assert E.add_node(a, ("buses", 9), "device") is None


def test_set_field_lists():
    a = A.analyze(MINIMAL, "m.yaml")
    out = apply(MINIMAL, E.set_field(a, FRAME + ("receivers",), ["x", "y"]))
    assert "            cycle_ms: 100\n            receivers: [x, y]\n" in out
    block = MINIMAL.replace("            cycle_ms: 100\n", "            cycle_ms: 100\n            receivers:\n"
                                                          "              - x\n              - y\n")
    a = A.analyze(block, "m.yaml")
    out = apply(block, E.set_field(a, FRAME + ("receivers",), ["z"]))
    assert "            receivers: [z]\n            signals:" in out
    flow = MINIMAL.replace("            cycle_ms: 100\n", "            cycle_ms: 100\n            receivers: [x, y]\n")
    a = A.analyze(flow, "m.yaml")
    assert "            receivers: [z]\n" in apply(flow, E.set_field(a, FRAME + ("receivers",), ["z"]))


def test_set_field_unchanged_and_texts_in_languages():
    a = A.analyze(MINIMAL, "m.yaml")
    assert E.set_field(a, FRAME + ("signals", 0, "name"), "mode") == []
    assert E.set_field(a, FRAME + ("cycle_ms",), 100) == []
    assert E.set_field(a, FRAME + ("signals", 0), "x") == []
    assert E.set_field(a, FRAME + ("nope",), None) == []
    text = MINIMAL.replace("        title: Pump\n", "        title: {en: Pump, ru: Насос}\n")
    a = A.analyze(text, "m.yaml")
    # Only the text in the document language changes or goes
    assert "title: {en: Main pump, ru: Насос}" in apply(text, E.set_field(a, DEV + ("title",), "Main pump"))
    assert "title: {ru: Насос}" in apply(text, E.set_field(a, DEV + ("title",), None))
    assert E.set_field(a, DEV + ("title",), "Pump") == []


def test_routed_ops_errors(tmp_path):
    from mapcan.web.yamlops import OpError

    a = A.analyze(MINIMAL, "m.yaml")
    with pytest.raises(OpError):
        E.routed_ops(a, [{"op": "set", "path": "buses.0", "value": 1}], A.read_disk)
    main = ROOT / "examples" / "tractor" / "tractor.yaml"
    a = A.analyze(main.read_text(encoding="utf-8"), str(main))
    title = ["buses", 0, "devices", 1, "title"]        # the gateway, in powertrain.yaml
    with pytest.raises(OpError, match="powertrain.yaml"):
        E.routed_ops(a, [{"op": "set", "path": title, "value": "x"}], lambda f: None)
    text, others = E.routed_ops(a, [{"op": "set", "path": title, "value": "x"}], A.read_disk)
    assert text == a.text and [Path(f).name for f in others] == ["powertrain.yaml"]
