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
])
def test_layout_keys(start, length, be, expected):
    assert layout_keys(start, length, be, None) == expected


def test_layout_keys_flag_encoding_needs_explicit_length():
    # for encoding: flag, `byte: 1` would mean 1 bit: an explicit length is needed
    assert layout_keys(8, 8, False, "flag") != {"byte": 1}
    assert layout_keys(11, 1, False, "flag") == {"byte": 1, "bit": 3}


def test_errors():
    with pytest.raises(OpError):
        _edit("a: 1\n", [{"op": "remove", "path": ["b"]}])
    with pytest.raises(OpError):
        _edit("a: [1]\n", [{"op": "move", "path": ["a", 0], "to": 5}])
    with pytest.raises(OpError):
        _edit("a: 1\n", [{"op": "frobnicate", "path": ["a"]}])
    with pytest.raises(OpError):
        _edit("v:\n  values: {0: A, 1: B}\n", [{"op": "rename_key", "path": ["v", "values", "0"], "new_key": "1"}])
