"""Общие вспомогательные функции генераторов кода."""

from __future__ import annotations

from ..model import Bus, Frame, Signal


def is_byte_array(s: Signal) -> bool:
    """Сигнал kind=bytes, выровненный по байтам, представляется массивом."""
    return s.kind == "bytes" and s.start_bit % 8 == 0 and s.bit_length % 8 == 0 \
        and s.byte_order == "little_endian"


def storage_bits(s: Signal) -> int:
    for n in (8, 16, 32, 64):
        if s.bit_length <= n:
            return n
    return 64


def frames_with_layout(bus: Bus) -> list[Frame]:
    return [f for f in bus.all_frames() if f.can_id is not None]


def selector_of(frame: Frame) -> Signal | None:
    return next((s for s in frame.layout if s.multiplexer), None)


def physical(s: Signal) -> bool:
    return s.factor != 1 or s.offset != 0 or s.kind == "metric"


def num(x: float) -> str:
    """Литерал float для C/Python без потери точности."""
    r = repr(float(x))
    return r
