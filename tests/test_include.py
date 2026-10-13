"""Included files (include) and named value tables (value_tables)."""

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
            length: 1
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
            length: 1
            signals:
              - {name: fault, encoding: enum, description: x, byte: 0, byte_length: 1, values: faults}
  - name: can2
    protocol: can
    devices:
      - name: charger
        frames:
          - name: charger_state
            id: 0x300
            length: 1
            signals:
              - {name: on, encoding: enum, description: x, byte: 0, byte_length: 1, values: states}
"""


def test_paths_of_included_nodes_both_ways(tmp_path):
    src = load(write(tmp_path)).source
    common = str(tmp_path / "common.yaml")
    main = src.file
    # bms extends can1 of the main file: second device of the map, first of common.yaml
    assert src.origin(("buses", 0, "devices", 1, "frames", 0, "signals", 0)) == \
        (common, ("buses", 0, "devices", 0, "frames", 0, "signals", 0))
    assert src.origin(("buses", 1, "devices", 0)) == (common, ("buses", 1, "devices", 0))     # the new bus can2
    assert src.origin(("value_tables", "faults", 1)) == (common, ("value_tables", "faults", 1))
    assert src.origin(("buses", 0, "devices", 0)) == (main, ("buses", 0, "devices", 0))      # vcu, main file
    assert src.merged_path(common, ("buses", 0, "devices", 0, "name")) == ("buses", 0, "devices", 1, "name")
    assert src.merged_path(common, ("buses", 1)) == ("buses", 1)
    assert src.merged_path(common, ("buses", 0)) is None        # only extends can1: not a node of the map
    assert src.merged_path(main, ("buses", 0)) == ("buses", 0)


def test_texts_of_open_files_replace_the_disk(tmp_path):
    p = write(tmp_path)
    from mapcan.loader import loads

    edited = COMMON.replace("name: charger", "name: charger2")
    res = loads(p.read_text(encoding="utf-8"), str(p), texts={str((tmp_path / "common.yaml").resolve()): edited})
    assert res.map.buses[1].devices[0].name == "charger2"


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
    assert [d.name for d in can1.devices] == ["vcu", "bms"]            # the existing bus is extended
    assert can2.name == "can2" and can2.devices[0].name == "charger"   # and a new one is added
    # Tables: both own and included ones; a reference is replaced with the table
    sig = {s.name: s for b in res.map.buses for f in b.all_frames() for s in f.signals}
    assert sig["mode"].values == {0: "OFF", 1: "ON"} and sig["fault"].values == {0: "OK", 1: "FAULT"}
    assert sig["on"].values == {0: "OFF", 1: "ON"}


def test_diagnostics_point_into_included_file(tmp_path):
    res, rep = run(write(tmp_path, common=COMMON.replace("id: 0x200", "id: 0x100")))
    dup = next(d for d in rep.diagnostics if d.code == "duplicate-can-id")
    assert dup.file.endswith("common.yaml") and dup.line == 9
    # For the editor of the main file: on the include line, with the place in the message text
    moved = res.source.in_main_file(dup)
    assert moved.file == str(tmp_path / "main.yaml") and moved.line == 2
    assert moved.message.startswith("common.yaml:9: ")


def test_unknown_value_table(tmp_path):
    res, rep = run(write(tmp_path, main=MAIN.replace("values: states}", "values: nope}")))
    d = next(d for d in rep.diagnostics if d.code == "value-table")
    assert "'nope'" in d.message and d.line == 16


def test_include_errors(tmp_path):
    # No file
    _, rep = run(write(tmp_path, main=MAIN.replace("[common.yaml]", "[missing.yaml]")))
    assert "include" in rep.codes()
    # A key that is not allowed, and an attempt to redefine a bus that is already described
    bad = "document: {title: X}\n" + COMMON.replace("  - name: can1\n", "  - name: can1\n    protocol: j1939\n", 1)
    _, rep = run(write(tmp_path, common=bad))
    msgs = [d.message for d in rep.diagnostics if d.code == "include"]
    assert any("'document'" in m for m in msgs) and any("'protocol'" in m for m in msgs)
    # A repeated table name
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
    # An own node has no file, included ones have the file and their range in it
    assert "file" not in nodes["vcu"] and "file" not in nodes["mode"]
    assert nodes["bms"]["file"] == common and nodes["bms"]["path"] == ["buses", 0, "devices", 1]
    assert nodes["bms"]["selection"][0] == 5                    # "- name: bms" in common.yaml
    assert nodes["fault"]["file"] == common and nodes["can2"]["file"] == common
    assert nodes["charger_state"]["path"] == ["buses", 1, "devices", 0, "frames", 0]
    # Ranges of the main file are not shifted by the positions of the included one
    assert a.path_at((13, 16))[:6] == ("buses", 0, "devices", 0, "frames", 0)


def test_included_node_fields_are_read_only(tmp_path):
    from mapcan.lsp.edits import add_node, apply_ops, node_fields, set_field
    from mapcan.web.yamlops import OpError

    a, nodes = _tree(tmp_path)
    path = tuple(nodes["fault"]["path"])
    f = node_fields(a, path)
    assert f["file"] == str(tmp_path / "common.yaml") and f["values"]["name"] == "fault"
    # Devices of a bus of the main file come with the included ones (receivers, sender)
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
    assert len(st["data"]["buses"]) == 1                         # data of the main file, without the included ones
    with pytest.raises(OpError):
        s.apply([{"op": "set", "path": ["buses", 1, "name"], "value": "x"}])


HEADER = "mapcan: 1\npart_of: main.yaml\n"


def test_included_file_names_its_map(tmp_path):
    # Without the header: a warning (files written before it keep loading)
    _, rep = run(write(tmp_path))
    d = next(d for d in rep.diagnostics if d.code == "include-part-of")
    assert d.level == "warning" and d.file.endswith("common.yaml") and "part_of: main.yaml" in d.message
    # With it: no message
    _, rep = run(write(tmp_path, common=HEADER + COMMON))
    assert not {"include", "include-part-of"} & rep.codes(), [d.format() for d in rep.diagnostics]
    # part_of of another map is an error at part_of
    _, rep = run(write(tmp_path, common=HEADER.replace("main.yaml", "other.yaml") + COMMON))
    d = next(d for d in rep.diagnostics if d.code == "include")
    assert "'other.yaml'" in d.message and d.line == 2
    # A different format version is an error
    _, rep = run(write(tmp_path, common=HEADER.replace("mapcan: 1", "mapcan: 2") + COMMON))
    assert any(d.code == "include" and "version" in d.message for d in rep.diagnostics)


def test_included_file_alone_points_to_its_map(tmp_path):
    write(tmp_path, common=HEADER + COMMON)
    res, rep = run(tmp_path / "common.yaml")
    assert res.map is None and [d.code for d in rep.diagnostics] == ["include"]
    assert "'main.yaml'" in rep.diagnostics[0].message


def test_included_file_is_not_a_map_for_the_editors():
    from mapcan.lsp.analysis import is_mapcan

    assert is_mapcan(MAIN) and not is_mapcan(HEADER + COMMON)
