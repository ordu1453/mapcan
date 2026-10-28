import pytest

from mapcan.web.yamlops import OpError, apply_ops, dump, layout_keys, make_yaml, merge_text

from .conftest import DATA, REFERENCE, ROOT

FILES = [REFERENCE, ROOT / "examples" / "minimal.yaml", DATA / "invalid_map.yaml"]


def _edit(text: str, ops: list[dict]) -> str:
    y = make_yaml(text)
    doc = y.load(text)
    before = dump(y, doc)
    apply_ops(doc, ops)
    return merge_text(text, before, dump(y, doc))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_noop_roundtrip_is_identical(path):
    text = path.read_text(encoding="utf-8")
    assert _edit(text, []) == text


@pytest.mark.parametrize("document", ["document:\n  title: T\n", "document: {title: T}\n"])
def test_new_top_level_key_is_separated_as_the_others(document):
    """#136: include added to a map whose keys are separated by empty lines, after a block or a "{…}" mapping."""
    text = f"mapcan: 2\n\n{document}\nbuses: []\n"
    out = _edit(text, [{"op": "set", "path": ["include"], "value": ["devices/a.yaml"]}])
    assert out == f"mapcan: 2\n\n{document}\ninclude: [devices/a.yaml]\n\nbuses: []\n"
    # Keys not separated stay so
    text = f"mapcan: 2\n{document}buses: []\n"
    assert _edit(text, [{"op": "set", "path": ["include"], "value": ["a.yaml"]}]) == (
        f"mapcan: 2\n{document}include: [a.yaml]\nbuses: []\n")


def test_multiline_flow_map_survives_unrelated_edit():
    text = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8")
    out = _edit(text, [{"op": "set", "path": ["document", "version"], "value": "0.2.0"}])
    assert "                  - {name: sensor_state, bit: 4, bit_length: 2,\n" in out
    assert out.replace("version: 0.2.0", "version: 0.1.0") == text


def test_hex_for_new_ids():
    out = _edit("a:\n  id: 0x10\n", [{"op": "set", "path": ["a", "node_id"], "value": 26}])
    assert "node_id: 0x1A" in out or "node_id: 0x1a" in out


def test_hex_for_invalid_raw():
    # Raw codes without a value are written in hex, a negative value of a signed signal as it is (#148)
    out = _edit("s:\n  name: x\n", [{"op": "set", "path": ["s", "invalid_raw"], "value": [255, "0xFF00..0xFFFF", -1]}])
    assert out.endswith("  invalid_raw:\n    - 0xFF\n    - 0xFF00..0xFFFF\n    - -1\n")
    assert _edit("s:\n  name: x\n", [{"op": "set", "path": ["s", "invalid_raw"], "value": 255}]).endswith(
        "  invalid_raw: 0xFF\n")


def test_values_keys_become_ints():
    out = _edit("s:\n  name: x\n", [{"op": "set", "path": ["s", "values"], "value": {"0": "OFF", "0x1": "ON"}}])
    assert "values:\n    0: OFF\n    1: ON\n" in out
    # A new row of a table is a numeric key too, not the string "'2'"
    out = _edit(out, [{"op": "set", "path": ["s", "values", "2"], "value": "ERR"}])
    assert "    1: ON\n    2: ERR\n" in out


@pytest.mark.parametrize("start, length, be, expected", [
    (8, 8, False, {"byte": 1, "byte_length": 1}),
    (8, 16, False, {"byte": 1, "byte_length": 2}),
    (11, 1, False, {"byte": 1, "bit": 3, "bit_length": 1}),
    (20, 4, False, {"byte": 2, "bit": 4, "bit_length": 4}),
    (12, 12, False, {"start_bit": 12, "bit_length": 12}),
    (16, 16, True, {"byte": 1, "byte_length": 2}),
    (19, 9, True, {"start_bit": 19, "bit_length": 9}),
    (19, 4, True, {"byte": 2, "bit": 3, "bit_length": 4}),
])
def test_layout_keys(start, length, be, expected):
    assert layout_keys(start, length, be) == expected


