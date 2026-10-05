"""Шаблоны новых карт для «Файл → Новая карта»."""

from __future__ import annotations

import datetime as _dt
import json

TEMPLATES = {
    "canopen": "CANopen: шина и одно устройство",
    "j1939": "SAE J1939: ECU с одним PGN",
    "can": "CAN с явными ID: шина и одно устройство",
    "empty": "Пустая: только шина",
}


def _q(s: str) -> str:
    """Строка YAML в двойных кавычках (JSON-строка — валидный YAML-скаляр)."""
    return json.dumps(s, ensure_ascii=False)


def new_map_text(template: str, title: str, author: str = "", github: str | None = None,
                 today: _dt.date | None = None) -> str:
    if template not in TEMPLATES:
        raise ValueError(f"неизвестный шаблон: {template}")
    today = today or _dt.date.today()
    lines = [
        "# Карта сигналов canmap (формат v1).",
        "# Байты и биты нумеруются с 0; start_bit — позиция младшего бита; physical = raw * factor + offset.",
        "",
        "canmap: 1",
        "",
        "document:",
        f"  title: {_q(title or 'Новая карта')}",
        "  version: 0.1.0",
        f"  date: {today.isoformat()}",
    ]
    if author:
        lines.append(f"  author: {_q(author)}")
    lines += ["  language: ru", "  history:", "    - version: 0.1.0", f"      date: {today.isoformat()}"]
    if author:
        lines.append(f"      author: {_q(author)}")
    if github:
        lines.append(f"      github: {github}")
    lines += ["      changes:", "        - Создана карта.", "", "buses:"]

    if template == "empty":
        lines += ["  - name: bus1", "    title: Шина 1", "    bitrate: 500000", "    protocol: canopen",
                  "    devices: []", ""]
    elif template == "canopen":
        lines += [
            "  - name: bus1",
            "    title: Шина 1",
            "    bitrate: 500000",
            "    protocol: canopen",
            "    devices:",
            "      - name: device",
            "        title: Устройство",
            "        node_id: 0x10",
            "        frames:",
            "          - name: device_state",
            "            type: pdo_tx1",
            "            description: Состояние устройства",
            "            dlc: 1",
            "            cycle_ms: 100",
            "            signals:",
            "              - name: status",
            "                description: Статус",
            "                byte: 0",
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
            "    title: Шина J1939",
            "    bitrate: 250000",
            "    protocol: j1939",
            "    devices:",
            "      - name: ecu",
            "        title: Блок управления",
            "        address: 0x00",
            "        frames:",
            "          - name: status",
            "            description: Состояние блока",
            "            pgn: 0xFF00",
            "            priority: 6",
            "            dlc: 8",
            "            cycle_ms: 100",
            "            signals:",
            "              - name: state",
            "                description: Режим работы",
            "                byte: 0",
            "                values:",
            "                  0: OFF",
            "                  1: ON",
            "                  0xFF: NOT_AVAILABLE",
            "",
        ]
    else:
        lines += [
            "  - name: bus1",
            "    title: Шина 1",
            "    bitrate: 250000",
            "    protocol: can",
            "    devices:",
            "      - name: device",
            "        title: Устройство",
            "        frames:",
            "          - name: device_state",
            "            id: 0x100",
            "            description: Состояние устройства",
            "            dlc: 1",
            "            cycle_ms: 100",
            "            signals:",
            "              - name: status",
            "                description: Статус",
            "                byte: 0",
            "                values:",
            "                  0: NO_DATA",
            "                  1: OK",
            "",
        ]
    return "\n".join(lines)
