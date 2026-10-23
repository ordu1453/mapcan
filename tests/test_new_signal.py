"""Where the tree's "+ Signal" puts a new signal: never over another one."""

from __future__ import annotations

import pytest

from mapcan.lsp import analysis as A
from mapcan.lsp import edits as E

FRAME = ("buses", 0, "devices", 0, "frames", 0)


def frame_map(signals: str, length: str = "length: 8", fd: bool = False) -> str:
    return f"""mapcan: 2
document: {{title: T, language: en}}
buses:
  - name: b
    protocol: can{"\n    fd: true" if fd else ""}
    devices:
      - name: ecu
        frames:
          - name: f
            id: 0x100
            {length}
            cycle_ms: 100
            signals:
{signals}
"""


def sig(name: str, place: str) -> str:
    return f"              - {{name: {name}, description: {name}, encoding: number, {place}}}"


def bits(text: str) -> dict[str, set[int]]:
    """Bits of each signal of the frame, as the map says."""
    a = A.analyze(text, "m.yaml")
    assert a.map is not None
    return {s.name: set(E.occupied_bits(s.start_bit, s.bit_length, s.byte_order == "big_endian"))
            for s in E._find(a.map, FRAME).signals}


def add(text: str) -> str:
    change = E.add_node(A.analyze(text, "m.yaml"), FRAME, "signal")
    assert change is not None
    return change.text


def no_overlap(text: str) -> None:
    seen: set[int] = set()
    for b in bits(text).values():
        assert not seen & b
        seen |= b


def test_a_free_byte():
    text = add(frame_map(sig("a", "start_bit: 0, bit_length: 4")))
    assert bits(text)["signal"] == set(range(8, 16))


def test_a_full_frame_grows_by_a_byte():
    text = add(frame_map(sig("a", "byte: 0, byte_length: 2"), "length: 2"))
    assert "length: 3" in text and bits(text)["signal"] == set(range(16, 24))
    no_overlap(text)


def test_a_full_fd_frame_grows_to_the_next_length():
    text = add(frame_map(sig("a", "byte: 0, byte_length: 8"), fd=True))
    assert "length: 12" in text and bits(text)["signal"] == set(range(64, 72))


def test_a_full_frame_of_8_bytes_takes_free_bits():
    text = add(frame_map("\n".join([sig("a", "byte: 0, byte_length: 7"), sig("b", "start_bit: 56, bit_length: 3")])))
    assert bits(text)["signal"] == set(range(59, 64))
    no_overlap(text)


def test_a_frame_without_free_bits_is_refused():
    with pytest.raises(E.EditRefused, match="No free bits"):
        add(frame_map(sig("a", "byte: 0, byte_length: 8")))


def test_signals_added_one_after_another_do_not_overlap():
    text = frame_map(sig("a", "byte: 0, byte_length: 6"))
    for _ in range(2):
        text = add(text)
    no_overlap(text)
    assert len(bits(text)) == 3
    with pytest.raises(E.EditRefused):
        add(text)


def test_a_map_that_does_not_load():
    # cycle_ms is wrong: there is no model, the signals are read from the frame's YAML
    text = frame_map(sig("a", "byte: 0, byte_length: 2")).replace("cycle_ms: 100", "cycle_ms: fast")
    assert A.analyze(text, "m.yaml").map is None
    out = add(text)
    assert bits(out.replace("cycle_ms: fast", "cycle_ms: 100"))["signal"] == set(range(16, 24))
    # A signal whose position cannot be read: the new one goes after the last known bit
    text = frame_map("\n".join([sig("a", "byte: 2, byte_length: 1"), sig("b", "byte: x")]))
    out = add(text)
    assert "byte: 3, byte_length: 1" in out or "byte: 3\n" in out


def test_the_cursor_is_on_the_new_name_when_the_frame_grows():
    text = frame_map(sig("a", "byte: 0, byte_length: 1"), "length: 1").replace("            length: 1\n", "")
    text = text.replace("            id: 0x100\n", "            id: 0x100\n            length: 1\n")
    change = E.add_node(A.analyze(text, "m.yaml"), FRAME, "signal")
    line = change.text.splitlines()[change.cursor[0]]
    assert line[change.cursor[1]:].startswith("signal")
