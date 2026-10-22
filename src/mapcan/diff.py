"""Comparison of two map versions at the level of frames and signals, changelog generation."""

from __future__ import annotations

import json
import re
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
    item: str = ""           # flag or enum value
    field: str = ""          # changed field
    old: Any = None
    new: Any = None
    breaking: bool = False   # devices built against the old version misread the bus (see is_breaking)


@dataclass
class MapDiff:
    old_version: str
    new_version: str
    changes: list[Change] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.changes

    @property
    def breaking(self) -> list[Change]:
        return [c for c in self.changes if c.breaking]

    def to_dict(self) -> dict:
        return {"old_version": self.old_version, "new_version": self.new_version,
                "changes": [asdict(c) for c in self.changes]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)


DEVICE_FIELDS = ("node_id", "address", "short", "title")
FRAME_FIELDS = ("can_id", "canopen", "length", "direction", "mode", "cycle_ms", "inhibit_ms", "timeout_ms",
                "extended", "brs",
                "device", "pgn", "priority", "sender", "receivers", "description")
SIGNAL_FIELDS = ("start_bit", "bit_length", "byte_order", "representation", "encoding", "factor", "offset",
                 "unit",
                 "min", "max", "initial", "source", "invalid_raw", "multiplexer", "mux", "description")
FLAG_FIELDS = ("bit", "bit_length", "description")

# Fields whose change makes a device built against the old version send or read the bus differently
BREAKING_FIELDS = {
    "device": {"node_id", "address"},
    "frame": {"can_id", "canopen", "length", "extended", "pgn", "priority"},
    "signal": {"start_bit", "bit_length", "byte_order", "representation", "encoding", "factor", "offset",
               "multiplexer", "mux"},
    "flag": {"bit", "bit_length"},
    "value": {"name"},
}


def _narrowed(fld: str, old: Any, new: Any) -> bool:
    """A limit (min or max) admits fewer values than before; a limit set where there was none does too."""
    if new is None:
        return False
    if old is None:
        return True
    try:
        return new > old if fld == "min" else new < old
    except TypeError:
        return True


def is_breaking(c: Change) -> bool:
    """The change breaks devices built against the old version of the map.

    Removing a bus, frame, signal, flag or value breaks them; so do moving or rescaling a signal, changing the
    identifier or length of a frame, renaming or renumbering a value and narrowing a limit. Additions, texts,
    units of display, timing and widened limits do not. A removed device is not breaking by itself: its frames
    are listed as removed.
    """
    if c.kind == "added":
        return False
    if c.kind == "removed":
        return c.scope != "device"
    if c.scope == "signal" and c.field in ("min", "max"):
        return _narrowed(c.field, c.old, c.new)
    return c.field in BREAKING_FIELDS.get(c.scope, ())


def _invalid_text(s: Signal) -> str | None:
    """invalid_raw as one comparable text: "not_available 0xFF; error 0xFE00..0xFEFF"."""
    parts = [f"{meaning} " + ", ".join(f"0x{lo:X}" if lo == hi else f"0x{lo:X}..0x{hi:X}" for lo, hi in ranges)
             for meaning, ranges in s.invalid_ranges.items()]
    return "; ".join(parts) or None


def _frame_attrs(f: Frame, langs: tuple[str, str]) -> dict:
    return {
        "can_id": f.can_id, "canopen": f.canopen, "length": f.length, "direction": f.direction,
        "mode": f.mode, "cycle_ms": f.cycle_ms, "inhibit_ms": f.inhibit_ms, "timeout_ms": f.timeout_ms,
        "extended": f.extended, "brs": f.bit_rate_switch, "device": f.device.name if f.device else None,
        "pgn": f.pgn, "priority": f.priority, "sender": f.sender_name, "receivers": list(f.receivers),
        "description": text(f.description, *langs),
    }


def _signal_attrs(s: Signal, langs: tuple[str, str]) -> dict:
    return {
        "start_bit": s.start_bit, "bit_length": s.bit_length, "byte_order": s.byte_order,
        "representation": s.representation, "encoding": s.encoding,
        "factor": s.factor, "offset": s.offset, "unit": s.unit,
        "min": s.min, "max": s.max, "initial": s.initial, "source": s.source,
        "invalid_raw": _invalid_text(s),
        "multiplexer": s.multiplexer, "mux": s.mux_values,
        "description": text(s.description, *langs),
    }


