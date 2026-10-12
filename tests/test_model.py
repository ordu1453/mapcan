import pytest

from mapcan import bits as B
from mapcan.canopen import compute_id
from mapcan.model import Signal

from .conftest import one_bus, run


def sig(**kw) -> Signal:
    return Signal(name="s", **{"encoding": "raw", **kw})


@pytest.mark.parametrize(
    "kw, start, length",
    [
        ({"byte": 0, "byte_length": 1}, 0, 8),
        ({"byte": 1, "byte_length": 2}, 8, 16),
        ({"byte": 1, "bit": 3, "bit_length": 1}, 11, 1),
        ({"byte": 2, "bit": 4, "bit_length": 4}, 20, 4),
        ({"start_bit": 5, "bit_length": 7}, 5, 7),
        # big-endian: byte is the byte of the high part, the LSB is in the last byte of the field
        ({"byte": 1, "byte_length": 2, "byte_order": "big_endian"}, 16, 16),
    ],
)
def test_layout_sugar(kw, start, length):
    s = sig(**kw)
    assert (s.start_bit, s.bit_length) == (start, length)


def test_big_endian_bytes():
    s = sig(byte=1, byte_length=2, byte_order="big_endian")
    assert B.byte_span(s.start_bit, s.bit_length, True) == (1, 2)
    buf = bytearray(4)
    B.insert(buf, 0x1234, s.start_bit, s.bit_length, True)
    assert buf == bytearray([0, 0x12, 0x34, 0])
    assert B.extract(buf, s.start_bit, s.bit_length, True) == 0x1234


def test_little_endian_bytes():
    buf = bytearray(4)
    B.insert(buf, 0x1234, 8, 16, False)
    assert buf == bytearray([0, 0x34, 0x12, 0])


@pytest.mark.parametrize(
    "start, length, be",
    [(0, 1, False), (3, 7, False), (12, 13, False), (7, 9, False), (0, 64, False),
     (16, 16, True), (59, 10, True), (56, 64, True), (20, 1, True), (13, 11, True)],
)
def test_roundtrip_bits(start, length, be):
    bits = B.occupied_bits(start, length, be)
    assert len(set(bits)) == length and min(bits) >= 0 and max(bits) <= 63
    for value in (0, 1, (1 << length) - 1, 0x5A5A5A5A5A5A5A5A & ((1 << length) - 1)):
        buf = bytearray(8)
        B.insert(buf, value, start, length, be)
        assert B.extract(buf, start, length, be) == value
        assert sum(bin(b).count("1") for b in buf) == bin(value).count("1")


def test_signed_extract():
    buf = bytearray([0xFE, 0xFF])
    assert B.extract(buf, 0, 16, False, signed=True) == -2


def test_length_required():
    with pytest.raises(ValueError):
        sig(byte=0)
    with pytest.raises(ValueError):
        sig(byte=1, bit=3)
    assert sig(byte=1, bit=3, encoding="flag").bit_length == 1
    assert sig(byte=0, encoding="float").bit_length == 32


def test_encoding_required():
    with pytest.raises(ValueError):
        Signal(name="s", byte=0, values={0: "A"})


def test_both_position_forms_rejected():
    with pytest.raises(ValueError):
        sig(byte=0, start_bit=0)


def test_compute_id():
    assert compute_id("pdo_tx1", 0x21) == 0x1A1
    assert compute_id("emcy", 0x22) == 0x0A2
    assert compute_id("sdo_rx", 0x21) == 0x621
    assert compute_id("sync", None) == 0x080
    assert compute_id("pdo_tx1", None) is None
    assert compute_id("raw", 1) is None


def test_id_override_and_direction():
    res, _ = run(one_bus("""
        - name: a
          canopen: pdo_tx1
          length: 8
        - name: b
          canopen: pdo_tx2
          id: 0x123
          length: 8
          direction: rx
        - name: c
          canopen: sdo_rx
    """))
    frames = res.map.buses[0].devices[0].frames
    assert [f.can_id for f in frames] == [0x190, 0x123, 0x610]
    assert [f.direction for f in frames] == ["tx", "rx", "rx"]


def test_cycle_ms_means_cyclic():
    res, _ = run(one_bus("""
        - name: a
          canopen: pdo_tx1
          length: 8
          cycle_ms: 20
    """))
    f = res.map.buses[0].devices[0].frames[0]
    assert (f.mode, f.cycle_ms) == ("cyclic", 20)


def test_sdo_layout(ref_map):
    f = next(f for f in ref_map.buses[0].all_frames() if f.name == "imd_sdo_request")
    names = [s.name for s in f.layout]
    assert names[:3] == ["sdo_command", "sdo_index", "sdo_subindex"]
    assert f.layout[2].multiplexer
    alarm = next(s for s in f.layout if s.name == "alarm_resistance")
    assert (alarm.start_bit, alarm.bit_length, alarm.mux) == (32, 16, 1)


def test_reference_ids(ref_map):
    ids = {f.name: f.can_id for b in ref_map.buses for f in b.all_frames()}
    assert ids["imd_state"] == 0x1A1
    assert ids["imd_data"] == 0x2A1
    assert ids["imd_command"] == 0x221
    assert ids["imd_sdo_request"] == 0x621
    assert ids["imd_sdo_response"] == 0x5A1
    assert ids["cmu_event"] == 0x0A2
    assert ids["cmu_parse_data"] == 0x2A2
    assert ids["cmu_request"] == 0x222
    assert ids["pcu_command"] == 0x223
    assert ids["host_data"] == 0x001