SIGNAL_DOC = "signals:\n  - name: s\n    encoding: number\n{layout}    unit: V\n"
SIGNAL = ["signals", 0]


def _layout(layout: str, ops: list[dict]) -> str:
    out = _edit(SIGNAL_DOC.format(layout=layout), ops)
    return out.split("encoding: number\n", 1)[1].split("    unit: V\n", 1)[0]


@pytest.mark.parametrize("layout, ops, expected", [
    # a length across bytes written next to `byte` turns into start_bit, and back
    ("    byte: 1\n    byte_length: 1\n",
     [{"op": "remove", "path": [*SIGNAL, "byte_length"]}, {"op": "set", "path": [*SIGNAL, "bit_length"], "value": 12}],
     "    start_bit: 8\n    bit_length: 12\n"),
    ("    start_bit: 8\n    bit_length: 12\n", [{"op": "set", "path": [*SIGNAL, "bit_length"], "value": 16}],
     "    byte: 1\n    byte_length: 2\n"),
    # dragged to a byte boundary: the notation follows (#117)
    ("    start_bit: 3\n    bit_length: 8\n",
     [{"op": "set_layout", "path": SIGNAL, "start_bit": 16, "bit_length": 8}], "    byte: 2\n    byte_length: 1\n"),
    # a value in one byte: byte, bit and bit_length
    ("    start_bit: 8\n    bit_length: 16\n", [{"op": "set", "path": [*SIGNAL, "bit_length"], "value": 4}],
     "    byte: 1\n    bit: 0\n    bit_length: 4\n"),
    # big-endian: byte is the byte with the high part
    ("    start_bit: 8\n    bit_length: 16\n", [{"op": "set", "path": [*SIGNAL, "byte_order"], "value": "big_endian"}],
     "    byte: 0\n    byte_length: 2\n"),
])
def test_position_is_written_canonical(layout, ops, expected):
    """#117: the editors write a position in one notation, whichever field or drag changed it."""
    assert _layout(layout, ops) == expected


def test_position_that_does_not_parse_is_left_as_typed():
    out = _edit(SIGNAL_DOC.format(layout="    byte: 1\n    byte_length: 1\n"),
                [{"op": "set", "path": [*SIGNAL, "bit_length"], "value": 12}])
    assert "    byte: 1\n    byte_length: 1\n" in out and "    bit_length: 12\n" in out


def test_position_keeps_the_length_the_encoding_implies():
    text = "signals:\n  - name: s\n    encoding: number\n    representation: float\n    byte: 0\n"
    assert _edit(text, [{"op": "set", "path": [*SIGNAL, "byte"], "value": 4}]).endswith("    byte: 4\n")
    out = _edit(text, [{"op": "set_layout", "path": SIGNAL, "start_bit": 3, "bit_length": 32}])
    assert out.endswith("    start_bit: 3\n    bit_length: 32\n")


def test_errors():
    with pytest.raises(OpError):
        _edit("a: 1\n", [{"op": "remove", "path": ["b"]}])
    with pytest.raises(OpError):
        _edit("a: [1]\n", [{"op": "move", "path": ["a", 0], "to": 5}])
    with pytest.raises(OpError):
        _edit("a: 1\n", [{"op": "frobnicate", "path": ["a"]}])
    with pytest.raises(OpError):
        _edit("v:\n  values: {0: A, 1: B}\n", [{"op": "rename_key", "path": ["v", "values", "0"], "new_key": "1"}])


MINI = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8")
SIG = ["buses", 0, "devices", 0, "frames", 0, "signals"]


