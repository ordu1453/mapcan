"""A new device in a file of its own (#136): the included file with the device and the line of ``include`` of the
map, made by the web editor and the VS Code extension in one edit."""

from __future__ import annotations

import json
import keyword
import os
import re
from pathlib import Path
from typing import Any

from ..i18n import _
from ..lsp.edits import yaml_text
from ..schema import schema_line
from ..validate import IDENT_RE

#: Where a new device's file goes by default, relative to the map.
DEFAULT_TEMPLATE = "devices/{device}.yaml"

#: Keys of a device written as hexadecimal numbers.
_HEX = ("node_id", "address")


def default_device_file(device: str) -> str:
    return DEFAULT_TEMPLATE.format(device=device)


def device_file_target(map_path: Path, file: str) -> tuple[Path, str]:
    """The new file and its line in ``include`` (relative to the map, with "/"). ValueError if the name does not
    fit or the file exists."""
    file = file.strip()
    if not file:
        raise ValueError(_("Enter the name of the file"))
    if not re.search(r"\.ya?ml$", file, re.IGNORECASE):
        raise ValueError(_("the name of an included file must end with .yaml or .yml"))
    if Path(file).is_absolute():
        raise ValueError(_("the path of an included file is relative to the map"))
    target = (map_path.parent / file).resolve()
    if target == map_path.resolve() or target.exists():
        raise ValueError(_("file already exists: {path}", path=target))
    return target, Path(os.path.relpath(target, map_path.parent.resolve())).as_posix()


def named_after_file(device: dict[str, Any], target: Path, taken) -> dict[str, Any]:
    """The device named after its file (devices/node_c.yaml: node_c) when that name is an identifier not taken on
    the bus; otherwise as it is."""
    name = target.stem
    if IDENT_RE.match(name) and not keyword.iskeyword(name) and name not in set(taken):
        return {**device, "name": name}
    return device


def _scalar(key: str, value: Any) -> str:
    if key in _HEX and isinstance(value, int) and not isinstance(value, bool):
        return f"0x{value:02X}"
    if isinstance(value, str):
        return yaml_text(value)
    return json.dumps(value, ensure_ascii=False)


def device_file_text(map_path: Path, target: Path, bus: str, device: dict[str, Any]) -> str:
    """Text of an included file with one device on the bus ``bus`` (described by the map)."""
    part_of = Path(os.path.relpath(map_path.resolve(), target.parent)).as_posix()
    lines = [schema_line(part=True), "", "mapcan: 1", f"part_of: {part_of}", "", "buses:",
             f"  - name: {_scalar('name', bus)}", "    devices:"]
    for i, (key, value) in enumerate(device.items()):
        lines.append(("      - " if i == 0 else "        ") + f"{key}: {_scalar(key, value)}")
    return "\n".join(lines) + "\n"


def include_ops(include: Any, line: str) -> list[dict]:
    """Operations that add ``line`` to the map's ``include`` (the key is created in its place if missing)."""
    if include is None:
        return [{"op": "set", "path": ["include"], "value": [line]}]
    if not isinstance(include, list):
        raise ValueError(_("include of the map is not a list"))
    return [{"op": "insert", "path": ["include"], "value": line}]


# --------------------------------------------------------------------------- an included file left empty

_PART_KEYS = {"mapcan", "part_of", "buses", "value_tables"}


def part_is_empty(text: str) -> bool:
    """The included file adds nothing to the map: no value tables, and its buses are only named, without devices or
    frames (what is left of a device's own file after the device is deleted)."""
    import yaml

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    if not isinstance(data, dict) or set(data) - _PART_KEYS or data.get("value_tables"):
        return False
    buses = data.get("buses") or []
    return isinstance(buses, list) and all(
        isinstance(b, dict) and not set(b) - {"name", "devices", "frames"} and not b.get("devices")
        and not b.get("frames") for b in buses)


def exclude_ops(include: Any, map_path: Path, part: Path) -> list[dict]:
    """Operations that remove the included file from ``include`` of the map (the key too if it was the only one)."""
    if not isinstance(include, list):
        return []
    base = map_path.resolve().parent
    found = [i for i, f in enumerate(include) if isinstance(f, str) and (base / f).resolve() == part.resolve()]
    if not found:
        return []
    if len(found) == len(include):
        return [{"op": "remove", "path": ["include"]}]
    return [{"op": "remove", "path": ["include", i]} for i in reversed(found)]
