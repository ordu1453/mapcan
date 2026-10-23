"""The deprecated frame field direction: it follows from the CANopen function and the sender, and a frame from
outside the map is a frame of the bus. Maps with it read the same; mapcan migrate removes it."""

from __future__ import annotations

import pytest

from mapcan.loader import loads
from mapcan.validate import validate_text
from mapcan.web.yamlops import migrate_directions_text, migrate_text

from .test_lsp_edits import fixed

PROTOCOL_ID = {"can": "id: 0x7E0", "j1939": "id: 0x18FF20F9\n            extended: true"}


def device_rx(protocol: str = "can", direction: str = "rx", extra: str = "") -> str:
    """A map whose device ecu has its own frame and a frame received from outside the map, with direction."""
    return f"""mapcan: 2
document: {{title: T, language: en}}
buses:
  - name: b
    protocol: {protocol}
    devices:
      - name: ecu
        address: 0x10
        frames:
          - name: own
            {"id: 0x100" if protocol == "can" else "pgn: 0xFF10"}
            length: 8
            cycle_ms: 100
            receivers: [panel]
            signals: [{{name: a, description: a, encoding: number, byte: 0, byte_length: 1}}]
          - name: from_tester   # the diagnostic tester
            direction: {direction}
            {PROTOCOL_ID[protocol]}
            length: 8
            trigger: event{extra}
            signals: [{{name: b, description: b, encoding: number, byte: 0, byte_length: 1}}]
      - name: panel
        address: 0x11
"""


def frames(text: str) -> dict:
    """What a map says about its frames, whatever file place they are written in."""
    res = loads(text, "m.yaml")
    assert res.map is not None, [d.message for d in res.report.sorted()]
    return {f.name: (f.can_id, f.extended, f.sender_name, sorted(f.receiver_names), [s.name for s in f.signals])
            for b in res.map.buses for f in b.all_frames()}


def messages(text: str, code: str) -> list[str]:
    return [d.message for d in validate_text(text, "m.yaml")[1].sorted() if d.code == code]


@pytest.mark.parametrize("protocol", ["can", "j1939"])
def test_a_frame_from_outside_the_map_moves_to_the_bus(protocol):
    text = device_rx(protocol)
    assert messages(text, "direction-deprecated") == [
        "frame 'from_tester' comes from outside the map: describe it in the frames of bus 'b' with 'ecu' in "
        "receivers (mapcan migrate moves it)"]
    out = migrate_text(text)
    assert "direction" not in out
    # The same frames: sender (outside the map), receivers, ID; the comment goes along
    assert frames(out) == frames(text)
    moved = out[out.index("    frames:\n      - name: from_tester"):]
    assert moved.splitlines()[1].endswith("# the diagnostic tester")
    assert "receivers: [ecu]" in out
    assert not messages(out, "direction-deprecated")


def test_a_direction_that_follows_from_the_map_is_removed():
    text = device_rx(direction="tx").replace("          - name: from_tester", "          - name: from_tester2")
    assert messages(text, "direction-deprecated") == [
        "direction of frame 'from_tester2' follows from the CANopen function and the sender: remove it "
        "(mapcan migrate does)"]
    out = migrate_text(text)
    assert out == text.replace("            direction: tx\n", "")
    assert frames(out) == frames(text)


def test_a_received_frame_with_its_sender_keeps_its_place():
    text = device_rx(extra="\n            sender: panel")
    out = migrate_text(text)
    assert out == text.replace("            direction: rx\n", "")
    assert frames(out) == frames(text)


def test_a_contradiction_is_left_for_the_author():
    # The owner sends the frame (direction tx), but sender names another device: which one is meant is unknown
    text = device_rx(direction="tx", extra="\n            sender: panel")
    assert messages(text, "direction-deprecated") == [
        "direction of frame 'from_tester' contradicts its CANopen function or sender: remove it, and set sender to "
        "the device that sends the frame"]
    assert migrate_directions_text(text) == text


def test_maps_without_direction_do_not_change():
    text = device_rx().replace("            direction: rx\n", "            sender: panel\n")
    assert migrate_directions_text(text) == text
    assert not messages(text, "direction-deprecated")


def test_quick_fix_removes_direction():
    text = device_rx()
    assert fixed(text, "direction-deprecated") == migrate_directions_text(text)
