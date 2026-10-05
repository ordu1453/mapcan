"""JSON Schema формата для подсказок в IDE (VS Code YAML extension)."""

from __future__ import annotations

from typing import Any

from .model import CanMap

SCHEMA_ID = "https://canmap.local/schema/canmap-v1.json"


def json_schema() -> dict[str, Any]:
    schema = CanMap.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = SCHEMA_ID
    schema["title"] = "canmap — карта сигналов CAN (формат v1)"
    _allow_int_keys(schema)
    return schema


def _allow_int_keys(node: Any) -> None:
    """Таблицы значений имеют целочисленные ключи; в JSON Schema ключи — строки.
    Разрешаем десятичную и шестнадцатеричную запись ключей."""
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