@pytest.mark.parametrize(("op", "message"), [
    ({"op": "copy", "path": []}, "unknown operation"),
    ({"op": "set", "path": "buses", "value": 1}, "path must be a list"),
    ({"op": "set", "path": [], "value": 1}, "empty path"),
    ({"op": "set", "path": ["buses", 5], "value": 1}, "index out of range"),
    ({"op": "set", "path": ["mapcan", "x"], "value": 1}, "parent is not a mapping"),
    ({"op": "set", "path": ["buses", "first", "x"], "value": 1}, "path not found"),
    ({"op": "set", "path": ["document", "title", "x"], "value": None}, "parent is not a mapping"),
    ({"op": "remove", "path": ["buses", 5]}, "index out of range"),
    ({"op": "remove", "path": ["document", "nope"]}, "key not found"),
    ({"op": "remove", "path": ["document", "title", "x"]}, "cannot remove"),
    ({"op": "insert", "path": ["document", "title"], "value": 1}, "not a list"),
    ({"op": "insert", "path": ["mapcan", "x", "y"], "value": 1}, "path not found"),
    ({"op": "move", "path": ["document", "title"], "to": 0}, "only list items"),
    ({"op": "move", "path": [*SIG, 0], "to": 9}, "index out of range"),
    ({"op": "rename_key", "path": ["buses", 0], "new_key": "x"}, "not a mapping"),
    ({"op": "rename_key", "path": ["document", "title"], "new_key": "version"}, "already exists"),
    ({"op": "move", "path": [*SIG, 0]}, "move: "),
])
def test_operation_errors(op, message):
    with pytest.raises(OpError, match=message):
        _edit(MINI, [op])


def test_operations_on_lists_and_keys():
    # Insert at a position, move, rename a value key given as a string
    out = _edit(MINI, [
        {"op": "insert", "path": [*SIG, 1, "flags"], "index": 0, "value": {"name": "first", "bit": 7}},
        {"op": "rename_key", "path": [*SIG, 0, "values", "2"], "new_key": "0x3"},
        {"op": "rename_key", "path": ["document", "title"], "new_key": "title"},
        {"op": "move", "path": [*SIG, 5], "to": 0},
    ])
    lines = out.splitlines()
    assert lines.index("              - name: counter         # arbitrary position: bits 56..59") < \
        lines.index("              - name: mode            # enum, byte 0")
    assert "                  3: {name: FAULT, description: fault}" in lines
    assert out.index("name: first") < out.index("name: overheat")
    # A list that is not there yet is created; an item past the end is appended
    out = _edit(MINI, [{"op": "insert", "path": ["buses", 0, "devices", 0, "frames", 0, "receivers"],
                        "value": "x"},
                       {"op": "insert", "path": [*SIG, 1, "flags"], "index": 99, "value": {"name": "z", "bit": 7}}])
    # The new list goes to its place in the canonical order, as a key set with "set" does
    assert "            cycle_ms: 100\n            receivers:\n              - x\n            signals:\n" in out
    assert out.index("name: sensor_state") < out.index("name: z")
    # Removing a key that is not there, with a value of None
    assert _edit(MINI, [{"op": "set", "path": ["document", "nope"], "value": None}]) == MINI


def test_values_keep_their_notation():
    from mapcan.web.yamlops import _key, plain, to_node

    out = _edit(MINI, [{"op": "set", "path": ["buses", 0, "devices", 0, "node_id"], "value": 0x22},
                       {"op": "set", "path": [*SIG, 0, "byte"], "value": 0.0}])
    assert "        node_id: 0x22\n" in out and "                byte: 0\n" in out
    assert _key("0x10") == 16 and _key("-0x1") == -1 and _key(" 7 ") == 7 and _key("OFF") == "OFF"
    assert to_node("2026-13-40", "date") == "2026-13-40"
    assert str(to_node("2026-10-26", "date")) == "2026-10-26"
    assert plain({"a": [True, 1, 1.5, "x"]}) == {"a": [True, 1, 1.5, "x"]}
