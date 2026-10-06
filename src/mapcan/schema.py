"""JSON Schema формата для подсказок в IDE (VS Code YAML extension)."""

from __future__ import annotations

from typing import Any

from .i18n import N_, _
from .model import MapCan

SCHEMA_ID = "https://mapcan.local/schema/mapcan-v1.json"


def json_schema() -> dict[str, Any]:
    schema = MapCan.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = SCHEMA_ID
    schema["title"] = _(N_("mapcan — карта сигналов CAN (формат v1)"))
    _allow_int_keys(schema)
    _translate(schema)
    return schema


# Докстроки моделей pydantic тоже попадают в описания схемы.
_MODEL_DOCS = (
    N_("Текст с переводами. Строка вместо объекта трактуется как язык документа."),
    N_("Должностное лицо для блоков «УТВЕРЖДАЮ» / «СОГЛАСОВАНО»."),
    N_("Подписи основной надписи ЕСКД (ГОСТ 2.104) и листов утверждения."),
    N_("Настраиваемые правила стиля (проверяются как warning)."),
    N_("Флаг внутри битового поля. ``bit`` — смещение от младшего бита поля."),
    N_("Один SDO-обмен (expedited): команда, индекс, субиндекс, значение."),
)


def _translate(node: Any) -> None:
    """Описания в схеме — на английском, как и весь интерфейс."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "description" and isinstance(v, str):
                node[k] = _(v)
            else:
                _translate(v)
    elif isinstance(node, list):
        for v in node:
            _translate(v)


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
