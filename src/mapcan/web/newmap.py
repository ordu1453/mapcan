"""Шаблоны новых карт для «Файл → Новая карта»."""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Callable

from ..i18n import N_, _, normalize_language

TEMPLATES = {
    "canopen": N_("CANopen: шина и одно устройство"),
    "j1939": N_("SAE J1939: ECU с одним PGN"),
    "can": N_("CAN с явными ID: шина и одно устройство"),
    "empty": N_("Пустая: только шина"),
}


def template_labels() -> dict[str, str]:
    return {k: _(v) for k, v in TEMPLATES.items()}


def _q(s: str) -> str:
    """Строка YAML в двойных кавычках (JSON-строка — валидный YAML-скаляр)."""
    return json.dumps(s, ensure_ascii=False)


def new_map_text(template: str, title: str, author: str = "", github: str | None = None,
                 today: _dt.date | None = None, lang: str = "en") -> str:
    if template not in TEMPLATES:
        raise ValueError(_("неизвестный шаблон: {template}", template=template))
    doc_lang = normalize_language(lang)
    if doc_lang is None:
        raise ValueError(_("неизвестный язык: {language}", language=lang))
    # Содержимое новой карты — на выбранном языке документов; ключи сообщений уже русские.
    return _map_text(_ if doc_lang == "en" else _same, doc_lang, template, title, author, github,
                     today or _dt.date.today())


def _same(msg: str, /, **kw) -> str:
    return msg.format(**kw) if kw else msg


def _map_text(_: Callable[..., str], doc_lang: str, template: str, title: str, author: str,
              github: str | None, today: _dt.date) -> str:
    lines = [
        "# " + _("Карта сигналов mapcan (формат v1)."),
        "# " + _("Байты и биты нумеруются с 0; start_bit — позиция младшего бита; physical = raw * factor + offset."),
        "",
        "mapcan: 1",
        "",
        "document:",
        f"  title: {_q(title or _('Новая карта'))}",
        "  version: 0.1.0",
        f"  date: {today.isoformat()}",
    ]
    if author:
        lines.append(f"  author: {_q(author)}")
    lines += [f"  language: {doc_lang}", "  history:", "    - version: 0.1.0", f"      date: {today.isoformat()}"]
    if author:
        lines.append(f"      author: {_q(author)}")
    if github:
        lines.append(f"      github: {github}")
    lines += ["      changes:", "        - " + _("Создана карта."), "", "buses:"]
    bus1 = "    title: " + _q(_("Шина 1"))
    device = "        title: " + _q(_("Устройство"))
    device_state = "            description: " + _q(_("Состояние устройства"))
    status = "                description: " + _q(_("Статус"))

    if template == "empty":
        lines += ["  - name: bus1", bus1, "    bitrate: 500000", "    protocol: canopen",
                  "    devices: []", ""]
    elif template == "canopen":
        lines += [
            "  - name: bus1",
            bus1,
            "    bitrate: 500000",
            "    protocol: canopen",
            "    devices:",
            "      - name: device",
            device,
            "        node_id: 0x10",
            "        frames:",
            "          - name: device_state",
            "            type: pdo_tx1",
            device_state,
            "            dlc: 1",
            "            cycle_ms: 100",
            "            signals:",
            "              - name: status",
            "                encoding: enum",
            status,
            "                byte: 0",
            "                byte_length: 1",
            "                values:",
            "                  0: NO_DATA",
            "                  1: OK",
            "                  2: WARNING",
            "                  3: ALARM",
            "",
        ]
    elif template == "j1939":
        lines += [
            "  - name: j1939",
            "    title: " + _q(_("Шина J1939")),
            "    bitrate: 250000",
            "    protocol: j1939",
            "    devices:",
            "      - name: ecu",
            "        title: " + _q(_("Блок управления")),
            "        address: 0x00",
            "        frames:",
            "          - name: status",
            "            description: " + _q(_("Состояние блока")),
            "            pgn: 0xFF00",
            "            priority: 6",
            "            dlc: 8",
            "            cycle_ms: 100",
            "            signals:",
            "              - name: state",
            "                encoding: enum",
            "                description: " + _q(_("Режим работы")),
            "                byte: 0",
            "                byte_length: 1",
            "                values:",
            "                  0: OFF",
            "                  1: ON",
            "                  0xFF: NOT_AVAILABLE",
            "",
        ]
    else:
        lines += [
            "  - name: bus1",
            bus1,
            "    bitrate: 250000",
            "    protocol: can",
            "    devices:",
            "      - name: device",
            device,
            "        frames:",
            "          - name: device_state",
            "            id: 0x100",
            device_state,
            "            dlc: 1",
            "            cycle_ms: 100",
            "            signals:",
            "              - name: status",
            "                encoding: enum",
            status,
            "                byte: 0",
            "                byte_length: 1",
            "                values:",
            "                  0: NO_DATA",
            "                  1: OK",
            "",
        ]
    return "\n".join(lines)
