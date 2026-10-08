"""Языковой сервер: быстрые исправления, ссылки и переименование, правки дерева карты."""

from __future__ import annotations

import pytest

from mapcan.lsp import analysis as A
from mapcan.lsp import edits as E

from .conftest import ROOT

MINIMAL = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8")
VEHICLE = (ROOT / "examples" / "vehicle-can.yaml").read_text(encoding="utf-8")
DEV = ("buses", 0, "devices", 0)
FRAME = DEV + ("frames", 0)


def apply(text: str, edits: list[E.Edit]) -> str:
    """Применить правки (в обратном порядке, чтобы позиции не сдвигались)."""
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
    text = MINIMAL.replace("byte_order: big_endian", "byte_ordr: big_endian")
    assert fixed(text, "schema", "Change to 'byte_order'") == MINIMAL
    text = MINIMAL.replace("byte_order: big_endian", "byte_order: big_endain")
    assert fixed(text, "schema", "Change to 'big_endian'") == MINIMAL


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
        "          - name: Big_Frame\n            id: 0x900\n            signals: [{name: s, encoding: raw, byte: 0, byte_length: 1}]\n"
        "          - name: pump_state"))
    out = fixed(fixed(text, "can-id-range"), "name-style")
    assert "extended: true" in out and "- name: big_frame" in out
    assert "can-id-range" not in errors(out) and "name-style" not in errors(out)


# --------------------------------------------------------------------------- ссылки и переименование


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


# --------------------------------------------------------------------------- правки дерева


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
    assert f["frameDirection"] == "tx"   # не записано: из типа pdo_tx1
    assert f["values"] == {"name": "pump_state", "type": "pdo_tx1", "description": "Pump state", "dlc": 8,
                           "cycle_ms": 100}
    assert f["devices"] == [{"name": "pump", "label": "PMP"}]
    assert E.node_fields(a, ("buses", 0))["values"]["title"] == "Demo bus"
    assert E.node_fields(a, FRAME + ("signals", 0))["units"][0] == ["В", "V"]
    assert E.node_fields(a, FRAME + ("signals",)) is None
    # Длина сигнала из разобранной карты (для поля «Порядок байт») и наличие селектора mux в кадре
    f = E.node_fields(a, FRAME + ("signals", 2))
    assert (f["bitLength"], f["hasSelector"]) == (16, False)
    pad = " " * 16
    b = A.analyze(MINIMAL.replace(f"{pad}byte: 0\n", f"{pad}byte: 0\n{pad}multiplexer: true\n", 1), "m.yaml")
    assert E.node_fields(b, FRAME + ("signals", 0))["hasSelector"] is False
    assert E.node_fields(b, FRAME + ("signals", 1))["hasSelector"] is True


