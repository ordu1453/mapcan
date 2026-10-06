"""Сравнение двух версий карты на уровне кадров и сигналов, генерация changelog."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .docmodel import fmt_num, hex_id
from .model import Bus, Frame, MapCan, Signal, enum_entries, text

ChangeKind = Literal["added", "removed", "changed"]
Scope = Literal["bus", "device", "frame", "signal", "flag", "value"]


@dataclass
class Change:
    kind: ChangeKind
    scope: Scope
    bus: str
    frame: str = ""
    can_id: str = ""
    device: str = ""
    signal: str = ""
    item: str = ""           # флаг или значение enum
    field: str = ""          # изменённое поле
    old: Any = None
    new: Any = None


@dataclass
class MapDiff:
    old_version: str
    new_version: str
    changes: list[Change] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.changes

    def to_dict(self) -> dict:
        return {"old_version": self.old_version, "new_version": self.new_version,
                "changes": [asdict(c) for c in self.changes]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)


DEVICE_FIELDS = ("node_id", "address", "short", "title")
FRAME_FIELDS = ("can_id", "type", "dlc", "direction", "mode", "cycle_ms", "extended", "device",
                "pgn", "priority", "sender", "receivers", "description")
SIGNAL_FIELDS = ("start_bit", "bit_length", "byte_order", "signed", "signed_code", "kind", "factor", "offset", "unit",
                 "min", "max", "initial", "invalid", "multiplexer", "mux", "description")
FLAG_FIELDS = ("bit", "bit_length", "description")


def _frame_attrs(f: Frame, lang: str) -> dict:
    tr = f.transmission
    return {
        "can_id": f.can_id, "type": f.type, "dlc": f.dlc, "direction": f.direction,
        "mode": tr.mode if tr else None, "cycle_ms": tr.cycle_ms if tr else None,
        "extended": f.extended, "device": f.device.name if f.device else None,
        "pgn": f.pgn, "priority": f.priority, "sender": f.sender_name, "receivers": list(f.receivers),
        "description": text(f.description, lang),
    }


def _signal_attrs(s: Signal, lang: str) -> dict:
    return {
        "start_bit": s.start_bit, "bit_length": s.bit_length, "byte_order": s.byte_order,
        "signed": s.signed, "signed_code": s.signed_code, "kind": s.kind,
        "factor": s.factor, "offset": s.offset, "unit": s.unit,
        "min": s.min, "max": s.max, "initial": s.initial, "invalid": s.invalid_values or None,
        "multiplexer": s.multiplexer, "mux": s.mux_values,
        "description": text(s.description, lang),
    }


def _attrs_diff(old: dict, new: dict, names) -> list[tuple[str, Any, Any]]:
    return [(n, old.get(n), new.get(n)) for n in names if old.get(n) != new.get(n)]


def diff_maps(old: MapCan, new: MapCan, lang: str | None = None) -> MapDiff:
    lang = lang or new.lang
    d = MapDiff(old.document.version, new.document.version)
    ob = {b.name: b for b in old.buses}
    nb = {b.name: b for b in new.buses}
    for name in ob.keys() - nb.keys():
        d.changes.append(Change("removed", "bus", name))
    for name in nb:
        if name not in ob:
            d.changes.append(Change("added", "bus", name))
            for f in nb[name].all_frames():
                d.changes.append(_frame_change("added", name, f))
            continue
        _diff_bus(d, ob[name], nb[name], lang)
    return d


def _frame_change(kind, bus: str, f: Frame, **kw) -> Change:
    return Change(kind, "frame", bus, frame=f.name, can_id=hex_id(f.can_id, f.extended),
                  device=f.device.name if f.device else "", **kw)


def _diff_bus(d: MapDiff, old: Bus, new: Bus, lang: str) -> None:
    od = {x.name: x for x in old.devices}
    nd = {x.name: x for x in new.devices}
    for name in nd.keys() - od.keys():
        d.changes.append(Change("added", "device", new.name, device=name))
    for name in od.keys() - nd.keys():
        d.changes.append(Change("removed", "device", new.name, device=name))
    for name in nd.keys() & od.keys():
        oa = {"node_id": od[name].node_id, "address": od[name].address, "short": od[name].short,
              "title": text(od[name].title, lang)}
        na = {"node_id": nd[name].node_id, "address": nd[name].address, "short": nd[name].short,
              "title": text(nd[name].title, lang)}
        for fld, a, b in _attrs_diff(oa, na, DEVICE_FIELDS):
            d.changes.append(Change("changed", "device", new.name, device=name, field=fld, old=a, new=b))

    of = {f.name: f for f in old.all_frames()}
    nf = {f.name: f for f in new.all_frames()}
    for f in old.all_frames():
        if f.name not in nf:
            d.changes.append(_frame_change("removed", new.name, f))
    for f in new.all_frames():
        if f.name not in of:
            d.changes.append(_frame_change("added", new.name, f))
            continue
        o = of[f.name]
        for fld, a, b in _attrs_diff(_frame_attrs(o, lang), _frame_attrs(f, lang), FRAME_FIELDS):
            d.changes.append(_frame_change("changed", new.name, f, field=fld, old=a, new=b))
        _diff_signals(d, new.name, o, f, lang)


def _diff_signals(d: MapDiff, bus: str, of: Frame, nf: Frame, lang: str) -> None:
    base = {"bus": bus, "frame": nf.name, "can_id": hex_id(nf.can_id, nf.extended),
            "device": nf.device.name if nf.device else ""}
    os_ = {s.name: s for s in of.layout}
    ns = {s.name: s for s in nf.layout}
    for s in of.layout:
        if s.name not in ns:
            d.changes.append(Change("removed", "signal", signal=s.name, **base,
                                    old=(s.start_bit, s.bit_length)))
    for s in nf.layout:
        if s.name not in os_:
            d.changes.append(Change("added", "signal", signal=s.name, **base, new=(s.start_bit, s.bit_length)))
            continue
        o = os_[s.name]
        for fld, a, b in _attrs_diff(_signal_attrs(o, lang), _signal_attrs(s, lang), SIGNAL_FIELDS):
            d.changes.append(Change("changed", "signal", signal=s.name, field=fld, old=a, new=b, **base))
        # значения enum
        ov = {v: ev for v, ev in enum_entries(o.values)}
        nv = {v: ev for v, ev in enum_entries(s.values)}
        for v in sorted(ov.keys() - nv.keys()):
            d.changes.append(Change("removed", "value", signal=s.name, item=str(v), old=ov[v].name, **base))
        for v in sorted(nv.keys() - ov.keys()):
            d.changes.append(Change("added", "value", signal=s.name, item=str(v), new=nv[v].name, **base))
        for v in sorted(nv.keys() & ov.keys()):
            if ov[v].name != nv[v].name:
                d.changes.append(Change("changed", "value", signal=s.name, item=str(v), field="name",
                                        old=ov[v].name, new=nv[v].name, **base))
            elif text(ov[v].description, lang) != text(nv[v].description, lang):
                d.changes.append(Change("changed", "value", signal=s.name, item=str(v), field="description",
                                        old=text(ov[v].description, lang),
                                        new=text(nv[v].description, lang), **base))
        # флаги
        ofl = {x.name: x for x in o.flags or []}
        nfl = {x.name: x for x in s.flags or []}
        for n in [x.name for x in o.flags or []]:
            if n not in nfl:
                d.changes.append(Change("removed", "flag", signal=s.name, item=n, old=ofl[n].bit, **base))
        for x in s.flags or []:
            if x.name not in ofl:
                d.changes.append(Change("added", "flag", signal=s.name, item=x.name, new=x.bit, **base))
                continue
            y = ofl[x.name]
            oa = {"bit": y.bit, "bit_length": y.bit_length, "description": text(y.description, lang)}
            na = {"bit": x.bit, "bit_length": x.bit_length, "description": text(x.description, lang)}
            for fld, a, b in _attrs_diff(oa, na, FLAG_FIELDS):
                d.changes.append(Change("changed", "flag", signal=s.name, item=x.name, field=fld,
                                        old=a, new=b, **base))


# --------------------------------------------------------------------------- changelog

_T = {
    "ru": {
        "added": "добавлен", "removed": "удалён", "changed": "изменён",
        "bus": "шина", "device": "устройство", "frame": "кадр", "signal": "сигнал",
        "flag": "флаг", "value": "значение", "bits": "биты", "byte": "байт",
        "added_n": "добавлено", "removed_n": "удалено", "changed_n": "изменено",
        "none": "Изменений нет.",
    },
    "en": {
        "added": "added", "removed": "removed", "changed": "changed",
        "bus": "bus", "device": "device", "frame": "frame", "signal": "signal",
        "flag": "flag", "value": "value", "bits": "bits", "byte": "byte",
        "added_n": "added", "removed_n": "removed", "changed_n": "changed",
        "none": "No changes.",
    },
}


def _fmt(v: Any) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return fmt_num(v)
    if isinstance(v, list):
        return ", ".join(_fmt(x) for x in v)
    return str(v)


def _fmt_field(fld: str, v: Any) -> str:
    if fld in ("can_id", "node_id", "address", "pgn") and isinstance(v, int):
        return {"can_id": f"0x{v:03X}", "pgn": f"0x{v:04X}"}.get(fld, f"0x{v:02X}")
    return _fmt(v)


def _bits(start_len) -> str:
    start, length = start_len
    return str(start) if length == 1 else f"{start}–{start + length - 1}"


def changelog_lines(diff: MapDiff, lang: str = "ru") -> list[str]:
    T = _T.get(lang, _T["ru"])
    lines = []
    for c in diff.changes:
        frame = f"{c.can_id} {c.frame}".strip()
        if c.scope == "bus":
            lines.append(f"{T[c.kind].capitalize()} {T['bus']} {c.bus}")
        elif c.scope == "device":
            if c.kind == "changed":
                lines.append(f"{c.device}: {c.field} {_fmt_field(c.field, c.old)} → {_fmt_field(c.field, c.new)}")
            else:
                lines.append(f"{T[c.kind].capitalize()} {T['device']} {c.device}")
        elif c.scope == "frame":
            if c.kind == "changed":
                lines.append(f"{frame}: {c.field} {_fmt_field(c.field, c.old)} → {_fmt_field(c.field, c.new)}")
            else:
                dev = f" ({c.device})" if c.device else ""
                lines.append(f"{T[c.kind].capitalize()} {T['frame']} {frame}{dev}")
        elif c.scope == "signal":
            if c.kind == "changed":
                lines.append(f"{frame}: {c.signal}.{c.field} {_fmt(c.old)} → {_fmt(c.new)}")
            else:
                pos = c.new if c.kind == "added" else c.old
                lines.append(f"{frame}: {T[c.kind]} {T['signal']} {c.signal} ({T['bits']} {_bits(pos)})")
        elif c.scope == "value":
            if c.kind == "changed":
                lines.append(f"{frame}: {c.signal} = {c.item}: {_fmt(c.old)} → {_fmt(c.new)}")
            else:
                name = c.new if c.kind == "added" else c.old
                lines.append(f"{frame}: {c.signal}: {T[c.kind + '_n']} {T['value']} {c.item} = {name}")
        elif c.scope == "flag":
            if c.kind == "changed":
                lines.append(f"{frame}: {c.signal}.{c.item}.{c.field} {_fmt(c.old)} → {_fmt(c.new)}")
            else:
                bit = c.new if c.kind == "added" else c.old
                lines.append(f"{frame}: {c.signal}: {T[c.kind]} {T['flag']} {c.item} ({T['bits']} {bit})")
    return lines


def render_diff(diff: MapDiff, fmt: str = "text", lang: str = "ru") -> str:
    if fmt == "json":
        return diff.to_json()
    lines = changelog_lines(diff, lang)
    if not lines:
        return _T.get(lang, _T["ru"])["none"]
    if fmt == "md":
        head = f"## {diff.old_version} → {diff.new_version}\n\n"
        return head + "\n".join(f"- {line}" for line in lines)
    return "\n".join(lines)
