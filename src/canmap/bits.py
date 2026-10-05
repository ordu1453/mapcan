"""Раскладка бит сигналов и упаковка/распаковка полезной нагрузки.

Позиции — в нумерации lsb0: абсолютный бит ``p`` это бит ``p % 8`` байта ``p // 8``.
``start_bit`` сигнала — позиция его младшего бита (LSB).

* little-endian: значение занимает биты ``start .. start+len-1`` подряд;
* big-endian (Motorola): от LSB биты идут вверх до конца байта, затем
  переходят к биту 0 *предыдущего* байта.
"""

from __future__ import annotations


def chunks(start: int, length: int, big_endian: bool) -> list[tuple[int, int, int]]:
    """Разбить поле на куски внутри байтов: (байт, сдвиг в байте, число бит).

    Куски идут от младших бит значения к старшим. Байт может быть
    отрицательным, если big-endian поле «вылезает» за начало кадра.
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
    """Абсолютные позиции бит поля, от младшего бита значения к старшему."""
    bits = []
    for byte, shift, n in chunks(start, length, big_endian):
        base = byte * 8 + shift
        bits.extend(range(base, base + n))
    return bits


def byte_span(start: int, length: int, big_endian: bool) -> tuple[int, int]:
    """Первый и последний байт поля (по возрастанию)."""
    bs = [c[0] for c in chunks(start, length, big_endian)]
    return min(bs), max(bs)


def msb_position(start: int, length: int, big_endian: bool) -> int:
    """Позиция старшего бита значения (нужна для DBC/Motorola)."""
    return occupied_bits(start, length, big_endian)[-1]


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


def raw_range(length: int, signed: bool) -> tuple[int, int]:
    if signed:
        return -(1 << (length - 1)), (1 << (length - 1)) - 1
    return 0, (1 << length) - 1
