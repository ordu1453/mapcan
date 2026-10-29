"""Fingerprint of the map's frame layouts (signal source ``layout_crc32``).

A device that sends the fingerprint lets a receiver check that both were built from the same layouts, even
when the map version was not raised. The fingerprint covers what goes on the wire and how it is read: for
every frame its ID (and whether it is 29-bit), length and CAN FD flag; for every signal its position, byte
order, representation, encoding, factor, offset and multiplexing. Names, texts, units, value tables, ranges,
the order of buses, devices, frames and signals, and the values of ``source`` signals do not change it.

The text it is computed from is fixed by this format (see docs/format.md): changing it changes the
fingerprint of every map, so it is versioned by the line it starts with (``v2``: the encodings number, enum,
bitfield and bytes).
"""

from __future__ import annotations

import zlib

from .model import Frame, MapCan, Signal


def _num(x: float) -> str:
    return repr(float(x))


def _signal_line(s: Signal) -> str:
    mux = ",".join(str(v) for v in sorted(s.mux_values or []))
    # A field of a bit field that is the selector (#149) adds its place; other lines stay as they were
    sel = [f"m{fl.bit}:{fl.bit_length}" for fl in s.flags or [] if fl.multiplexer]
    return " ".join([
        "s", str(s.start_bit), str(s.bit_length), s.byte_order, s.representation, s.encoding,
        _num(s.factor), _num(s.offset), "m" if s.multiplexer else "-", mux or "-", *sel,
    ])


def _frame_lines(f: Frame) -> list[str]:
    head = f"f {'x' if f.extended else 's'} {f.can_id:X} {f.length} {'fd' if f._bus.fd else 'cc'}"
    return [head] + sorted(_signal_line(s) for s in f.layout)


def layout_text(cmap: MapCan) -> str:
    """The canonical text of the layouts: one block per frame, in the order of the IDs."""
    frames = [f for bus in cmap.buses for f in bus.all_frames() if f.can_id is not None]
    blocks = sorted("\n".join(_frame_lines(f)) for f in frames)
    return "v2\n" + "\n".join(blocks) + "\n"


def layout_crc32(cmap: MapCan) -> int:
    """CRC-32 (IEEE 802.3, as zlib) of :func:`layout_text`."""
    return zlib.crc32(layout_text(cmap).encode("ascii")) & 0xFFFFFFFF
