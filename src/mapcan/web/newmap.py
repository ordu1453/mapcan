"""Templates of new maps for "File → New map"."""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Callable

from ..i18n import N_, _, normalize_language

TEMPLATES = {
    "canopen": N_("CANopen: a bus and one device"),
    "j1939": N_("SAE J1939: an ECU with one PGN"),
    "can": N_("CAN with explicit IDs: a bus and one device"),
    "empty": N_("Empty: just a bus"),
}


def template_labels() -> dict[str, str]:
    return {k: _(v) for k, v in TEMPLATES.items()}


def _q(s: str) -> str:
    """A YAML string in double quotes (a JSON string is a valid YAML scalar)."""
    return json.dumps(s, ensure_ascii=False)


def new_map_text(template: str, title: str, author: str = "", github: str | None = None,
                 today: _dt.date | None = None, lang: str = "en") -> str:
    if template not in TEMPLATES:
        raise ValueError(_("unknown template: {template}", template=template))
    doc_lang = normalize_language(lang)
    if doc_lang is None:
        raise ValueError(_("unknown language: {language}", language=lang))
    # The new map is written in the document language: Russian from the translations, otherwise English
    return _map_text(_russian if doc_lang == "ru" else _, doc_lang, template, title, author, github,
                     today or _dt.date.today())


def _russian(msg: str, /, **kw) -> str:
    from ..locale.ru import RU

    return _(RU.get(msg, msg), **kw)


def _map_text(_: Callable[..., str], doc_lang: str, template: str, title: str, author: str,
              github: str | None, today: _dt.date) -> str:
    lines = [
        "# " + _("mapcan signal map (format v1)."),
        "# " + _("Bytes and bits are numbered from 0; start_bit is the position of the least significant bit; physical "
                 "= raw * factor + offset."),
        "",
        "mapcan: 1",
        "",
        "document:",
        f"  title: {_q(title or _('New map'))}",
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
    lines += ["      changes:", "        - " + _("Map created."), "", "buses:"]
    bus1 = "    title: " + _q(_("Bus 1"))
    device = "        title: " + _q(_("Device"))
    device_state = "            description: " + _q(_("Device state"))
    status = "                description: " + _q(_("Status"))

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
            "            length: 1",
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
            "    title: " + _q(_("J1939 bus")),
            "    bitrate: 250000",
            "    protocol: j1939",
            "    devices:",
            "      - name: ecu",
            "        title: " + _q(_("Control unit")),
            "        address: 0x00",
            "        frames:",
            "          - name: status",
            "            description: " + _q(_("Unit state")),
            "            pgn: 0xFF00",
            "            priority: 6",
            "            length: 8",
            "            cycle_ms: 100",
            "            signals:",
            "              - name: state",
            "                encoding: enum",
            "                description: " + _q(_("Operating mode")),
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
            "            length: 1",
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
