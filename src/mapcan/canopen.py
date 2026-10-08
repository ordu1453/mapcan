"""CANopen function codes (CiA 301, predefined connection set)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionCode:
    type: str
    base: int
    per_node: bool          # ID = base + node_id
    direction: str | None   # default direction relative to the device
    label_ru: str
    label_en: str
    purpose_ru: str
    purpose_en: str


FUNCTION_CODES: dict[str, FunctionCode] = {
    fc.type: fc
    for fc in [
        FunctionCode("nmt", 0x000, False, "rx", "NMT", "NMT", "управление сетью", "network management"),
        FunctionCode("sync", 0x080, False, None, "SYNC", "SYNC", "синхронизация", "synchronization"),
        FunctionCode("emcy", 0x080, True, "tx", "EMCY", "EMCY", "события", "emergency"),
        FunctionCode("time", 0x100, False, None, "TIME", "TIME", "дата и время", "time stamp"),
        FunctionCode("pdo_tx1", 0x180, True, "tx", "PDO TX 1", "TPDO1", "состояния", "states"),
        FunctionCode("pdo_rx1", 0x200, True, "rx", "PDO RX 1", "RPDO1", "установки", "settings"),
        FunctionCode("pdo_tx2", 0x280, True, "tx", "PDO TX 2", "TPDO2", "данные", "data"),
        FunctionCode("pdo_rx2", 0x300, True, "rx", "PDO RX 2", "RPDO2", "", ""),
        FunctionCode("pdo_tx3", 0x380, True, "tx", "PDO TX 3", "TPDO3", "", ""),
        FunctionCode("pdo_rx3", 0x400, True, "rx", "PDO RX 3", "RPDO3", "", ""),
        FunctionCode("pdo_tx4", 0x480, True, "tx", "PDO TX 4", "TPDO4", "", ""),
        FunctionCode("pdo_rx4", 0x500, True, "rx", "PDO RX 4", "RPDO4", "", ""),
        FunctionCode("sdo_tx", 0x580, True, "tx", "SDO TX", "SDO TX", "настройка (ответ)", "SDO response"),
        FunctionCode("sdo_rx", 0x600, True, "rx", "SDO RX", "SDO RX", "настройка (приказ)", "SDO request"),
        FunctionCode("heartbeat", 0x700, True, "tx", "Heartbeat", "Heartbeat", "контроль связи", "node guarding"),
    ]
}

# Allowed DLC of service frames by CiA 301; a frame without an explicit dlc gets the smallest of them.
CANOPEN_DLC: dict[str, set[int]] = {
    "nmt": {2}, "sync": {0, 1}, "time": {6}, "heartbeat": {1}, "sdo_tx": {8}, "sdo_rx": {8},
}

# Order of the rows in the addressing table.
ADDRESSING_ORDER = list(FUNCTION_CODES)


def compute_id(frame_type: str, node_id: int | None) -> int | None:
    """CAN ID from the function code and node_id; None if it cannot be computed."""
    fc = FUNCTION_CODES.get(frame_type)
    if fc is None:
        return None
    if not fc.per_node:
        return fc.base
    if node_id is None:
        return None
    return fc.base + node_id


def default_direction(frame_type: str) -> str | None:
    fc = FUNCTION_CODES.get(frame_type)
    return fc.direction if fc else None
