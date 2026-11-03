"""CANopen object dictionary (CiA 301): data types, index areas, standard objects, the dictionary of a device.

The dictionary is written in the map (``objects`` of a bus and of a device) and read and written by SDO. Objects of
the bus are in the dictionary of each of its devices; a device's own objects are in the manufacturer area, and one with
an index of the bus's takes its place. PDO signals carry objects by their ``index``/``subindex`` but do not make them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .i18n import N_
from .model import Bus, Device, OdObject

# Basic data types: code (an index of the data type area 0x0001..0x001F) and length in bits (0: of any length)
DATA_TYPES: dict[str, tuple[int, int]] = {
    "boolean": (0x0001, 1), "integer8": (0x0002, 8), "integer16": (0x0003, 16), "integer32": (0x0004, 32),
    "unsigned8": (0x0005, 8), "unsigned16": (0x0006, 16), "unsigned32": (0x0007, 32), "real32": (0x0008, 32),
    "visible_string": (0x0009, 0), "octet_string": (0x000A, 0), "unicode_string": (0x000B, 0),
    "time_of_day": (0x000C, 48), "time_difference": (0x000D, 48), "domain": (0x000F, 0),
    "integer24": (0x0010, 24), "real64": (0x0011, 64), "integer40": (0x0012, 40), "integer48": (0x0013, 48),
    "integer56": (0x0014, 56), "integer64": (0x0015, 64), "unsigned24": (0x0016, 24), "unsigned40": (0x0018, 40),
    "unsigned48": (0x0019, 48), "unsigned56": (0x001A, 56), "unsigned64": (0x001B, 64),
}

STRING_TYPES = {"visible_string", "octet_string", "unicode_string", "domain"}


@dataclass(frozen=True)
class Area:
    first: int
    last: int
    title: str


# Index areas of the dictionary (CiA 301, 7.4.1)
AREAS = (
    Area(0x0000, 0x0FFF, N_("Data types")),
    Area(0x1000, 0x1FFF, N_("Communication profile")),
    Area(0x2000, 0x5FFF, N_("Manufacturer area")),
    Area(0x6000, 0x9FFF, N_("Standardized device profiles")),
    Area(0xA000, 0xBFFF, N_("Standardized interface profiles")),
    Area(0xC000, 0xFFFF, N_("Reserved")),
)


def area_of(index: int) -> Area:
    return next(a for a in AREAS if a.first <= index <= a.last)


def integer_range(data_type: str) -> tuple[int, int] | None:
    """Range of an integer type (boolean: 0..1); None for other types."""
    if data_type == "boolean":
        return 0, 1
    bits = DATA_TYPES[data_type][1]
    if data_type.startswith("unsigned"):
        return 0, (1 << bits) - 1
    if data_type.startswith("integer"):
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return None


def dictionary(bus: Bus, dev: Device | None) -> list[OdObject]:
    """Objects of the dictionary of a device by index (of the bus, if ``dev`` is None): the bus's, with the device's
    own in place of those with the same index."""
    objects = {o.index: o for o in bus.objects}
    if dev is not None:
        objects.update({o.index: o for o in dev.objects})
    return [objects[i] for i in sorted(objects)]


def subindices(obj: OdObject) -> set[int]:
    """Subindices an SDO exchange or a PDO signal may address: 0 of a variable; 0 (the number of entries) and the
    entries of an array or a record."""
    return {0} | {e.subindex for e in obj.entries or []}
