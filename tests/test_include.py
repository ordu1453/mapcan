"""Included files (include) and named value tables (value_tables)."""

from __future__ import annotations

import textwrap

import pytest

from mapcan.loader import load
from mapcan.validate import check

MAIN = """\
mapcan: 2
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
    open_files = {str((tmp_path / "common.yaml").resolve()): edited}
    res = loads(p.read_text(encoding="utf-8"), str(p), read=open_files.get)
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


def test_lsp_form_edits_go_to_the_included_file(tmp_path):
    from mapcan.lsp.analysis import analyze
    from mapcan.lsp.edits import field_ops, in_other_file, routed_ops

    main = write(tmp_path)
    common = str((tmp_path / "common.yaml").resolve())
    a = analyze(main.read_text(encoding="utf-8"), str(main))
    bms = ("buses", 0, "devices", 1, "name")
    assert in_other_file(a, bms) and not in_other_file(a, ("buses", 0, "devices", 0, "name"))
    # Renaming bms renames it in common.yaml; a receiver in the main file follows
    text = main.read_text(encoding="utf-8").replace("length: 1\n", "length: 1\n            receivers: [bms]\n", 1)
    main.write_text(text, encoding="utf-8")
    a = analyze(text, str(main))
    own, others = routed_ops(a, field_ops(a, bms, "battery"), lambda p: open(p, encoding="utf-8").read())
    assert "receivers: [battery]" in own
    assert list(others) == [common] and "- name: battery" in others[common]


def test_rename_and_references_span_the_files_of_the_map(tmp_path):
    from mapcan.lsp.analysis import analyze, analyze_part
    from mapcan.lsp.edits import reference_locations, rename_edits, rename_files

    main = write(tmp_path)
    common = str((tmp_path / "common.yaml").resolve())
    text = main.read_text(encoding="utf-8").replace("length: 1\n", "length: 1\n            receivers: [bms]\n", 1)
    main.write_text(text, encoding="utf-8")
    read = lambda p: open(p, encoding="utf-8").read()   # noqa: E731
    a = analyze(text, str(main), read)
    line = next(i for i, ln in enumerate(a.lines) if "receivers: [bms]" in ln)
    pos = (line, a.lines[line].index("bms") + 1)
    # From the main file: the receiver here, the device in common.yaml
    files = rename_files(a, ("buses", 0, "devices", 0, "frames", 0, "receivers", 0), "battery")
    assert set(files) == {None, common}
    assert [e.text for e in files[None]] == ["battery"] and files[common][0].start == (5, 14)
    assert rename_edits(a, ("buses", 0, "devices", 0, "frames", 0, "receivers", 0), "x")[0].start[0] == line
    assert [f for f, _r in reference_locations(a, pos)] == [common, None]
    # From common.yaml opened on its own: the device here, the receiver in the main file
    part_text = f"mapcan: 2\npart_of: {main.name}\n" + read(common)
    (tmp_path / "common.yaml").write_text(part_text, encoding="utf-8")
    b = analyze_part(part_text, common, read)
    files = rename_files(b, ("buses", 0, "devices", 1, "name"), "battery")
    assert files[None][0].start == (7, 14)
    assert [(k, e.start) for k, v in files.items() if k for e in v] == [(str(main), (line, pos[1] - 1))]


def test_tree_edits_of_included_nodes_go_to_their_file(tmp_path):
    from mapcan.lsp.analysis import analyze, analyze_part
    from mapcan.lsp.edits import add_node, delete_node, duplicate_node

    main = write(tmp_path)
    common = str((tmp_path / "common.yaml").resolve())
    a = analyze(main.read_text(encoding="utf-8"), str(main))
    bms = ("buses", 0, "devices", 1)
    # The tree's edits of a node are made in the text of its file (the server sends them there)
    v = a.view_of(bms)
    assert v is not a and v.text == (tmp_path / "common.yaml").read_text(encoding="utf-8")
    added = add_node(v, bms, "frame")
    assert "          - name: bms_frame\n            id: 0x" in added.text
    assert added.text.count("- name:") == v.text.count("- name:") + 1
    assert "- name: bms_copy" in duplicate_node(v, bms).text
    # bms is the only device of can1 in common.yaml: the list stays a list there
    gone = delete_node(v, bms).text
    assert "bms" not in gone and "    devices: []\n  - name: can2" in gone
    # A device added to a bus of the main file goes to the main file, one added to can2 to common.yaml
    assert a.view_of(("buses", 0)) is a
    assert a.view_of(("buses", 1)).own_file == common
    assert "- name: device" in add_node(a.view_of(("buses", 1)), ("buses", 1), "device").text
    # In the included file opened on its own, the main file's nodes and new buses go to the main file
    part = analyze_part(f"part_of: {main.name}\n" + v.text, common, lambda p: open(p, encoding="utf-8").read())
    assert part.view_of(()).own_file is None and part.view_of(("buses", 0, "devices", 0)) is part.view_of(())
    assert part.view_of(bms) is part
    assert add_node(part.view_of(()), (), "bus").text.startswith("mapcan: 2\ninclude: [common.yaml]\n")


def test_web_editor_opens_the_map_of_an_included_file(tmp_path):
    from mapcan.loader import map_of
    from mapcan.web.session import EditorSession

    main = write(tmp_path)
    common = tmp_path / "common.yaml"
    common.write_text(f"mapcan: 2\npart_of: {main.name}\n" + common.read_text(encoding="utf-8"), encoding="utf-8")
    assert map_of(common) == main.resolve() and map_of(main) == main.resolve()
    s = EditorSession(common)
    st = s.state()
    assert st["file"] == main.name and st["opened_part"] == "common.yaml"
    assert EditorSession(main).state()["opened_part"] is None
    # A file that names a map which does not include it opens on its own
    stray = tmp_path / "stray.yaml"
    stray.write_text(f"mapcan: 2\npart_of: {main.name}\nbuses: []\n", encoding="utf-8")
    assert map_of(stray) == stray.resolve()


def test_web_state_has_included_nodes(tmp_path):
    from mapcan.web.session import EditorSession

    s = EditorSession(write(tmp_path))
    st = s.state()
    assert st["included"] == [{"path": ["buses", 0, "devices", 1], "file": "common.yaml",
                               "local": ["buses", 0, "devices", 0]},
                              {"path": ["buses", 1], "file": "common.yaml", "local": ["buses", 1]}]
    assert st["parts"] == {"common.yaml": (tmp_path / "common.yaml").read_text(encoding="utf-8")}
    assert [b["name"] for b in st["included_buses"]] == ["can1", "can2"]
    assert len(st["data"]["buses"]) == 1                         # data of the main file, without the included ones


def test_web_edits_included_nodes_in_their_file(tmp_path):
    from mapcan.web.session import EditorSession

    main = write(tmp_path)
    common = tmp_path / "common.yaml"
    main_text, common_text = main.read_text(encoding="utf-8"), common.read_text(encoding="utf-8")
    s = EditorSession(main)
    # Rename bms (the second device of can1 in the map, the first in common.yaml) and a reference to it in the
    # main file: one edit, one undo step, in two files
    assert s.apply([{"op": "set", "path": ["buses", 0, "devices", 1, "name"], "value": "battery"},
                    {"op": "set", "path": ["buses", 0, "devices", 0, "frames", 0, "receivers"], "value": ["battery"]}])
    st = s.state()
    assert st["dirty"] and st["dirty_files"] == ["common.yaml"]
    assert [d["name"] for d in st["included_buses"][0]["devices"]] == ["vcu", "battery"]
    assert s.state()["data"]["buses"][0]["devices"][0]["frames"][0]["receivers"] == ["battery"]
    assert "- name: battery" in s.parts[str(common.resolve())].text
    assert common.read_text(encoding="utf-8") == common_text          # nothing written before Save
    # A field of a node of the included file's own bus
    assert s.apply([{"op": "set", "path": ["buses", 1, "devices", 0, "title"], "value": "Charger"}])
    s.undo()
    s.undo()
    assert s.text == main_text and s.parts[str(common.resolve())].text == common_text and not s.dirty
    s.redo()
    s.save()
    assert "- name: battery" in common.read_text(encoding="utf-8") and "battery" in main.read_text(encoding="utf-8")
    assert not s.state()["dirty"] and not s.disk_changed()


def test_web_yaml_tab_edits_an_included_file(tmp_path):
    from mapcan.web.session import EditorSession

    main = write(tmp_path)
    common = tmp_path / "common.yaml"
    main_text, common_text = main.read_text(encoding="utf-8"), common.read_text(encoding="utf-8")
    s = EditorSession(main)
    # Typing in the YAML tab of common.yaml: the steps of a series are one undo step, the map is not touched
    assert s.set_text(common_text.replace("id: 0x300", "id: 0x30"), live=True, file="common.yaml")
    assert s.set_text(common_text.replace("id: 0x300", "id: 0x301"), live=True, file="common.yaml")
    st = s.state()
    assert st["text"] == main_text and st["dirty_files"] == ["common.yaml"]
    assert "id: 0x301" in st["parts"]["common.yaml"]
    assert s.undo() and s.parts[str(common.resolve())].text == common_text and not s.dirty
    # A message about the included file has its place in that file
    bad = common_text.replace("id: 0x200", "id: 0x100")
    dup = next(d for d in s.check_text(bad, file="common.yaml") if d["code"] == "duplicate-can-id")
    assert dup["line"] == 2 and dup["part"] == {"file": "common.yaml", "line": 9, "column": dup["part"]["column"]}
    assert s.set_text(bad, file="common.yaml")
    assert any(d.get("part", {}).get("line") == 9 for d in s.state()["diagnostics"])
    with pytest.raises(Exception, match="cannot be read"):
        s.set_text("x: 1", file="other.yaml")


def test_web_save_checks_included_files_on_disk(tmp_path):
    from mapcan.web.session import ConflictError, EditorSession

    main = write(tmp_path)
    s = EditorSession(main)
    s.apply([{"op": "set", "path": ["buses", 1, "devices", 0, "title"], "value": "Charger"}])
    (tmp_path / "common.yaml").write_text(COMMON + "\n# changed outside\n", encoding="utf-8")
    assert s.disk_changed()
    with pytest.raises(ConflictError):
        s.save()


HEADER = "mapcan: 2\npart_of: main.yaml\n"


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
    _, rep = run(write(tmp_path, common=HEADER.replace("mapcan: 2", "mapcan: 1") + COMMON))
    assert any(d.code == "include" and "version" in d.message for d in rep.diagnostics)


def test_included_file_alone_points_to_its_map(tmp_path):
    write(tmp_path, common=HEADER + COMMON)
    res, rep = run(tmp_path / "common.yaml")
    assert res.map is None and [d.code for d in rep.diagnostics] == ["include"]
    assert "'main.yaml'" in rep.diagnostics[0].message


def test_included_file_is_not_a_map_for_the_editors():
    from mapcan.lsp.analysis import is_mapcan

    assert is_mapcan(MAIN) and not is_mapcan(HEADER + COMMON)


def _include_messages(tmp_path, common: str, main: str = MAIN) -> list[str]:
    _, rep = run(write(tmp_path, main=main, common=common))
    return [d.message for d in rep.diagnostics if d.code in ("include", "yaml")]


def test_included_files_that_cannot_be_read(tmp_path):
    # Broken YAML is shown in the included file, and a list instead of a mapping is refused
    _, rep = run(write(tmp_path, common="buses: [\n"))
    assert any(d.code == "yaml" and d.file.endswith("common.yaml") for d in rep.diagnostics)
    assert "an included file must be a YAML mapping" in _include_messages(tmp_path, "- a\n- b\n")
    # An empty included file adds nothing
    assert _include_messages(tmp_path, "") == []
    # part_of that is not a path
    assert "part_of is the path of the map file" in _include_messages(tmp_path, "part_of: 5\n" + COMMON)


def test_include_field_of_another_type(tmp_path):
    # Not a list: the schema reports it; an item that is not a file name is skipped
    _, rep = run(write(tmp_path, main=MAIN.replace("include: [common.yaml]", "include: common.yaml")))
    assert "include" not in rep.codes() and "schema" in rep.codes()
    _, rep = run(write(tmp_path, main=MAIN.replace("[common.yaml]", "[5, common.yaml]")))
    assert [d.code for d in rep.diagnostics if d.level == "error"] == ["schema"]
    # common.yaml is still read
    assert "include-part-of" in rep.codes()


def test_include_without_a_folder_to_resolve_it():
    from mapcan.loader import loads

    res = loads(MAIN)
    assert "include: the map has no path to resolve included files from" in [d.message for d in res.report.diagnostics]


def test_included_parts_of_another_shape(tmp_path):
    # Tables and buses that are not a mapping and a list, or a bus that is not a mapping, are not merged, and
    # the included file says why
    for common, message in (("value_tables: [a]\n", "value_tables must be a mapping of tables"),
                            ("buses: {a: 1}\n", "buses must be a list of buses"),
                            ("buses: [5]\n", "a bus must be a mapping with its name")):
        res, rep = run(write(tmp_path, common=common))
        assert [d.name for b in res.map.buses for d in b.devices] == ["vcu"], common
        [d] = [d for d in rep.diagnostics if d.code == "include"]
        assert d.message == message and d.file.endswith("common.yaml") and d.level == "error"
    # The map's own tables of another shape: the included ones are not merged into them, the schema reports it
    main = MAIN.replace("value_tables:\n  states: {0: OFF, 1: ON}\n", "value_tables: [x]\n")
    _, rep = run(write(tmp_path, main=main))
    assert "schema" in rep.codes()


def test_map_of(tmp_path):
    from mapcan.loader import map_of

    main = write(tmp_path, common=HEADER + COMMON)
    common = tmp_path / "common.yaml"
    assert map_of(common) == main.resolve()
    assert map_of(main) == main.resolve()                              # no part_of: the file itself
    assert map_of(tmp_path / "missing.yaml") == (tmp_path / "missing.yaml").resolve()
    # The map it names does not include it, or is not there
    other = tmp_path / "other.yaml"
    other.write_text(HEADER + COMMON, encoding="utf-8")
    assert map_of(other) == other.resolve()
    lost = tmp_path / "lost.yaml"
    lost.write_text(HEADER.replace("main.yaml", "nope.yaml") + COMMON, encoding="utf-8")
    assert map_of(lost) == lost.resolve()
