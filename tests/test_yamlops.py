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