def _attrs_diff(old: dict, new: dict, names) -> list[tuple[str, Any, Any]]:
    return [(n, old.get(n), new.get(n)) for n in names if old.get(n) != new.get(n)]


def diff_maps(old: MapCan, new: MapCan, lang: str | None = None) -> MapDiff:
    langs = (lang or new.lang, new.lang)   # the requested language, then the document language
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
        _diff_bus(d, ob[name], nb[name], langs)
    for c in d.changes:
        c.breaking = is_breaking(c)
    return d


def _frame_change(kind, bus: str, f: Frame, **kw) -> Change:
    return Change(kind, "frame", bus, frame=f.name, can_id=hex_id(f.can_id, f.extended),
                  device=f.device.name if f.device else "", **kw)


def _diff_bus(d: MapDiff, old: Bus, new: Bus, langs: tuple[str, str]) -> None:
    od = {x.name: x for x in old.devices}
    nd = {x.name: x for x in new.devices}
    for name in nd.keys() - od.keys():
        d.changes.append(Change("added", "device", new.name, device=name))
    for name in od.keys() - nd.keys():
        d.changes.append(Change("removed", "device", new.name, device=name))
    for name in nd.keys() & od.keys():
        oa = {"node_id": od[name].node_id, "address": od[name].address, "short": od[name].short,
              "title": text(od[name].title, *langs)}
        na = {"node_id": nd[name].node_id, "address": nd[name].address, "short": nd[name].short,
              "title": text(nd[name].title, *langs)}
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
        for fld, a, b in _attrs_diff(_frame_attrs(o, langs), _frame_attrs(f, langs), FRAME_FIELDS):
            d.changes.append(_frame_change("changed", new.name, f, field=fld, old=a, new=b))
        _diff_signals(d, new.name, o, f, langs)


def _diff_signals(d: MapDiff, bus: str, of: Frame, nf: Frame, langs: tuple[str, str]) -> None:
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
        for fld, a, b in _attrs_diff(_signal_attrs(o, langs), _signal_attrs(s, langs), SIGNAL_FIELDS):
            d.changes.append(Change("changed", "signal", signal=s.name, field=fld, old=a, new=b, **base))
        # enum values
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
            elif text(ov[v].description, *langs) != text(nv[v].description, *langs):
                d.changes.append(Change("changed", "value", signal=s.name, item=str(v), field="description",
                                        old=text(ov[v].description, *langs),
                                        new=text(nv[v].description, *langs), **base))
        # flags
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
            oa = {"bit": y.bit, "bit_length": y.bit_length, "description": text(y.description, *langs)}
            na = {"bit": x.bit, "bit_length": x.bit_length, "description": text(x.description, *langs)}
            for fld, a, b in _attrs_diff(oa, na, FLAG_FIELDS):
                d.changes.append(Change("changed", "flag", signal=s.name, item=x.name, field=fld,
                                        old=a, new=b, **base))


# --------------------------------------------------------------------------- nodes of the new version


NodeStatus = Literal["added", "modified"]


def changed_paths(diff: MapDiff, new: MapCan) -> dict[tuple, NodeStatus]:
    """Nodes of the new map version touched by the changes: path in the YAML → added or modified.

    A removed node marks its owner as modified (a frame: its device or bus, a signal: its frame),
    a changed value or flag marks its signal. Ancestors of marked nodes are not marked.
    """
    buses = {b.name: b for b in new.buses}
    out: dict[tuple, NodeStatus] = {}

    def mark(path, status: NodeStatus) -> None:
        if path and out.get(tuple(path)) != "added":
            out[tuple(path)] = status

    for c in diff.changes:
        bus = buses.get(c.bus)
        if bus is None:
            continue
        if c.scope == "bus":
            mark(bus._path, "added" if c.kind == "added" else "modified")
            continue
        if c.scope == "device":
            dev = next((d for d in bus.devices if d.name == c.device), None)
            if c.kind == "removed" or dev is None:
                mark(bus._path, "modified")
            else:
                mark(dev._path, "added" if c.kind == "added" else "modified")
            continue
        frame = next((f for f in bus.all_frames() if f.name == c.frame), None)
        if frame is None:
            # Removed frame: its device changed if it is still there, otherwise the bus
            dev = next((d for d in bus.devices if d.name == c.device), None)
            mark(dev._path if dev is not None else bus._path, "modified")
            continue
        if c.scope == "frame":
            mark(frame._path, "added" if c.kind == "added" else "modified")
            continue
        sig = next((s for s in frame.signals if s.name == c.signal), None)
        if sig is None:
            mark(frame._path, "modified")       # removed signal or a signal of an SDO exchange
        elif c.scope == "signal":
            mark(sig._path, "added" if c.kind == "added" else "modified")
        elif c.scope == "flag" and c.kind != "removed":
            flag = next((x for x in sig.flags or [] if x.name == c.item), None)
            mark(flag._path if flag is not None else sig._path, "added" if c.kind == "added" else "modified")
        else:
            mark(sig._path, "modified")
    return out


