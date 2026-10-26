"""Edits of a map's text for the language server: quick fixes, renaming and references,
adding, duplicating and deleting nodes.

Edits are made in the text keeping the indents, comments and style (block or "{…}").
Positions are 0-based, as in :mod:`mapcan.lsp.analysis`.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import model as M
from .. import upgrade as U
from ..bits import occupied_bits
from ..canopen import CANOPEN_DLC, FUNCTION_CODES, compute_id
from ..i18n import _
from ..units import UNITS
from ..upgrade import upgrade_node
from ..validate import STYLE_RE
from .analysis import Analysis, Path_, Pos, _txt, doc_language, enum_choices, model_for, raw_at_path

_PLAIN = re.compile(r"^[A-Za-z0-9_.+-]+$")


@dataclass
class Edit:
    start: Pos
    end: Pos
    text: str


@dataclass
class Action:
    title: str
    edits: list[Edit]
    preferred: bool = False
    diagnostics: list[int] = field(default_factory=list)   # indices of the diagnostics it fixes


def yaml_scalar(value: str) -> str:
    """Text to write in the YAML: as is if it is a plain word, otherwise in double quotes."""
    if _PLAIN.match(value) and not re.fullmatch(r"(?i)true|false|yes|no|on|off|null|~|[-+]?[\d.]+(e[-+]?\d+)?", value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# --------------------------------------------------------------------------- #
# Access to nodes
# --------------------------------------------------------------------------- #


def raw_at(a: Analysis, path: Path_):
    obj = a.raw
    for el in path:
        try:
            obj = obj[el]
        except (KeyError, IndexError, TypeError):
            return None
    return obj


def value_range(a: Analysis, path: Path_) -> tuple[Pos, Pos] | None:
    n = a.nodes.get(path)
    return (n.start, a.token_end(n.start)) if n else None


def key_range(a: Analysis, path: Path_) -> tuple[Pos, Pos] | None:
    """Position of the key ``path[-1]`` (left of the value on the same line)."""
    n = a.nodes.get(path)
    if n is None or not path or isinstance(path[-1], int):
        return None
    line, col = n.start
    key = re.escape(str(path[-1]))
    m = re.search(rf"({key})\s*:\s*$", a.lines[line][:col])
    if m:
        return (line, m.start(1)), (line, m.end(1))
    # A block list or mapping: the value starts on the next line, the key is above
    if a.lines[line][:col].strip() in ("", "-"):
        for i in range(line - 1, -1, -1):
            m = re.match(rf"^\s*(?:-\s+)?({key})\s*:\s*(?:#.*)?$", a.lines[i])
            if m:
                return (i, m.start(1)), (i, m.end(1))
            if a.lines[i].strip() and not a.lines[i].lstrip().startswith("#"):
                break
    return None


def _is_flow(a: Analysis, path: Path_) -> bool:
    n = a.nodes.get(path)
    return n is not None and a.lines[n.start[0]][n.start[1]:n.start[1] + 1] in ("{", "[")


def set_value(a: Analysis, path: Path_, text: str) -> list[Edit]:
    """Replace a scalar value or add the key to the parent mapping."""
    if path in a.nodes and not isinstance(raw_at(a, path), (dict, list)):
        start, end = value_range(a, path)
        return [Edit(start, end, text)]
    return insert_key(a, path[:-1], str(path[-1]), text)


def insert_key(a: Analysis, map_path: Path_, key: str, text: str) -> list[Edit]:
    """Add ``key: text`` to the mapping at ``map_path``, at its place in the canonical order (mapcan fmt)."""
    from ..fmt import insert_position

    n = a.nodes.get(map_path)
    if n is None:
        return []
    raw = raw_at(a, map_path)
    keys = list(raw) if isinstance(raw, dict) else []
    i = insert_position(map_path, keys, key)
    before = key_range(a, map_path + (keys[i],)) if i is not None else None
    if before is not None:
        line, col = before[0]
        if _is_flow(a, map_path):
            return [Edit((line, col), (line, col), f"{key}: {text}, ")]
        if not a.lines[line][:col].strip():         # not the first key on a "- " line
            while line > 0 and a.lines[line - 1].strip().startswith("#") and \
                    len(a.lines[line - 1]) - len(a.lines[line - 1].lstrip()) == col:
                line -= 1                           # the comment above the key stays with it
            return [Edit((line, 0), (line, 0), f"{' ' * col}{key}: {text}\n")]
    if _is_flow(a, map_path):
        close = a._closing(n.start)
        if close is None:
            return []
        pos = (close[0], close[1] - 1)
        return [Edit(pos, pos, f", {key}: {text}")]
    _, (end_line, _end_col) = a.block(map_path)
    pos = (end_line + 1, 0)
    return [Edit(pos, pos, f"{' ' * n.start[1]}{key}: {text}\n")]


def delete_key(a: Analysis, path: Path_) -> list[Edit]:
    """Remove a key with a scalar value if it is written on a line of its own or inside "{…}"."""
    kr = key_range(a, path)
    vr = value_range(a, path)
    if kr is None or vr is None:
        return []
    (line, kcol), (_, vend) = kr[0], vr[1]
    text = a.lines[line]
    if _is_flow(a, path[:-1]):
        after = re.match(r"\s*,\s*", text[vend:])
        if after:
            return [Edit((line, kcol), (line, vend + after.end()), "")]
        before = re.search(r",\s*$", text[:kcol])
        return [Edit((line, before.start() if before else kcol), (line, vend), "")]
    if text[:kcol].strip():
        return []      # the key is on a "- …" line or after another key
    return [Edit((line, 0), (line + 1, 0), "")]


# --------------------------------------------------------------------------- #
# Quick fixes
# --------------------------------------------------------------------------- #


def _suggest(word: str, options, cutoff: float = 0.6) -> list[str]:
    return difflib.get_close_matches(word, [o for o in options if o != word], n=3, cutoff=cutoff)


def _bus_devices(a: Analysis, path: Path_) -> list[str]:
    devices = raw_at(a, path[:2] + ("devices",)) if len(path) >= 2 else None
    return [d["name"] for d in devices or [] if isinstance(d, dict) and isinstance(d.get("name"), str)]


def to_style(name: str, style: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])", name) if w]
    if style == "snake_case":
        return "_".join(w.lower() for w in words)
    if style == "UPPER_SNAKE":
        return "_".join(w.upper() for w in words)
    if style == "camelCase":
        return words[0].lower() + "".join(w.capitalize() for w in words[1:]) if words else name
    if style == "PascalCase":
        return "".join(w.capitalize() for w in words)
    return name


def quick_fixes(a: Analysis, diags: list[tuple[str, list, Pos]]) -> list[Action]:
    """Fixes for the diagnostics (code, node path, start); ``Action.diagnostics`` are their indices."""
    out: list[Action] = []
    for i, (code, node, start) in enumerate(diags):
        path = tuple(node or ())
        acts = _yaml_fixes(a, start) if code == "yaml" else _fixes_for(a, code, path)
        for act in acts:
            act.diagnostics = [i]
            out.append(act)
    return out


def _fixes_for(a: Analysis, code: str, path: Path_) -> list[Action]:
    n = a.nodes.get(path)
    if code in ("number-comma", "number-cyrillic-x", "number-quoted") and n:
        line, col = n.start
        text = a.lines[line][col:]
        patterns = {
            "number-comma": (r"[+-]?\d+,\d+", lambda s: s.replace(",", ".")),
            "number-cyrillic-x": (r"0[хХ][0-9a-fA-F]+", lambda s: "0x" + s[2:]),
            "number-quoted": (r"""(["'])\s*0[xX][0-9a-fA-F]+\s*\1""", lambda s: s[1:-1].strip()),
        }
        pattern, fix = patterns[code]
        m = re.match(pattern, text)
        if m:
            new = fix(m.group(0))
            return [Action(_("Change to {value}", value=new),
                           [Edit((line, col), (line, col + m.end()), new)], preferred=True)]
        return []

    if code == "unknown-receiver" or code == "unknown-sender":
        value = raw_at(a, path)
        vr = value_range(a, path)
        if not isinstance(value, str) or vr is None:
            return []
        return [Action(_("Change to {value!r}", value=s), [Edit(*vr, s)], preferred=k == 0)
                for k, s in enumerate(_suggest(value, _bus_devices(a, path), 0.4))]

    if code == "schema" and path and isinstance(path[-1], str):
        key = path[-1]
        cls = model_for(path[:-1])
        if cls is not None and key not in cls.model_fields:
            kr = key_range(a, path)
            fields = [f for f in cls.model_fields if not f.startswith("_")]
            return [Action(_("Change to {value!r}", value=s), [Edit(*kr, s)], preferred=k == 0)
                    for k, s in enumerate(_suggest(key, fields))] if kr else []
        value = raw_at(a, path)
        choices = enum_choices().get(key) if cls is not None and key in cls.model_fields else None
        vr = value_range(a, path)
        if isinstance(value, str) and choices and value not in choices and vr:
            return [Action(_("Change to {value!r}", value=s), [Edit(*vr, s)], preferred=k == 0)
                    for k, s in enumerate(_suggest(value, choices, 0.4))]
        return []

    if code == "deprecated-key":
        from ..web.yamlops import migrate_renames_text
        new = migrate_renames_text(a.text)
        return [Action(_("Rename the former fields of the whole map (mapcan migrate)"),
                       [minimal_edit(a.text, new)], preferred=True)] if new != a.text else []

    if code == "format-v1":
        from ..web.yamlops import migrate_format_text
        new = migrate_format_text(a.text)
        return [Action(_("Rewrite this file in format version 2 (mapcan migrate)"),
                       [minimal_edit(a.text, new)], preferred=True)] if new != a.text else []

    if code == "direction-deprecated":
        from ..web.yamlops import migrate_directions_text
        new = migrate_directions_text(a.text)
        return [Action(_("Remove direction from the frames of this file (mapcan migrate)"),
                       [minimal_edit(a.text, new)], preferred=True)] if new != a.text else []

    if code == "can-id-range" and path and path[-1] == "id":
        return [Action(_("Add extended: true"), set_value(a, path[:-1] + ("extended",), "true"),
                       preferred=True)]

    if code == "j1939-destination":
        edits = delete_key(a, path) if path and path[-1] == "destination" else []
        return [Action(_("Remove destination"), edits)] if edits else []

    if code == "version-redundant":
        from ..web.yamlops import migrate_version_text
        new = migrate_version_text(a.text)
        return [Action(_("Remove the document's version and date repeated from the revision history "
                         "(mapcan migrate)"), [minimal_edit(a.text, new)], preferred=True)] if new != a.text else []

    if code == "history-version":
        hv = value_range(a, ("document", "history", 0, "version"))
        if hv and ("document", "version") in a.nodes:
            latest = a.lines[hv[0][0]][hv[0][1]:hv[1][1]]
            return [Action(_("Change to {value}", value=latest),
                           set_value(a, ("document", "version"), latest), preferred=True)]
        return []

    if code == "name-style" and path:
        name = raw_at(a, path)
        if isinstance(name, dict):      # an enum value written as {name: …, description: …}
            name = name.get("name")
        style = _style_for(a, path)
        if isinstance(name, str) and style:
            new = to_style(name, style)
            if new and new != name and STYLE_RE[style].match(new):
                edits = rename_edits(a, path, new) if path[-1] == "name" else _rename_key(a, path, new)
                return [Action(_("Rename to {value!r}", value=new), edits, preferred=True)] if edits else []
        return []

    if code in ("bit-overlap", "signal-out-of-frame"):
        act = move_to_free_bits(a, path)
        return [act] if act else []

    if code == "duplicate-can-id" and path and path[-1] == "canopen":
        # Another type of the same purpose (PDO TX → a free PDO TX) whose ID is not taken
        current = raw_at(a, path)
        prefix = re.sub(r"\d+$", "", current) if isinstance(current, str) else ""
        free = [t["type"] for t in frame_types(a, path[:-1])
                if t["taken"] is None and t["type"] != current and prefix.startswith("pdo_")
                and t["type"].startswith(prefix)]
        vr = value_range(a, path)
        return [Action(_("Change type to {value}", value=t), [Edit(*vr, t)], preferred=k == 0)
                for k, t in enumerate(free)] if vr else []
    return []


