"""Вычисление CAN ID по протоколу шины: CANopen, J1939, CAN с явными ID."""

from __future__ import annotations

from .canopen import compute_id as canopen_id

J1939_DEFAULT_PRIORITY = 6
J1939_GLOBAL = 0xFF


def j1939_is_pdu1(pgn: int) -> bool:
    """PDU1 (адресный): PF < 240 — младший байт PGN (PS) задаёт адрес получателя."""
    return ((pgn >> 8) & 0xFF) < 240


def j1939_id(pgn: int, source: int, priority: int = J1939_DEFAULT_PRIORITY,
             destination: int | None = None) -> int:
    """29-битный ID J1939: priority(3) | EDP(1) DP(1) PF(8) PS(8) | SA(8)."""
    if j1939_is_pdu1(pgn):
        field = (pgn & 0x3FF00) | (J1939_GLOBAL if destination is None else destination)
    else:
        field = pgn & 0x3FFFF
    return ((priority & 0x7) << 26) | (field << 8) | (source & 0xFF)


def j1939_decode(can_id: int) -> tuple[int, int, int, int | None]:
    """(priority, pgn, source, destination|None) из 29-битного ID."""
    priority = (can_id >> 26) & 0x7
    field = (can_id >> 8) & 0x3FFFF
    source = can_id & 0xFF
    if j1939_is_pdu1(field):
        return priority, field & 0x3FF00, source, field & 0xFF
    return priority, field, source, None


def frame_id(bus, device, frame) -> tuple[int | None, bool]:
    """(CAN ID, extended) для кадра; ID None — вычислить нельзя."""
    if frame.id is not None:
        return frame.id, frame.extended
    if bus.protocol == "canopen":
        return canopen_id(frame.type, device.node_id if device else None), frame.extended
    if bus.protocol == "j1939" and frame.pgn is not None:
        if device is None or device.address is None:
            return None, True
        prio = J1939_DEFAULT_PRIORITY if frame.priority is None else frame.priority
        return j1939_id(frame.pgn, device.address, prio, frame.destination), True
    return None, frame.extended
