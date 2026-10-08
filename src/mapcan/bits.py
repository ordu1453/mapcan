"""Bit layout of signals and packing/unpacking of the payload.

Positions are in lsb0 numbering: absolute bit ``p`` is bit ``p % 8`` of byte ``p // 8``.
``start_bit`` of a signal is the position of its least significant bit (LSB).

* little-endian: the value takes bits ``start .. start+len-1`` in a row;
* big-endian (Motorola): from the LSB the bits go up to the end of the byte, then
  continue at bit 0 of the *previous* byte.
"""

from __future__ import annotations


def chunks(start: int, length: int, big_endian: bool) -> list[tuple[int, int, int]]:
    """Split a field into pieces within bytes: (byte, shift in the byte, number of bits).

    The pieces go from the low bits of the value to the high ones. A byte can be
    negative if a big-endian field sticks out before the start of the frame.
    """
    out = []
    pos, left = start, length
    while left > 0:
        byte, shift = divmod(pos, 8)
        n = min(8 - shift, left)
        out.append((byte, shift, n))
        left -= n
        pos = (byte - 1) * 8 if big_endian else (byte + 1) * 8
    return out


def occupied_bits(start: int, length: int, big_endian: bool) -> list[int]:
    """Absolute positions of the field's bits, from the value's least significant bit to the most significant."""
    bits = []
    for byte, shift, n in chunks(start, length, big_endian):
        base = byte * 8 + shift
        bits.extend(range(base, base + n))
    return bits


def byte_span(start: int, length: int, big_endian: bool) -> tuple[int, int]:
    """First and last byte of the field (ascending)."""
    bs = [c[0] for c in chunks(start, length, big_endian)]
    return min(bs), max(bs)


def msb_position(start: int, length: int, big_endian: bool) -> int:
    """Position of the value's most significant bit (needed for DBC/Motorola)."""
    return occupied_bits(start, length, big_endian)[-1]


def lsb_from_msb(msb: int, length: int) -> int:
    """start_bit (LSB position) of a big-endian field from the position of its MSB, as in DBC/Motorola.

    From the MSB the value goes down the byte, and from bit 0 on to bit 7 of the *next* byte."""
    pos = msb
    for _ in range(length - 1):
        pos = pos + 15 if pos % 8 == 0 else pos - 1
    return pos


def extract(data: bytes, start: int, length: int, big_endian: bool, signed: bool = False) -> int:
    value, i = 0, 0
    for byte, shift, n in chunks(start, length, big_endian):
        value |= ((data[byte] >> shift) & ((1 << n) - 1)) << i
        i += n
    if signed and value & (1 << (length - 1)):
        value -= 1 << length
    return value


def insert(buf: bytearray, value: int, start: int, length: int, big_endian: bool) -> None:
    value &= (1 << length) - 1
    i = 0
    for byte, shift, n in chunks(start, length, big_endian):
        mask = ((1 << n) - 1) << shift
        buf[byte] = (buf[byte] & ~mask & 0xFF) | (((value >> i) << shift) & mask)
        i += n


def raw_range(length: int, signed: bool, code: str | None = None) -> tuple[int, int]:
    """Range of the raw value; in ones' complement and sign-magnitude it is symmetric (zero has two forms)."""
    if signed:
        lo = -(1 << (length - 1)) + (code in ("ones_complement", "sign_magnitude"))
        return lo, (1 << (length - 1)) - 1
    return 0, (1 << length) - 1