# --------------------------------------------------------------------------- changelog

_T = {
    "ru": {
        "added": "добавлен", "removed": "удалён", "changed": "изменён",
        "bus": "шина", "device": "устройство", "frame": "кадр", "signal": "сигнал",
        "flag": "флаг", "value": "значение", "bits": "биты", "byte": "байт",
        "added_n": "добавлено", "removed_n": "удалено", "changed_n": "изменено",
        "none": "Изменений нет.", "breaking": "несовместимо",
    },
    "en": {
        "added": "added", "removed": "removed", "changed": "changed",
        "bus": "bus", "device": "device", "frame": "frame", "signal": "signal",
        "flag": "flag", "value": "value", "bits": "bits", "byte": "byte",
        "added_n": "added", "removed_n": "removed", "changed_n": "changed",
        "none": "No changes.", "breaking": "breaking",
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


def bump_version(version: str) -> str:
    """Next version: 1.2.3 → 1.2.4; a non-semantic version stays as is, an empty one becomes 0.1.0."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", version or "")
    return f"{m[1]}.{m[2]}.{int(m[3]) + 1}" if m else version or "0.1.0"


def release_draft(new: MapCan, old: MapCan | None, tagged) -> dict:
    """Draft of a release of the map version ``new``: {version, recorded, changes}.

    ``old`` is the map of the previous release (or of the last commit), ``None`` if there were no releases yet;
    ``tagged(version)`` tells whether that version already has a tag. If the document version is already
    first in the revision history but not released, it is released with its recorded changes (``recorded``).
    Otherwise: the next unreleased version and the changes since ``old``.
    """
    lang = new.lang
    version = (new.document.version or "").strip()
    first = new.document.history[0] if new.document.history else None
    if first is not None and version and first.version == version and not tagged(version):
        return {"version": version, "recorded": True,
                "changes": [c for x in first.changes if (c := text(x, lang).strip())]}
    changes: list[str] = []
    old_version = None
    if old is not None:
        d = diff_maps(old, new)
        changes, old_version = changelog_lines(d, lang), d.old_version
    # The version is already released (it has a tag) or did not change since the last release: the next one
    while not version or version == old_version or tagged(version):
        bumped = bump_version(version)
        if bumped == version:
            break
        version, old_version = bumped, None
    return {"version": version, "recorded": False, "changes": changes}


def release_message(version: str, changes: list[str]) -> str:
    """Message of the release commit and tag (as in the web editor's commit dialog)."""
    from .i18n import _

    if len(changes) == 1:
        return f"{version}: {changes[0]}"
    head = _("Version {version}", version=version)
    return "\n".join([head, "", *(f"- {c}" for c in changes)]) if changes else head


def render_diff(diff: MapDiff, fmt: str = "text", lang: str = "ru") -> str:
    if fmt == "json":
        return diff.to_json()
    T = _T.get(lang, _T["ru"])
    lines = changelog_lines(diff, lang)
    if not lines:
        return T["none"]
    # changelog_lines gives one line per change, in the same order
    mark = f"**{T['breaking']}:** " if fmt == "md" else f"[{T['breaking']}] "
    lines = [mark + line if c.breaking else line for c, line in zip(diff.changes, lines, strict=True)]
    if fmt == "md":
        head = f"## {diff.old_version} → {diff.new_version}\n\n"
        return head + "\n".join(f"- {line}" for line in lines)
    return "\n".join(lines)