def test_layout_and_tables():
    a = A.analyze(MINIMAL, "m.yaml")
    # Кадр и его сигнал — одна раскладка (как в веб-редакторе): биты сигналов и флагов
    frame = E.node_fields(a, FRAME)["frame"]
    assert (frame["name"], frame["dlc"], frame["path"]) == ("pump_state", 8, list(FRAME))
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
    # Таблица значений флага
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
    # Новый сигнал перетаскиванием по сетке: вставка и позиция в одной правке, остальное — как было
    n = len(E.raw_at(a, FRAME + ("signals",)))
    out = E.apply_ops(a, [{"op": "insert", "path": [*FRAME, "signals"], "value": {"name": "extra", "encoding": "raw"}},
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
    # Поле существующего значения
    out = apply(text, E.set_field(a, sdo + ("value", "factor"), 0.1))
    assert "изоляции, factor: 0.1}" in out
    assert errors(out) == errors(text)
    # Значения ещё нет: словарь добавляется вместе с первым полем
    bare = next(p for p in a.nodes if E.node_kind(p) == "sdo" and E.raw_at(a, p + ("value",)) is None)
    out = apply(text, E.set_field(a, bare + ("value", "name"), "ack"))
    assert "value: {name: ack, encoding: raw, bit_length: 32}" in out
    assert errors(out) == errors(text)
    assert E.set_field(a, bare + ("value", "name"), None) == []
    # Последнее поле значения удаляется вместе со словарём
    b = A.analyze(out, "r.yaml")
    assert apply(out, E.set_field(b, bare + ("value", "name"), None)) == text


def test_set_field():
    a = A.analyze(MINIMAL, "m.yaml")
    # Новое поле — рядом с остальными полями, перед списком сигналов
    out = apply(MINIMAL, E.set_field(a, FRAME + ("title",), "Pump state"))
    assert "            cycle_ms: 100\n            title: Pump state\n            signals:\n" in out
    out = apply(MINIMAL, E.set_field(a, FRAME + ("signals", 0, "unit"), "rpm"))
    assert "                byte_length: 1\n                unit: rpm\n                values:\n" in out
    out = apply(MINIMAL, E.set_field(a, DEV + ("node_id",), 0x22))
    assert "node_id: 0x22\n" in out
    out = apply(MINIMAL, E.set_field(a, FRAME + ("description",), None))
    assert "Pump state" not in out and errors(out) == errors(MINIMAL)
    out = apply(MINIMAL, E.set_field(a, FRAME + ("signals", 3, "signed"), False))
    assert "signed: false" in out
    out = apply(MINIMAL, E.set_field(a, FRAME + ("signals", 2, "factor"), 0.1))
    assert "factor: 0.1\n" in out
    # Имя устройства меняется вместе со ссылками на него
    assert E.set_field(a, DEV + ("name",), "pump") == []
    assert [e.text for e in E.set_field(a, DEV + ("name",), "pump2")] == ["pump2"]
    # Текст на нескольких языках меняется только на языке документа
    text = MINIMAL.replace("    title: Demo bus", "    title: {ru: Шина, en: Demo bus}")
    b = A.analyze(text, "m.yaml")
    assert "    title: {ru: Шина, en: CAN 1}\n" in apply(text, E.set_field(b, ("buses", 0, "title"), "CAN 1"))
    # Получатели: блочный список заменяется записью «[…]»
    text = MINIMAL.replace("            cycle_ms: 100\n",
                           "            cycle_ms: 100\n            receivers:\n              - a\n")
    c = A.analyze(text, "m.yaml")
    out = apply(text, E.set_field(c, FRAME + ("receivers",), ["a", "b"]))
    assert "            receivers: [a, b]\n            signals:" in out


def test_add_signal_to_flow_list_and_empty_frame():
    text = MINIMAL.replace("          - name: pump_state", (
        "          - name: f2\n            id: 0x300\n            signals: [{name: a, encoding: raw, byte: 0, byte_length: 1}]\n"
        "          - name: f3\n            id: 0x301\n            signals: []\n"
        "          - name: pump_state"))
    a = A.analyze(text, "m.yaml")
    out = _change(text, E.add_node(a, DEV + ("frames", 0), "signal"))
    assert ("signals: [{name: a, encoding: raw, byte: 0, byte_length: 1}, "
            "{name: signal, encoding: raw, byte: 1, byte_length: 1}]") in out
    out = _change(text, E.add_node(a, DEV + ("frames", 1), "signal"))
    assert ("            signals:\n              - name: signal\n                encoding: raw\n"
            "                byte: 0\n                byte_length: 1\n") in out
    assert "empty-frame" not in [d.code for d in A.analyze(out, "m.yaml").diagnostics]


def test_duplicate_and_delete():
    a = A.analyze(MINIMAL, "m.yaml")
    out = _change(MINIMAL, E.duplicate_node(a, DEV))
    assert "- name: pump_copy" in out and "node_id: 0x01" in out
    assert "duplicate-node-id" not in errors(out) and "duplicate-can-id" not in errors(out)
    out = _change(MINIMAL, E.duplicate_node(a, FRAME + ("signals", 1, "flags", 0)))
    assert "{bit: 0, name: overheat_copy" in out
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
    # Без истории: список создаётся в document, версия и дата документа — из записи
    a = A.analyze(MINIMAL, "m.yaml")
    change = E.add_history(a, entry, changes)
    out = _change(MINIMAL, change)
    b = A.analyze(out, "r.yaml")
    assert b.map.document.version == "0.2.0" and str(b.map.document.date) == "2026-10-07"
    first = b.map.document.history[0]
    assert (first.version, first.author, first.github) == ("0.2.0", "Jane Smith", None)
    assert first.changes == changes
    assert b.lines[change.cursor[0]].strip() == "- version: 0.2.0"
    # Новая запись — первой, перед прежними
    entry2 = {**entry, "version": "0.3.0"}
    c = A.analyze(out, "r.yaml")
    out2 = _change(out, E.add_history(c, entry2, ["x"]))
    assert [h.version for h in A.analyze(out2, "r.yaml").map.document.history] == ["0.3.0", "0.2.0"]
    assert errors(out2) == errors(MINIMAL)
    # Запись «[…]» в одну строку не дополняется
    flow = MINIMAL.replace("  version: 0.1.0\n", "  version: 0.1.0\n  history: [{version: 0.1.0}]\n")
    assert E.add_history(A.analyze(flow, "m.yaml"), entry, changes) is None


def test_new_frame_like_web_editor():
    # Кадр устройства CANopen — первый свободный тип PDO (pdo_tx1 уже занят), ID вычисляется
    a = A.analyze(MINIMAL, "m.yaml")
    out = _change(MINIMAL, E.add_node(a, DEV, "frame"))
    frame = A.analyze(out, "r.yaml").result.raw["buses"][0]["devices"][0]["frames"][-1]
    assert frame == {"name": "pump_frame", "type": "pdo_tx2", "dlc": 8, "cycle_ms": 100, "signals": []}
    # Кадр шины — с явным ID
    bus_frame = _change(MINIMAL, E.add_node(a, ("buses", 0), "frame"))
    raw = A.analyze(bus_frame, "r.yaml").result.raw["buses"][0]["frames"][-1]
    assert raw["name"] == "frame" and isinstance(raw["id"], int) and "type" not in raw
    # J1939 — свободный PGN и приоритет
    j1939 = (ROOT / "examples" / "j1939.yaml").read_text(encoding="utf-8")
    b = A.analyze(j1939, "j.yaml")
    dev = next(p for p in b.nodes if len(p) == 4 and p[2] == "devices")
    out = _change(j1939, E.add_node(b, dev, "frame"))
    raw = A.analyze(out, "r.yaml").result.raw
    frame = raw["buses"][dev[1]]["devices"][dev[3]]["frames"][-1]
    assert frame["pgn"] >= 0xFF00 and frame["priority"] == 6 and "id" not in frame


def test_frame_type_change_drops_invalid_dlc():
    text = MINIMAL.replace("            dlc: 8\n", "            dlc: 7\n", 1)
    a = A.analyze(text, "m.yaml")
    out = apply(text, E.set_field(a, FRAME + ("type",), "sdo_tx"))
    assert "type: sdo_tx\n" in out and "dlc: 7" not in out
    # Допустимый DLC остаётся
    out = apply(text, E.set_field(a, FRAME + ("type",), "pdo_tx2"))
    assert "type: pdo_tx2\n" in out and "dlc: 7\n" in out


def test_frame_types_mark_taken_ids():
    a = A.analyze(MINIMAL, "m.yaml")
    types = {t["type"]: t["taken"] for t in E.frame_types(a, FRAME)}
    assert types["pdo_tx1"] is None             # тип самого кадра не занят им же
    second = MINIMAL.replace("          - name: pump_state", (
        "          - name: other\n            type: pdo_tx2\n            signals: []\n          - name: pump_state"))
    b = A.analyze(second, "m.yaml")
    types = {t["type"]: t["taken"] for t in E.frame_types(b, DEV + ("frames", 1))}
    assert types["pdo_tx2"] == "other" and types["pdo_rx1"] is None
    # У кадра шины нет node_id: только типы, ID которых не зависит от узла
    bus_frame = E.frame_types(a, ("buses", 0, "frames", 0))
    assert [t["type"] for t in bus_frame] == ["raw", "nmt", "sync", "time"]


def test_duplicate_pdo_type_quick_fix():
    text = MINIMAL + ("          - name: pump_frame\n            type: pdo_tx1\n            dlc: 8\n"
                      "            signals: []\n")
    # Первое (предпочтительное) — свободный PDO того же направления; PDO RX не предлагается
    assert "            type: pdo_tx2\n            dlc: 8\n" in fixed(text, "duplicate-can-id")
    titles = [t for c, t, _ in fixes(text) if c == "duplicate-can-id"]
    assert titles and all("pdo_tx" in t for t in titles)
