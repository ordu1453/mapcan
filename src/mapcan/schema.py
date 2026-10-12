"""JSON Schema of the format for IDE hints (VS Code YAML extension)."""

from __future__ import annotations

from typing import Any

from .i18n import _
from .model import MapCan, MapPart

SCHEMA_ID = "https://mapcan.local/schema/mapcan-v1.json"
PART_SCHEMA_ID = "https://mapcan.local/schema/mapcan-part-v1.json"


def json_schema(part: bool = False) -> dict[str, Any]:
    """Schema of a map, or with ``part`` of a file it includes (``part_of``)."""
    schema = (MapPart if part else MapCan).model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = PART_SCHEMA_ID if part else SCHEMA_ID
    schema["title"] = (_("mapcan — file included by a map (format v1)") if part
                       else _("mapcan — CAN signal map (format v1)"))
    _allow_int_keys(schema)
    return schema


def _allow_int_keys(node: Any) -> None:
    """Value tables have integer keys; JSON Schema keys are strings.
    Decimal and hexadecimal keys are allowed."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "additionalProperties" in node and "propertyNames" not in node:
            ap = node["additionalProperties"]
            if isinstance(ap, dict) and ("anyOf" in ap or "$ref" in ap):
                node["propertyNames"] = {"pattern": r"^(-?\d+|0[xX][0-9a-fA-F]+)$"}
        for v in node.values():
            _allow_int_keys(v)
    elif isinstance(node, list):
        for v in node:
            _allow_int_keys(v)