def _yaml_fixes(a: Analysis, start: Pos) -> list[Action]:
    """"-name: x" instead of "- name: x": a list item without a space after "-"."""
    line = start[0]
    m = re.match(r"^(\s*)-(?=[A-Za-z_\"'{\[])", a.lines[line]) if line < len(a.lines) else None
    if not m:
        return []
    pos = (line, m.end())
    return [Action(_("Insert a space after '-'"), [Edit(pos, pos, " ")], preferred=True)]


def _style_for(a: Analysis, path: Path_) -> str | None:
    lint = a.map.lint if a.map else M.LintRules()
    if "values" in path:
        return lint.value_name
    owner = path[-3] if len(path) >= 3 and path[-1] == "name" else None
    return {"signals": lint.signal_name, "flags": lint.signal_name, "frames": lint.frame_name,
            "devices": lint.device_name}.get(owner)


def _rename_key(a: Analysis, path: Path_, new: str) -> list[Edit]:
    """Name of an enum value: its ``name`` or the value's string itself."""
    vr = value_range(a, path + ("name",)) if (path + ("name",)) in a.nodes else value_range(a, path)
    return [Edit(*vr, yaml_scalar(new))] if vr else []


# --------------------------------------------------------------------------- #
# Free bits
# --------------------------------------------------------------------------- #


def _coexist(a: M.Signal, b: M.Signal) -> bool:
    if a.mux is None or b.mux is None:
        return True
    return bool(set(a.mux_values) & set(b.mux_values))


def free_start(frame: M.Frame, length: int, step: int, skip: M.Signal | None = None) -> int | None:
    """First position (a multiple of ``step``) of a little-endian field of ``length`` bits that overlaps nothing."""
    taken: set[int] = set()
    for s in frame.signals:
        if s is not skip and (skip is None or _coexist(s, skip)):
            taken.update(occupied_bits(s.start_bit or 0, s.bit_length or 1, s.byte_order == "big_endian"))
    for start in range(0, frame.length * 8 - length + 1, step):
        if not taken & set(range(start, start + length)):
            return start
    return None


