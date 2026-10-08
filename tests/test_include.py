"""Подключаемые файлы (include) и именованные таблицы значений (value_tables)."""

from __future__ import annotations

import textwrap

import pytest

from mapcan.loader import load
from mapcan.validate import check

MAIN = """\
mapcan: 1
include: [common.yaml]
document: {title: Test, language: en}
value_tables:
  states: {0: OFF, 1: ON}
buses:
  - name: can1
    protocol: can
    devices:
      - name: vcu
        frames:
          - name: vcu_state
            id: 0x100
            dlc: 1
            signals:
              - {name: mode, encoding: enum, description: x, byte: 0, byte_length: 1, values: states}
"""

COMMON = """\
value_tables:
  faults: {0: OK, 1: FAULT}
buses:
  - name: can1
    devices:
      - name: bms
        frames:
          - name: bms_state
            id: 0x200
            dlc: 1
            signals:
              - {name: fault, encoding: enum, description: x, byte: 0, byte_length: 1, values: faults}
  - name: can2
    protocol: can
    devices:
      - name: charger
        frames:
          - name: charger_state
            id: 0x300
            dlc: 1
            signals:
              - {name: on, encoding: enum, description: x, byte: 0, byte_length: 1, values: states}
"""


def write(tmp_path, main=MAIN, common=COMMON):
    (tmp_path / "common.yaml").write_text(textwrap.dedent(common), encoding="utf-8")
    p = tmp_path / "main.yaml"
    p.write_text(main, encoding="utf-8")
    return p


def run(path):
    res = load(path)
    return res, check(res)


def test_include_merges_buses_devices_and_tables(tmp_path):
    res, rep = run(write(tmp_path))
    assert res.map is not None and not rep.errors, [d.format() for d in rep.diagnostics]
    can1, can2 = res.map.buses
    assert [d.name for d in can1.devices] == ["vcu", "bms"]            # дополнена существующая шина
    assert can2.name == "can2" and can2.devices[0].name == "charger"   # и добавлена новая
    # Таблицы — и свои, и подключённые; ссылка подставляется таблицей
    sig = {s.name: s for b in res.map.buses for f in b.all_frames() for s in f.signals}
    assert sig["mode"].values == {0: "OFF", 1: "ON"} and sig["fault"].values == {0: "OK", 1: "FAULT"}
    assert sig["on"].values == {0: "OFF", 1: "ON"}


def test_diagnostics_point_into_included_file(tmp_path):
    res, rep = run(write(tmp_path, common=COMMON.replace("id: 0x200", "id: 0x100")))
    dup = next(d for d in rep.diagnostics if d.code == "duplicate-can-id")
    assert dup.file.endswith("common.yaml") and dup.line == 9
    # Для редактора основного файла — на строке include, с местом в тексте сообщения
    moved = res.source.in_main_file(dup)
    assert moved.file == str(tmp_path / "main.yaml") and moved.line == 2
    assert moved.message.startswith("common.yaml:9: ")


def test_unknown_value_table(tmp_path):
    res, rep = run(write(tmp_path, main=MAIN.replace("values: states}", "values: nope}")))
    d = next(d for d in rep.diagnostics if d.code == "value-table")
    assert "'nope'" in d.message and d.line == 16


def test_include_errors(tmp_path):
    # Нет файла
    _, rep = run(write(tmp_path, main=MAIN.replace("[common.yaml]", "[missing.yaml]")))
    assert "include" in rep.codes()
    # Недопустимый ключ и попытка переопределить уже описанную шину
    bad = "document: {title: X}\n" + COMMON.replace("  - name: can1\n", "  - name: can1\n    protocol: j1939\n", 1)
    _, rep = run(write(tmp_path, common=bad))
    msgs = [d.message for d in rep.diagnostics if d.code == "include"]
    assert any("'document'" in m for m in msgs) and any("'protocol'" in m for m in msgs)
    # Повтор имени таблицы
    _, rep = run(write(tmp_path, common=COMMON.replace("faults:", "states:")))
    assert any(d.code == "include" and "'states'" in d.message for d in rep.diagnostics)


def test_lsp_shows_included_problems_on_include_line(tmp_path):
    from mapcan.lsp import analysis as A

    p = write(tmp_path, common=COMMON.replace("id: 0x200", "id: 0x100"))
    a = A.analyze(p.read_text(encoding="utf-8"), str(p))
    d = next(d for d in a.diagnostics if d.code == "duplicate-can-id" and d.message.startswith("common.yaml"))
    assert d.line == 2


def _tree(tmp_path):
    from mapcan.lsp.analysis import analyze, map_tree

    p = write(tmp_path)
    a = analyze(p.read_text(encoding="utf-8"), str(p))
    return a, {n["ident"]: n for n in _walk(map_tree(a))}


def _walk(nodes):
    for n in nodes:
        yield n
        yield from _walk(n["children"])


def test_tree_shows_included_nodes(tmp_path):
    a, nodes = _tree(tmp_path)
    common = str(tmp_path / "common.yaml")
    # Свой узел — без файла, подключённые — с файлом и областью в нём
    assert "file" not in nodes["vcu"] and "file" not in nodes["mode"]
    assert nodes["bms"]["file"] == common and nodes["bms"]["path"] == ["buses", 0, "devices", 1]
    assert nodes["bms"]["selection"][0] == 5                    # «- name: bms» в common.yaml
    assert nodes["fault"]["file"] == common and nodes["can2"]["file"] == common
    assert nodes["charger_state"]["path"] == ["buses", 1, "devices", 0, "frames", 0]
    # Области основного файла не сбиты позициями подключённого
    assert a.path_at((13, 16))[:6] == ("buses", 0, "devices", 0, "frames", 0)


def test_included_node_fields_are_read_only(tmp_path):
    from mapcan.lsp.edits import add_node, apply_ops, node_fields, set_field
    from mapcan.web.yamlops import OpError

    a, nodes = _tree(tmp_path)
    path = tuple(nodes["fault"]["path"])
    f = node_fields(a, path)
    assert f["file"] == str(tmp_path / "common.yaml") and f["values"]["name"] == "fault"
    # Устройства шины основного файла — вместе с подключёнными (получатели, отправитель)
    assert [d["name"] for d in node_fields(a, ("buses", 0, "devices", 0, "frames", 0))["devices"]] == ["vcu", "bms"]
    assert set_field(a, path + ("name",), "x") == []
    assert add_node(a, tuple(nodes["bms"]["path"]), "frame") is None
    with pytest.raises(OpError):
        apply_ops(a, [{"op": "remove", "path": list(path)}])


def test_web_state_has_included_nodes(tmp_path):
    from mapcan.web.session import EditorSession
    from mapcan.web.yamlops import OpError

    s = EditorSession(write(tmp_path))
    st = s.state()
    assert st["included"] == [{"path": ["buses", 0, "devices", 1], "file": "common.yaml"},
                              {"path": ["buses", 1], "file": "common.yaml"}]
    assert [b["name"] for b in st["included_buses"]] == ["can1", "can2"]
    assert len(st["data"]["buses"]) == 1                         # данные основного файла — без подключённых
    with pytest.raises(OpError):
        s.apply([{"op": "set", "path": ["buses", 1, "name"], "value": "x"}])