def move_to_free_bits(a: Analysis, path: Path_) -> Action | None:
    if a.map is None or len(path) < 2 or path[-2] != "signals":
        return None
    frame = _find(a.map, path[:-2])
    sig = _find(a.map, path)
    raw = raw_at(a, path)
    if not isinstance(frame, M.Frame) or not isinstance(sig, M.Signal) or not isinstance(raw, dict):
        return None
    if sig.byte_order == "big_endian":
        return None
    length = sig.bit_length or 1
    if "start_bit" in raw:
        start = free_start(frame, length, 1, sig)
        edits = set_value(a, path + ("start_bit",), str(start)) if start is not None else []
    elif "bit" in raw:
        start = free_start(frame, length, 1, sig)
        edits = [] if start is None else (set_value(a, path + ("byte",), str(start // 8))
                                          + set_value(a, path + ("bit",), str(start % 8)))
    else:
        # Without "bit" the field starts at a byte boundary; "bit" cannot be added, it would change the default length
        start = free_start(frame, length, 8, sig)
        edits = set_value(a, path + ("byte",), str(start // 8)) if start is not None else []
    if not edits:
        return None
    hi = start + length - 1
    bits = _("bit {bit}", bit=start) if length == 1 else _("bits {lo}–{hi}", lo=start, hi=hi)
    return Action(_("Move to free bits: {bits}", bits=bits), edits, preferred=True)


def _find(cmap: M.MapCan, path: Path_):
    obj = cmap
    for el in path:
        try:
            obj = obj[el] if isinstance(el, int) else getattr(obj, el)
        except (IndexError, AttributeError, TypeError):
            return None
    return obj


# --------------------------------------------------------------------------- #
# References to devices, renaming
# --------------------------------------------------------------------------- #


def _frame_paths(a: Analysis, bus_path: Path_) -> list[Path_]:
    out = [bus_path + ("frames", i) for i, _ in enumerate(raw_at(a, bus_path + ("frames",)) or [])]
    for di, dev in enumerate(raw_at(a, bus_path + ("devices",)) or []):
        frames = dev.get("frames") if isinstance(dev, dict) else None
        out += [bus_path + ("devices", di, "frames", i) for i, _ in enumerate(frames or [])]
    return out


def device_refs(a: Analysis, bus_path: Path_, name: str) -> tuple[Path_ | None, list[Path_]]:
    """(declaration of the device, references to it in receivers and sender) on the bus, in every file of the map
    (the data together with the included files): :func:`value_range` of ``a`` finds those of its own text."""
    bus = raw_at_path(a.data, bus_path)
    decl = None
    for di, dev in enumerate((bus.get("devices") if isinstance(bus, dict) else None) or []):
        if isinstance(dev, dict) and dev.get("name") == name:
            decl = bus_path + ("devices", di, "name")
            break
    refs = []
    for fp, frame in _bus_frames_of(bus, list(bus_path)):
        fp = tuple(fp)
        rec = frame.get("receivers")
        for i, r in enumerate(rec if isinstance(rec, list) else []):
            if r == name:
                refs.append(fp + ("receivers", i))
        if frame.get("sender") == name:
            refs.append(fp + ("sender",))
    return decl, refs


def name_at(a: Analysis, pos: Pos) -> Path_ | None:
    """Path of the name under the cursor: ``…name`` of any node or a reference to a device in receivers/sender."""
    for path, n in a.nodes.items():
        if not path or n.start[0] != pos[0]:
            continue
        is_name = path[-1] == "name" and isinstance(raw_at(a, path), str)
        is_ref = (path[-1] == "sender" or (len(path) >= 2 and path[-2] == "receivers")) \
            and isinstance(raw_at(a, path), str)
        if (is_name or is_ref) and n.start <= pos <= a.token_end(n.start):
            return path
    return None


def _device_target(a: Analysis, path: Path_) -> tuple[Path_, str] | None:
    """(bus path, device name) if ``path`` is the name of a device or a reference to it."""
    if len(path) < 2 or path[0] != "buses":
        return None
    value = raw_at(a, path)
    is_decl = len(path) == 5 and path[2] == "devices" and path[4] == "name"
    is_ref = path[-1] == "sender" or (len(path) >= 2 and path[-2] == "receivers")
    return (path[:2], value) if (is_decl or is_ref) and isinstance(value, str) else None


def definition(a: Analysis, pos: Pos) -> tuple[Pos, Pos] | None:
    found = definition_location(a, pos)
    return found[1] if found and found[0] is None else None


def definition_location(a: Analysis, pos: Pos) -> tuple[str | None, tuple[Pos, Pos]] | None:
    """(file, range) of the declaration of the device under the cursor; the file is None for this text, else the
    other file of the map it is written in (a receiver in an included file declared in the main file)."""
    path = name_at(a, pos)
    target = _device_target(a, path) if path else None
    if target is None:
        return None
    decl, _refs = device_refs(a, *target)
    view = a.view_of(decl) if decl else None
    rng = value_range(view, decl) if view is not None else None
    return (a.included_file(decl), rng) if rng else None


def references(a: Analysis, pos: Pos, include_declaration: bool = True) -> list[tuple[Pos, Pos]]:
    return [r for f, r in reference_locations(a, pos, include_declaration) if f is None]


Location = tuple["str | None", tuple[Pos, Pos]]


def reference_locations(a: Analysis, pos: Pos, include_declaration: bool = True) -> list[Location]:
    """(file, range) of the name under the cursor and of the references to it; the file is None for this text,
    else the other file of the map (a device of an included file and its receivers in the main file)."""
    path = name_at(a, pos)
    target = _device_target(a, path) if path else None
    if target is None:
        return [(None, value_range(a, path))] if path and include_declaration else []
    decl, refs = device_refs(a, *target)
    return _locations(a, ([decl] if decl and include_declaration else []) + refs)


def _locations(a: Analysis, paths: list[Path_]) -> list[Location]:
    out = []
    for p in paths:
        view = a.view_of(p)
        rng = value_range(view, p) if view is not None else None
        if rng:
            out.append((a.included_file(p), rng))
    return out


def rename_edits(a: Analysis, path: Path_, new: str) -> list[Edit]:
    """A rename in this text only (see :func:`rename_files`)."""
    return rename_files(a, path, new).get(None, [])


def rename_files(a: Analysis, path: Path_, new: str) -> dict[str | None, list[Edit]]:
    """Edits of a rename in every file of the map: {None: this text, file: another file}. A device is renamed
    with the references to it on its bus, wherever they are written."""
    text = yaml_scalar(new)
    target = _device_target(a, path)
    if target is None:
        paths = [path]
    else:
        decl, refs = device_refs(a, *target)
        paths = ([decl] if decl else []) + refs
    out: dict[str | None, list[Edit]] = {}
    for file, rng in _locations(a, paths):
        out.setdefault(file, []).append(Edit(*rng, text))
    return out


# --------------------------------------------------------------------------- #
# Adding, duplicating and deleting nodes (the map tree)
# --------------------------------------------------------------------------- #


@dataclass
class TextChange:
    text: str
    cursor: Pos


def _unique(base: str, taken) -> str:
    taken = set(taken)
    if base not in taken:
        return base
    i = 2
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"


def _names(items) -> list[str]:
    return [i.get("name") for i in items or [] if isinstance(i, dict)]


def _join(a: Analysis, lines: list[str]) -> str:
    """Text of the lines with the source file's line break (CRLF or LF) and the same ending."""
    eol = "\r\n" if "\r\n" in a.text else "\n"
    return eol.join(lines) + (eol if a.text.endswith(("\n", "\r")) else "")


def _splice(lines: list[str], at_line: int, new_lines: list[str]) -> list[str]:
    return lines[:at_line] + new_lines + lines[at_line:]


def _dash_col(a: Analysis, item_path: Path_) -> int:
    line, col = a.nodes[item_path].start
    m = re.search(r"-\s*$", a.lines[line][:col])
    return m.start() if m else max(col - 2, 0)


def append_item(a: Analysis, owner: Path_, key: str, fields: list[tuple[str, str]]) -> TextChange | None:
    """Add the item ``{fields}`` to the list ``owner.key`` in that list's style."""
    lines = list(a.lines)
    items = raw_at(a, owner + (key,))
    first = f"{fields[0][0]}: {fields[0][1]}"
    if isinstance(items, list) and items and _is_flow(a, owner + (key,)):
        close = a._closing(a.nodes[owner + (key,)].start)
        if close is None:
            return None
        line, col = close[0], close[1] - 1
        flow = "{" + ", ".join(f"{k}: {v}" for k, v in fields) + "}"
        lines[line] = lines[line][:col] + ", " + flow + lines[line][col:]
        return TextChange(_join(a, lines), (line, col + 3 + len(f"{fields[0][0]}: ")))
    if isinstance(items, list) and items:
        last = owner + (key, len(items) - 1)
        dash = _dash_col(a, last)
        indent = a.nodes[last].start[1]
        at = a.block(last)[1][0] + 1
    else:
        slot = _empty_list_slot(a, owner, key, lines)
        if slot is None:
            return None
        dash, at = slot
        indent = dash + 2
    new = [" " * dash + "- " + first] + [" " * indent + f"{k}: {v}" for k, v in fields[1:]]
    lines = _splice(lines, at, new)
    return TextChange(_join(a, lines), (at, dash + 2 + len(f"{fields[0][0]}: ")))


def _empty_list_slot(a: Analysis, owner: Path_, key: str, lines: list[str]) -> tuple[int, int] | None:
    """Place of the first item of an empty or missing list ``owner.key``: (column of "-", line).
    The list's key is written to ``lines`` if needed."""
    n = a.nodes.get(owner)
    if n is None:
        return None
    kr = key_range(a, owner + (key,)) if owner + (key,) in a.nodes else None
    if kr:      # "key: []" or "key:" without a value: the items go as a block under the key
        kline = kr[0][0]
        lines[kline] = lines[kline][:kr[1][1]] + ":"
        return kr[0][1] + 2, kline + 1
    at = a.block(owner)[1][0] + 1
    lines[at:at] = [" " * n.start[1] + f"{key}:"]
    return n.start[1] + 2, at + 1


HISTORY: Path_ = ("document", "history")


def _entry_value(key: str, value: str) -> str:
    """A version like 1.2.3 without quotes (YAML does not read it as a number), anything else as text."""
    if key == "version" and re.fullmatch(r"\d+\.\d+\.\d+[\w.+-]*", value):
        return value
    return yaml_text(value)


def apply_edits(text: str, edits: list[Edit]) -> str:
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    def offset(p: Pos) -> int:
        return starts[p[0]] + p[1] if p[0] < len(lines) else len(text)

    for e in sorted(edits, key=lambda e: e.start, reverse=True):
        text = text[:offset(e.start)] + e.text + text[offset(e.end):]
    return text


def add_history(a: Analysis, entry: dict, changes: list[str]) -> TextChange | None:
    """Write the first entry of ``document.history`` (``entry`` fields: version, date, author, github and
    the changes, one per line); the document's version and date come from it, so the ones written in the
    document are removed. The cursor goes to the new entry's version."""
    from .analysis import analyze

    items = raw_at(a, HISTORY)
    if isinstance(items, list) and items and _is_flow(a, HISTORY):
        return None
    lines = list(a.lines)
    if isinstance(items, list) and items:
        first = HISTORY + (0,)
        dash, at = _dash_col(a, first), a.nodes[first].start[0]
    else:
        slot = _empty_list_slot(a, HISTORY[:-1], HISTORY[-1], lines)
        if slot is None:
            return None
        dash, at = slot
    fields = [f"{k}: {_entry_value(k, str(v))}" for k, v in entry.items() if v]
    pad = " " * (dash + 2)
    new = [" " * dash + "- " + fields[0]] + [pad + f for f in fields[1:]]
    if changes:
        new += [pad + "changes:"] + [pad + "  - " + yaml_text(c) for c in changes]
    text = _join(a, _splice(lines, at, new))
    for key in ("version", "date"):
        b = analyze(text, a.result.source.file)
        if ("document", key) in b.nodes:
            text = apply_edits(text, delete_key(b, ("document", key)))
    b = analyze(text, a.result.source.file)
    n = b.nodes.get(HISTORY + (0, "version"))
    return TextChange(text, n.start if n else (at, dash + 2))


#: PDO types in the order new frames of a CANopen device get them.
PDO_TYPES = [f"pdo_{d}{n}" for d in ("tx", "rx") for n in range(1, 5)]


def _new_frame(a: Analysis, owner: Path_) -> list[tuple[str, str]]:
    """Fields of a new frame, as in the web editor: a frame of a CANopen device gets the first free PDO type
    (the ID is computed from the type and node_id), a J1939 one a free PGN, otherwise a free explicit ID."""
    bus = raw_at(a, owner[:2]) or {}
    protocol = bus.get("protocol") or "canopen"
    device = len(owner) == 4
    taken = [raw_at(a, fp + ("name",)) for fp in _frame_paths(a, owner[:2])]
    base = f"{raw_at(a, owner + ('name',))}_frame" if device else "frame"
    fields = [("name", _unique(base, taken))]
    if protocol == "j1939":
        used = {raw_at(a, fp + ("pgn",)) for fp in _frame_paths(a, owner[:2])}
        pgn = next((p for p in range(0xFF00, 0x10000) if p not in used), 0xFF00)
        fields += [("pgn", f"0x{pgn:04X}"), ("priority", "6")]
    else:
        types = {f.get("canopen", f.get("type"))
                 for f in raw_at(a, owner + ("frames",)) or [] if isinstance(f, dict)}
        free = next((t for t in PDO_TYPES if t not in types), None) if protocol == "canopen" and device else None
        fields.append(("canopen", free) if free else ("id", f"0x{_free_id(a, owner[:2]):03X}"))
    return fields + [("length", "8"), ("cycle_ms", "100"), ("signals", "[]")]


def _free_id(a: Analysis, bus_path: Path_) -> int:
    used = set()
    if a.map is not None:
        bus = _find(a.map, bus_path)
        used = {f.can_id for f in bus.all_frames() if f.can_id is not None} if isinstance(bus, M.Bus) else set()
    else:
        for fp in _frame_paths(a, bus_path):
            fid = raw_at(a, fp + ("id",))
            if isinstance(fid, int):
                used.add(fid)
    start = max([u for u in used if u <= 0x7FF], default=0xFF) + 1
    while start in used:
        start += 1
    return start


def _free_number(values, lo: int, hi: int) -> int | None:
    used = {v for v in values if isinstance(v, int)}
    return next((v for v in range(lo, hi + 1) if v not in used), None)


def _default_title(a: Analysis, ru: str, en: str, siblings) -> str:
    """Full name of a new node in the document language: "Шина 2", "Device 3", the first free one among siblings
    (as in the web editor)."""
    lang = doc_language(a)
    base = en if lang == "en" else ru
    taken = {_txt(s.get("title"), lang) for s in siblings or [] if isinstance(s, dict)}
    n = len(siblings or []) + 1
    while f"{base} {n}" in taken:
        n += 1
    return f"{base} {n}"


def add_node(a: Analysis, path: Path_, kind: str) -> TextChange | None:
    """Add a bus (to the map), a device (to a bus), a frame (to a bus or a device) or a signal (to a frame).

    ``a`` has the text of the owner's file (:meth:`Analysis.view_of`): the node is written there."""
    if path and path not in a.nodes:
        return None
    if kind == "bus" and path == ():
        buses = raw_at(a, ("buses",)) or []
        return append_item(a, (), "buses", [("name", _unique("bus", _names(buses))),
                                            ("title", yaml_text(_default_title(a, "Шина", "Bus", buses))),
                                            ("protocol", "can")])
    if kind == "device" and len(path) == 2:
        device = new_device(a, raw_at(a, path) or {}, raw_at(a, path + ("devices",)) or [])
        fields = [(k, f"0x{v:02X}" if k in ("node_id", "address") else yaml_text(v)) for k, v in device.items()]
        return append_item(a, path, "devices", fields)
    if kind == "frame" and path and path[0] == "buses" and len(path) in (2, 4):
        return append_item(a, path, "frames", _new_frame(a, path))
    if kind == "signal" and len(path) >= 2 and path[-2] == "frames":
        return _add_signal(a, path)
    return None


def new_device(a: Analysis, bus: dict, devices: list) -> dict:
    """Fields of a new device of a bus with these devices: a free name, title and CANopen node ID or J1939
    address."""
    out = {"name": _unique("device", _names(devices)),
           "title": _default_title(a, "Устройство", "Device", devices)}
    protocol = bus.get("protocol", "canopen")
    if protocol == "canopen" and (nid := _free_number([d.get("node_id") for d in devices
                                                      if isinstance(d, dict)], 1, 127)):
        out["node_id"] = nid
    elif protocol == "j1939" and (sa := _free_number([d.get("address") for d in devices
                                                     if isinstance(d, dict)], 0, 253)) is not None:
        out["address"] = sa
    return out


def device_file(a: Analysis, bus_path: Path_, file: str | None) -> dict:
    """A new device of a bus in a file of its own (#136). Without ``file``: {file} with the default name of the
    file. With it: {device, target, text, ops}: the device, the new file and its text, and the operations that
    add it to ``include`` of the map (paths of the map). ValueError: why it cannot be made."""
    from ..web.devicefile import (
        default_device_file,
        device_file_target,
        device_file_text,
        include_ops,
        named_after_file,
    )

    data = a.data if isinstance(a.data, dict) else {}
    bus = raw_at_path(data, bus_path)
    if len(bus_path) != 2 or not isinstance(bus, dict) or not isinstance(bus.get("name"), str):
        raise ValueError(_("path not found: {path}", path=list(bus_path)))
    main = a.result.source.file
    if not main or not Path(main).is_file():
        raise ValueError(_("Save the map to a file first."))
    devices = [d for d in bus.get("devices") or [] if isinstance(d, dict)]
    device = new_device(a, bus, devices)
    if file is None:
        return {"file": default_device_file(device["name"])}
    target, line = device_file_target(Path(main), file)
    device = named_after_file(device, target, _names(devices))
    raw = a.result.raw if isinstance(a.result.raw, dict) else {}
    return {"device": device, "target": target, "ops": include_ops(raw.get("include"), line),
            "text": device_file_text(Path(main), target, bus["name"], {**device, "frames": []})}


class EditRefused(ValueError):
    """An edit that cannot be made; the message says why."""


FD_DLC = (0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64)


def _taken_bits(a: Analysis, path: Path_) -> tuple[set[int], int, bool, bool]:
    """(bits taken by the frame's signals, frame length, CAN FD bus, every signal's position is known).

    A map that does not load has no model: the signals are read from the frame's YAML one by one."""
    taken: set[int] = set()
    frame = _find(a.map, path) if a.map is not None else None
    if isinstance(frame, M.Frame):
        bus = _find(a.map, path[:2])
        for s in frame.signals:
            taken.update(occupied_bits(s.start_bit or 0, s.bit_length or 1, s.byte_order == "big_endian"))
        return taken, frame.length if frame.length is not None else 8, bool(getattr(bus, "fd", False)), True
    raw = raw_at(a, path)
    raw = raw if isinstance(raw, dict) else {}
    bus = raw_at(a, path[:2])
    known = True
    for s in raw.get("signals") or []:
        try:
            sig = M.Signal.model_validate(s)
        except ValueError:
            known = False
            continue
        taken.update(occupied_bits(sig.start_bit or 0, sig.bit_length or 1, sig.byte_order == "big_endian"))
    length = raw.get("length")
    length = length if isinstance(length, int) and not isinstance(length, bool) and length >= 0 else 8
    return taken, length, isinstance(bus, dict) and bus.get("fd") is True, known


def place_new_signal(a: Analysis, path: Path_) -> tuple[int, int, int | None] | None:
    """Place of a new signal in the frame: (start bit, bit length, new frame length or None).

    A free byte; if there is none, the frame grows by a byte (on a CAN FD bus, to the next allowed
    length); if it cannot, the first free bits (up to a byte); None: the frame has no free bits.
    When the position of some signal is unknown (the map does not load), only the bits after the
    last taken one count as free."""
    taken, length, fd, known = _taken_bits(a, path)
    first = 0 if known or not taken else max(taken) + 1
    for byte in range((first + 7) // 8, length):
        if not taken & set(range(byte * 8, byte * 8 + 8)):
            return byte * 8, 8, None
    grown = next((d for d in FD_DLC if d > length), None) if fd else length + 1 if length < 8 else None
    if grown is not None and length * 8 >= first:
        return length * 8, 8, grown
    for start in range(first, length * 8):
        if start not in taken:
            n = 1
            while n < 8 and (start + n) % 8 and start + n not in taken:
                n += 1
            return start, n, None
    return None


def _add_signal(a: Analysis, path: Path_) -> TextChange | None:
    place = place_new_signal(a, path)
    if place is None:
        raise EditRefused(_("No free bits left in the frame. Free up space or increase the frame length"))
    start, length, grown = place
    signals = raw_at(a, path + ("signals",)) or []
    fields = [("name", _unique("signal", _names(signals))), ("encoding", "number")]
    # The position in the notation the other editors write (#117)
    from ..web.yamlops import layout_keys

    fields += [(k, str(v)) for k, v in layout_keys(start, length, False).items()]
    change = append_item(a, path, "signals", fields)
    if change is None or grown is None:
        return change
    # The frame's new length goes in the same edit, before its signals
    grow = set_value(a, path + ("length",), str(grown))
    added = minimal_edit(a.text, change.text)
    shift = sum(e.text.count("\n") - (e.end[0] - e.start[0]) for e in grow if e.start < change.cursor)
    return TextChange(apply_edits(a.text, [*grow, added]), (change.cursor[0] + shift, change.cursor[1]))


def duplicate_node(a: Analysis, path: Path_) -> TextChange | None:
    """A copy of a list item right after it: the name with a suffix, a frame also gets a free ID."""
    if not path or not isinstance(path[-1], int) or path not in a.nodes:
        return None
    raw = raw_at(a, path)
    siblings = raw_at(a, path[:-1])
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        return None
    new_name = _unique(f"{raw['name']}_copy", _names(siblings))
    replace = {path + ("name",): yaml_scalar(new_name)}
    if path[-2] == "frames" and isinstance(raw.get("id"), int):
        replace[path + ("id",)] = f"0x{_free_id(a, path[:2]):03X}"
    if path[-2] == "devices":
        for key, lo, hi in (("node_id", 1, 127), ("address", 0, 253)):
            if isinstance(raw.get(key), int):
                free = _free_number([d.get(key) for d in siblings if isinstance(d, dict)], lo, hi)
                if free is not None:
                    replace[path + (key,)] = f"0x{free:02X}"
    (sl, sc), (el, ec) = a.block(path)
    lines = list(a.lines)
    if sl == el and _is_flow(a, path[:-1]):
        # An item "{…}" in a list "[…]": the copy goes after a comma on the same line
        text = _with_replacements(a, path, replace, (sl, sc), (el, ec))
        lines[sl] = lines[sl][:ec] + ", " + text + lines[sl][ec:]
        name_col = ec + 2 + (a.nodes[path + ("name",)].start[1] - sc)
        return TextChange(_join(a, lines), (sl, name_col))
    dash = _dash_col(a, path)
    block = " " * dash + _with_replacements(a, path, replace, (sl, dash), (el, len(a.lines[el])))
    new_lines = block.split("\n")
    nl, nc = a.nodes[path + ("name",)].start
    lines = _splice(lines, el + 1, new_lines)
    return TextChange(_join(a, lines), (el + 1 + nl - sl, nc))


def _with_replacements(a: Analysis, path: Path_, replace: dict, start: Pos, end: Pos) -> str:
    """Text from ``start`` to ``end`` with values replaced (all replacements are inside this text)."""
    spans = sorted((value_range(a, p), v) for p, v in replace.items() if p in a.nodes)
    out, cur = [], start
    for (s, e), v in spans:
        out.append(_slice(a, cur, s))
        out.append(v)
        cur = e
    out.append(_slice(a, cur, end))
    return "".join(out)


def _slice(a: Analysis, s: Pos, e: Pos) -> str:
    if s[0] == e[0]:
        return a.lines[s[0]][s[1]:e[1]]
    return "\n".join([a.lines[s[0]][s[1]:], *a.lines[s[0] + 1:e[0]], a.lines[e[0]][:e[1]]])


def delete_node(a: Analysis, path: Path_) -> TextChange | None:
    """Remove a list item (bus, device, frame, signal, flag, SDO exchange)."""
    if not path or not isinstance(path[-1], int) or path not in a.nodes:
        return None
    siblings = raw_at(a, path[:-1])
    (sl, sc), (el, ec) = a.block(path)
    lines = list(a.lines)
    if _is_flow(a, path[:-1]) and sl == el:
        text = lines[sl]
        after = re.match(r"\s*,\s*", text[ec:])
        if after:
            lines[sl] = text[:sc] + text[ec + after.end():]
        else:
            before = re.search(r"\s*,\s*$", text[:sc])
            lines[sl] = text[:before.start() if before else sc] + text[ec:]
        return TextChange(_join(a, lines), (sl, sc))
    del lines[sl:el + 1]
    cursor = (max(sl - 1, 0), 0)
    # The items in this text: a list of a bus of the main file has more items in an included file
    here = [i for i in range(len(siblings)) if path[:-1] + (i,) in a.nodes] if isinstance(siblings, list) else []
    if len(here) == 1:
        # The last item of a block list: "key:" → "key: []", otherwise the value would become null
        kr = key_range(a, path[:-1]) or _key_above(a, str(path[-2]), sl)
        if kr and kr[0][0] < sl:
            kline = kr[0][0]
            lines[kline] = lines[kline][:kr[1][1]] + ": []"
            cursor = (kline, kr[0][1])
    return TextChange(_join(a, lines), cursor)


def _key_above(a: Analysis, key: str, line: int) -> tuple[Pos, Pos] | None:
    """Position of the key ``key:`` of a block list whose first item is on ``line``: for a list that is not a node
    of this text (its items in this file extend a bus of the main file)."""
    for i in range(line - 1, -1, -1):
        m = re.match(rf"^\s*(?:-\s+)?({re.escape(key)})\s*:\s*(?:#.*)?$", a.lines[i])
        if m:
            return (i, m.start(1)), (i, m.end(1))
        if a.lines[i].strip() and not a.lines[i].lstrip().startswith("#"):
            return None
    return None


# --------------------------------------------------------------------------- #
# Fields of a node (the form in the side bar)
# --------------------------------------------------------------------------- #

#: Texts that can be written in several languages ({ru, en}).
TEXT_KEYS = {"title", "subtitle", "description", "comment"}
#: Fields written in hexadecimal.
HEX_KEYS = {"id", "pgn", "node_id", "address", "index", "subindex", "command", "destination"}


def node_kind(path: Path_) -> str | None:
    """Kind of a tree node from the shape of its path."""
    if len(path) == 2 and path[0] == "buses":
        return "bus"
    if len(path) >= 2 and isinstance(path[-1], int):
        return {"devices": "device", "frames": "frame", "signals": "signal", "flags": "flag",
                "sdo": "sdo"}.get(path[-2])
    return None


_RESERVED = re.compile(r"(?i)true|false|yes|no|on|off|null|~|[-+]?(0x[0-9a-f]+|[\d.]+(e[-+]?\d+)?)")


def yaml_text(value: str) -> str:
    """Text for people in the YAML: without quotes if YAML reads it as the same string (spaces and any
    letters are fine; commas and brackets are not, so the text also suits "{…}"), otherwise quoted."""
    plain = (value == value.strip() and value != "" and value[0] not in "-?:!&*|>'\"%@`"
             and not any(c in value for c in ",[]{}#\n\r\t") and ": " not in value and not value.endswith(":")
             and not _RESERVED.fullmatch(value))
    return value if plain else '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _insert_field(a: Analysis, map_path: Path_, key: str, text: str) -> list[Edit]:
    """Add a key to a mapping: in block style before the first nested list or mapping
    (``signals``, ``values``…), so that the field ends up next to the node's other fields."""
    n = a.nodes.get(map_path)
    raw = raw_at(a, map_path)
    if n is None or _is_flow(a, map_path) or not isinstance(raw, dict):
        return insert_key(a, map_path, key, text)
    for k, v in raw.items():
        kr = key_range(a, map_path + (k,)) if isinstance(v, (dict, list)) else None
        if kr and kr[0][0] > n.start[0]:
            pos = (kr[0][0], 0)
            return [Edit(pos, pos, f"{' ' * n.start[1]}{key}: {text}\n")]
    return insert_key(a, map_path, key, text)


def format_value(key: str, value) -> str:
    """Value of a form field → YAML text."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if key in HEX_KEYS and value >= 0:
            width = 2 if value <= 0xFF else 3 if value <= 0xFFF else 4 if value <= 0xFFFF else 8
            return f"0x{value:0{width}X}"
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return yaml_text(str(value)) if key in TEXT_KEYS or key == "unit" else yaml_scalar(str(value))


def frame_types(a: Analysis, path: Path_) -> list[dict]:
    """CANopen frame types for the form: {type, label, taken}. A frame of the bus (without a device's node_id)
    gets only the types whose ID does not depend on the node; ``taken`` names another frame of the bus with that CAN
    ID. The owner is read from the data together with the included files: the device can be in another file."""
    owner = raw_at_path(a.data, path[:4]) if len(path) >= 6 and path[2] == "devices" else None
    node_id = owner.get("node_id") if isinstance(owner, dict) else None
    used: dict[int, str] = {}
    if a.map is not None:
        bus, me = _find(a.map, path[:2]), _find(a.map, path)
        for f in bus.all_frames() if isinstance(bus, M.Bus) else []:
            if f is not me and f.can_id is not None:
                used.setdefault(f.can_id, f.name)
    out = [{"type": "", "label": "None (explicit ID)", "taken": None}]
    for fc in FUNCTION_CODES.values():
        if fc.per_node and owner is None:
            continue
        can_id = compute_id(fc.type, node_id if isinstance(node_id, int) else None)
        out.append({"type": fc.type, "label": fc.label_en, "taken": used.get(can_id) if can_id is not None else None})
    return out


def node_fields(a: Analysis, path: Path_) -> dict | None:
    """Data of a node for the form: kind, document language, the bus protocol, the frame's owner, the bus devices
    and the scalar fields (texts {ru, en} in the document language).

    A node of another file of the map is read from the data together with the included files, ``file`` is its
    file: the form's changes go there (``mapcan.lsp.set`` routes them). The bus devices also include those of the
    included files. In an included file opened on its own, every node has ``file``."""
    file = a.included_file(path) or a.own_file

    def at(p: Path_):
        return raw_at_path(a.data, p) if file else raw_at(a, p)

    raw = at(path)
    kind = node_kind(path)
    if kind is None or not isinstance(raw, dict):
        return None
    node = raw
    # Deprecated keys under their current names: the form knows only those (see upgrade.py)
    raw, _found = upgrade_node(U.node_kind(path), dict(raw), path)
    if kind == "sdo" and isinstance(raw.get("value"), dict):
        raw["value"] = upgrade_node("sdo_value", dict(raw["value"]))[0]
    # A map of format version 1: its encodings as version 2 has them
    if isinstance(a.data, dict) and a.data.get("mapcan") == 1:
        raw = U.upgrade_v1_node(U.node_kind(path), raw)
        if kind == "sdo" and isinstance(raw.get("value"), dict):
            raw["value"] = U.upgrade_v1_node("sdo_value", raw["value"])
    lang = doc_language(a)
    bus = raw_at_path(a.data, path[:2]) if path[:1] == ("buses",) else None
    bus = bus if isinstance(bus, dict) else {}
    values = {}
    for k, v in raw.items():
        if isinstance(v, dict) and k in TEXT_KEYS:
            values[k] = _txt(v, lang)
        elif isinstance(v, (str, int, float, bool)) or v is None:
            values[k] = v
        elif isinstance(v, list) and all(isinstance(x, (str, int)) for x in v):
            values[k] = list(v)
        elif isinstance(v, dict) and k == "invalid_raw":
            values[k] = {m: list(x) if isinstance(x, list) else x for m, x in v.items()}   # by meaning, read-only
        elif not isinstance(v, (dict, list)):
            values[k] = str(v)
    # The value of an SDO exchange is a nested mapping: its fields go to the form under the keys "value.<field>"
    if kind == "sdo" and isinstance(raw.get("value"), dict):
        for k, v in raw["value"].items():
            if isinstance(v, dict) and k in TEXT_KEYS:
                values[f"value.{k}"] = _txt(v, lang)
            elif isinstance(v, (str, int, float, bool)):
                values[f"value.{k}"] = v
    owner = at(path[:4]) if len(path) >= 6 and path[2] == "devices" else None
    devices = [(d.get("name"), _txt(d.get("short"), lang) or _txt(d.get("title"), lang) or d.get("name"))
               for d in bus.get("devices") or [] if isinstance(d, dict) and isinstance(d.get("name"), str)]
    # Signal from the parsed map: its length in bits is computed from byte_length and encoding
    signal = _find(a.map, path) if a.map is not None and kind == "signal" else None
    # Whether another signal of the frame is the multiplexer selector (then the signal can have mux)
    siblings = at(path[:-1]) if kind == "signal" else None
    has_selector = any(isinstance(s, dict) and s.get("multiplexer") and s is not node for s in siblings or [])
    return {"kind": kind, "path": list(path), "file": file, "lang": lang,
            "protocol": bus.get("protocol") or "canopen",
            # CAN FD bus and its BRS default: the frame's BRS field shows the inherited value
            "fd": bus.get("fd") is True, "busBrs": bus.get("brs") if isinstance(bus.get("brs"), bool) else None,
            "owner": owner.get("name") if isinstance(owner, dict) else None,
            "signalEncoding": signal.encoding if isinstance(signal, M.Signal) else values.get("encoding"),
            "bitLength": signal.bit_length if isinstance(signal, M.Signal) else None,
            "hasSelector": has_selector,
            # With a revision history the document's version and date come from its latest entry
            "hasHistory": kind == "document" and bool(raw.get("history")),
            "devices": [{"name": n, "label": str(lbl)} for n, lbl in devices], "values": values,
            "frameTypes": frame_types(a, path) if kind == "frame" else [],
            # Units reference (ru, en) for the suggestions of the Unit field; any other text is allowed too
            "units": [list(u) for u in UNITS] if kind == "signal" else [],
            **_layout_fields(a, path, kind, raw, lang)}


def _layout_fields(a: Analysis, path: Path_, kind: str, raw: dict, lang: str) -> dict:
    """Layout of the node's frame (frame, signal, flag, SDO exchange) as in the web editor, the value table
    and the flags of a signal. A table entry's value is as in the YAML (``raw``), so the form can extend it."""
    from ..docmodel import PALETTE
    from ..web.session import frame_view

    out: dict = {"frame": None, "palette": PALETTE, "valueTable": None, "valueTableRef": None, "flags": None}
    frame_path = next((path[:i + 1] for i in range(len(path) - 1, 0, -1)
                       if path[i - 1] == "frames" and isinstance(path[i], int)), None)
    frame = _find(a.map, frame_path) if a.map is not None and frame_path else None
    if isinstance(frame, M.Frame):
        out["frame"] = frame_view(frame)
    if kind not in ("signal", "flag"):
        return out
    values = raw.get("values")
    if isinstance(values, str):
        out["valueTableRef"] = values          # a named table from value_tables
    if isinstance(values, dict):
        rows = []
        for k, v in values.items():
            entry = v if isinstance(v, dict) else {}
            rows.append({"key": str(k), "value": k if isinstance(k, int) else None,
                         "name": str(entry.get("name") or "") if entry else ("" if v is None else str(v)),
                         "description": _txt(entry.get("description"), lang), "raw": v})
        out["valueTable"] = sorted(rows, key=lambda r: (r["value"] is None, r["value"] or 0, r["key"]))
    if kind == "signal" and isinstance(raw.get("flags"), list):
        out["flags"] = [{"bit": f.get("bit"), "bit_length": f.get("bit_length"), "name": f.get("name"),
                         "description": _txt(f.get("description"), lang), "raw": f}
                        if isinstance(f, dict) else {"bit": None, "bit_length": None, "name": None,
                                                     "description": "", "raw": f}
                        for f in raw["flags"]]
    return out


def apply_ops(a: Analysis, ops: list[dict]) -> str:
    """Text of the map after operations of the web editor (:mod:`mapcan.web.yamlops`): set, remove, insert,
    move, rename_key, set_layout. Untouched lines stay as they were. An operation error raises
    :class:`mapcan.web.yamlops.OpError`."""
    from ..web import yamlops as Y

    Y.check_editable(a.result.source, ops)
    y = Y.make_yaml(a.text)
    doc = y.load(a.text)
    if doc is None:
        raise Y.OpError(_("the YAML has a syntax error"))
    canon_old = Y.dump(y, doc)
    Y.apply_ops(doc, ops)
    return Y.merge_text(a.text, canon_old, Y.dump(y, doc))


Reader = Callable[[str], "str | None"]


def routed_ops(a: Analysis, ops: list[dict], read: Reader) -> tuple[str, dict[str, str]]:
    """Operations of the web editor (paths of the map) applied to the files they change, as the web editor does:
    (new text of this document, {resolved path of another file: its new text}). A node of an included file has
    its own path there (the loader's path mapping)."""
    from ..web import yamlops as Y

    src = a.result.source
    own = a.own_file or src.file
    groups: dict[str | None, list[dict]] = {}
    for o in ops:
        path = o.get("path")
        if not isinstance(path, list):
            raise Y.OpError(_("path must be a list"))
        file, local = src.origin(tuple(int(x) if isinstance(x, str) and x.isdigit() else x for x in path))
        key = None if file == own else str(Path(file).resolve())
        groups.setdefault(key, []).append({**o, "path": list(local)})

    def run(text: str, group: list[dict]) -> str:
        y = Y.make_yaml(text)
        doc = y.load(text)
        if doc is None:
            raise Y.OpError(_("the YAML has a syntax error"))
        canon_old = Y.dump(y, doc)
        Y.apply_ops(doc, group)
        return Y.merge_text(text, canon_old, Y.dump(y, doc))

    others = {}
    for key, group in groups.items():
        if key is None:
            continue
        text = read(key)
        if text is None:
            raise Y.OpError(_("the included file {file} cannot be read", file=Path(key).name))
        others[key] = run(text, group)
    return (run(a.text, groups[None]) if None in groups else a.text), others


def field_ops(a: Analysis, path: Path_, value) -> list[dict]:
    """A field written by the form as operations of the web editor: for a node of another file of the map
    (:func:`routed_ops` sends them there). A text in several languages changes in the document language, and a
    renamed device takes the references to it on its bus along, in every file."""
    key = path[-1]
    current = raw_at_path(a.data, path)
    if value is None or value == "":
        if isinstance(current, dict) and key in TEXT_KEYS:
            return [{"op": "set", "path": [*path, doc_language(a)], "value": None}]
        return [{"op": "set", "path": list(path), "value": None}]
    if isinstance(current, dict) and key in TEXT_KEYS and isinstance(value, str):
        return [{"op": "set", "path": [*path, doc_language(a)], "value": value}]
    ops = [{"op": "set", "path": list(path), "value": value}]
    if key == "name" and node_kind(path[:-1]) == "device" and isinstance(current, str) and value != current:
        bus = raw_at_path(a.data, path[:2])
        for fp, f in _bus_frames_of(bus, list(path[:2])):
            if f.get("sender") == current:
                ops.append({"op": "set", "path": [*fp, "sender"], "value": value})
            rec = f.get("receivers")
            if isinstance(rec, list) and current in rec:
                ops.append({"op": "set", "path": [*fp, "receivers"],
                            "value": [value if r == current else r for r in rec]})
    return ops


def _bus_frames_of(bus, bp: list) -> list[tuple[list, dict]]:
    if not isinstance(bus, dict):
        return []
    out = [([*bp, "frames", i], f) for i, f in enumerate(bus.get("frames") or [])]
    for di, d in enumerate(bus.get("devices") or []):
        if isinstance(d, dict):
            out += [([*bp, "devices", di, "frames", i], f) for i, f in enumerate(d.get("frames") or [])]
    return [(p, f) for p, f in out if isinstance(f, dict)]


def in_other_file(a: Analysis, path: Path_) -> bool:
    """The node is written in another file than this text, or this text is a file included by the map: its
    edits go through :func:`field_ops` and :func:`routed_ops`."""
    return bool(a.own_file) or a.result.source.is_included(path)


def set_field(a: Analysis, path: Path_, value) -> list[Edit]:
    """Write a field of a node (``path`` is the field's path): a new value, or ``None`` or "" to remove the key.

    A name is renamed together with the references to it; a text written in several languages
    changes only in the document language.
    """
    if not path or not isinstance(path[-1], str) or a.result.source.is_included(path):
        return []
    key = path[-1]
    if any(isinstance(node := raw_at(a, path[:i]), dict)
           and any(k in node for k in U.deprecated_of(U.node_kind(path[:i]), path[i]))
           for i in U.renamed_along(path)):
        # The node has the field under a former name: yamlops renames it in place (keeping its position)
        op = ({"op": "remove", "path": list(path)} if value is None or value == ""
              else {"op": "set", "path": list(path), "value": value})
        return [minimal_edit(a.text, apply_ops(a, [op]))]
    if key == "canopen" and node_kind(path[:-1]) == "frame":
        return _set_frame_type(a, path, value)
    if key == "sender" and node_kind(path[:-1]) == "frame":
        return _set_sender(a, path, value)
    if not isinstance(raw_at(a, path[:-1]), dict):
        # A field of a nested mapping that does not exist yet (value.name of an SDO): the mapping is added with it
        parent = path[:-1]
        if (value is None or value == "" or len(parent) < 2 or not isinstance(parent[-1], str)
                or raw_at(a, parent) is not None or not isinstance(raw_at(a, parent[:-1]), dict)):
            return []
        # encoding is required for an SDO value: the new mapping gets encoding: number right away
        extra = ", encoding: number, bit_length: 32" if parent[-1] == "value" and key == "name" else ""
        return _insert_field(a, parent[:-1], parent[-1], f"{{{key}: {format_value(key, value)}{extra}}}")
    current = raw_at(a, path)
    if value is None or value == "":
        if current is None or path not in a.nodes:
            return []
        if isinstance(current, dict) and key in TEXT_KEYS:
            lang = doc_language(a)
            return delete_key(a, path + (lang,)) if lang in current else []
        # Without an identifier an SDO exchange has no value: the value mapping is removed as a whole
        if key == "name" and len(path) >= 2 and path[-2] == "value" and node_kind(path[:-2]) == "sdo":
            return delete_key(a, path[:-1])
        # The last field of a nested mapping "key: {field: …}" is removed together with it rather than leaving "{}"
        parent, pn = path[:-1], a.nodes.get(path[:-1])
        if (len(parent) >= 2 and isinstance(parent[-1], str) and list(raw_at(a, parent)) == [key]
                and pn is not None and _is_flow(a, parent) and (close := a._closing(pn.start))
                and close[0] == pn.start[0]):
            return delete_key(a, parent)
        return delete_key(a, path)
    if key == "name" and current is not None:
        return rename_edits(a, path, str(value)) if value != current else []
    if isinstance(current, dict) and key in TEXT_KEYS:
        lang = doc_language(a)
        return set_value(a, path + (lang,), yaml_text(str(value))) if current.get(lang) != value else []
    if isinstance(value, list):
        text = "[" + ", ".join(format_value(key, v) for v in value) + "]"
        if isinstance(current, list):
            n = a.nodes.get(path)
            if n is None:
                return []
            if not _is_flow(a, path):
                # A block list is replaced with "[…]" after the key
                kr, block = key_range(a, path), a.block(path)
                return [Edit(kr[1], block[1], f": {text}")] if kr and block else []
            close = a._closing(n.start)
            return [Edit(n.start, close, text)] if close else []
        return _insert_field(a, path[:-1], key, text)
    if isinstance(current, (dict, list)) or current == value and type(current) is type(value):
        return []
    if path not in a.nodes:
        return _insert_field(a, path[:-1], key, format_value(key, value))
    return set_value(a, path, format_value(key, value))


def _set_frame_type(a: Analysis, path: Path_, value) -> list[Edit]:
    """CANopen frame type; a written length not allowed for the new type is removed, so the type's length is used."""
    edits = _set_plain(a, path, value)
    allowed = CANOPEN_DLC.get(str(value or ""))
    for key in ("length",) + U.deprecated_of("frame", "length"):
        length = raw_at(a, path[:-1] + (key,))
        if edits and allowed and isinstance(length, int) and length not in allowed:
            edits += delete_key(a, path[:-1] + (key,))
    return edits


def _set_sender(a: Analysis, path: Path_, value) -> list[Edit]:
    """The sender of a frame; a device named as the sender does not receive the frame, so it leaves the receivers."""
    receivers = raw_at(a, path[:-1] + ("receivers",))
    if not value or not isinstance(receivers, list) or value not in receivers:
        return _set_plain(a, path, value)
    rest = [r for r in receivers if r != value]
    ops = [{"op": "set", "path": list(path), "value": value},
           {"op": "set", "path": list(path[:-1] + ("receivers",)), "value": rest} if rest
           else {"op": "remove", "path": list(path[:-1] + ("receivers",))}]
    return [minimal_edit(a.text, apply_ops(a, ops))]


def _set_plain(a: Analysis, path: Path_, value) -> list[Edit]:
    """A scalar field without special rules: a new value, or ``None`` or "" to remove the key."""
    current = raw_at(a, path)
    if value is None or value == "":
        return delete_key(a, path) if current is not None and path in a.nodes else []
    if current == value:
        return []
    if path not in a.nodes:
        return _insert_field(a, path[:-1], path[-1], format_value(path[-1], value))
    return set_value(a, path, format_value(path[-1], value))


def minimal_edit(old: str, new: str) -> Edit:
    """One edit that replaces the differing lines ``old`` with the lines ``new``."""
    a, b = old.splitlines(keepends=True), new.splitlines(keepends=True)
    p = 0
    while p < min(len(a), len(b)) and a[p] == b[p]:
        p += 1
    s = 0
    while s < min(len(a), len(b)) - p and a[-1 - s] == b[-1 - s]:
        s += 1
    return Edit((p, 0), (len(a) - s, 0), "".join(b[p:len(b) - s]))
