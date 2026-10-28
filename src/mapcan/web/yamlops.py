"""Editing a YAML document with operations on paths, keeping comments and formatting.

The document is kept as a ruamel round-trip tree. Operations change only the nodes
they address. On serialization the changes are carried over to the *source* text line by line
(:func:`merge_text`), so untouched parts, including manual line breaks
in flow mappings, stay byte for byte the same.
"""

from __future__ import annotations

import datetime as _dt
import difflib
import io
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarint import HexCapsInt, HexInt
from ruamel.yaml.util import load_yaml_guess_indent

from ..i18n import _
from ..model import FORMAT_VERSION, Signal
from ..upgrade import DROP, V1_KINDS, node_kind, renamed_along, renames, upgrade_tree, v1_encoding

# Keys whose numbers are usually written in hex.
HEX_KEYS = {"id", "node_id", "address", "pgn", "destination", "command", "index", "subindex",
            "invalid_raw", "not_available", "error"}
LAYOUT_KEYS = ("start_bit", "bit_length", "byte", "bit", "byte_length")
FLOW_LISTS = {"include"}     # a new list of these keys is written "[…]" on one line, as in the docs
MAX_FRAME_BITS = 64 * 8     # a CAN FD frame is up to 64 bytes


class OpError(ValueError):
    """The operation cannot be applied (wrong path, type etc.)."""


# --------------------------------------------------------------------------- YAML I/O


def make_yaml(text: str = "") -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    ind, bsi = 4, 2
    if text.strip():
        try:
            _, ind, bsi = load_yaml_guess_indent(text)
        except Exception:  # noqa: BLE001 — keep the default indents
            pass
    if bsi is None:
        # The text has no lists: ind is the mapping indent; lists in the usual style "  - "
        mapping = ind or 2
        y.indent(mapping=mapping, sequence=mapping + 2, offset=mapping)
    else:
        # bsi is the indent of "-" (0: lists without an indent), ind the indent of an item's content
        y.indent(mapping=bsi or ind or 2, sequence=ind or 4, offset=bsi)
    return y


def dump(y: YAML, doc) -> str:
    buf = io.StringIO()
    y.dump(doc, buf)
    return buf.getvalue()


def merge_text(orig: str, canon_old: str, canon_new: str) -> str:
    """Carry the changes canon_old → canon_new over to the source text ``orig``.

    ``canon_old`` is the serialization of the document before the edit (it can differ from ``orig``
    in line breaks). Parts of ``orig`` that match unchanged lines are
    copied as is; changed ones are taken from ``canon_new``.
    """
    if canon_old == canon_new:
        return orig
    o = orig.splitlines(keepends=True)
    a = canon_old.splitlines(keepends=True)
    b = canon_new.splitlines(keepends=True)

    # 1. Atoms: groups of lines of canon_old with the matching lines of orig.
    atom_of = [0] * len(a)          # index of the atom of a canon_old line
    atoms: list[tuple[int, int, list[str]]] = []   # (first line of a, number of lines of a, lines of orig)
    pending: list[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, o, a, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                atoms.append((j1 + k, 1, pending + [o[i1 + k]]))
                pending = []
                atom_of[j1 + k] = len(atoms) - 1
        elif tag == "delete":
            pending += o[i1:i2]      # lines only in orig: attach them to the next atom
        else:  # replace / insert
            atoms.append((j1, j2 - j1, pending + o[i1:i2]))
            pending = []
            for k in range(j1, j2):
                atom_of[k] = len(atoms) - 1

    # 2. Which lines of canon_old stayed unchanged and where they went.
    new_of = [-1] * len(a)
    for tag, i1, i2, j1, _j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                new_of[i1 + k] = j1 + k

    def clean(idx: int) -> bool:
        start, n, _ = atoms[idx]
        first = new_of[start]
        return first >= 0 and all(new_of[start + k] == first + k for k in range(n))

    old_at = {j: i for i, j in enumerate(new_of) if j >= 0}
    out: list[str] = []
    fresh: list[bool] = []            # the line is taken from canon_new (new/changed)
    j = 0
    while j < len(b):
        i = old_at.get(j)
        if i is not None:
            idx = atom_of[i]
            start, n, orig_lines = atoms[idx]
            if i == start and clean(idx):
                out += orig_lines
                fresh += [False] * len(orig_lines)
                j += n
                continue
        out.append(b[j])
        fresh.append(True)
        j += 1
    out += pending
    fresh += [False] * len(pending)
    return "".join(_squeeze_blanks(_blank_before_insert(out, fresh), o))


def _squeeze_blanks(lines: list[str], orig: list[str]) -> list[str]:
    """A removed block leaves the empty lines on both sides of it: a text without two empty lines in a row keeps
    none."""
    blank = [not ln.strip() for ln in orig]
    if any(a and b for a, b in zip(blank, blank[1:], strict=False)):
        return lines
    return [ln for i, ln in enumerate(lines) if ln.strip() or i == 0 or lines[i - 1].strip()]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _blank_before_insert(lines: list[str], fresh: list[bool]) -> list[str]:
    """ruamel attributes empty separator lines to the end of the previous list item
    (or the last key of a mapping), so an item inserted at the end ends up
    *after* the separator. Move the separator after the inserted block if it starts
    with "- " or is a key appended to the end of a nested mapping. A top-level key
    inserted between top-level keys separated by empty lines gets one on both sides."""
    out = list(lines)
    i = 0
    while i < len(out):
        if fresh[i] and out[i].strip() and i > 0 and not out[i - 1].strip() and not fresh[i - 1]:
            j = i
            while j < len(out) and fresh[j] and out[j].strip():
                j += 1
            item = out[i].lstrip().startswith("- ")
            tail = j < len(out) and _indent(out[j]) < _indent(out[i])
            if j < len(out) and out[j].strip() and (item or tail):
                k = i
                while k > 0 and not out[k - 1].strip() and not fresh[k - 1]:
                    k -= 1
                blanks = out[k:i]
                out[k:j] = out[i:j] + blanks
                fresh[k:j] = fresh[i:j] + [False] * len(blanks)
                i = j
                continue
        i += 1
    return _separate_top_keys(out, fresh)


def _separate_top_keys(out: list[str], fresh: list[bool]) -> list[str]:
    """A new top-level key with an empty line on one side only (the other keys of the map are separated by empty
    lines) gets one on the other side too."""
    i = 1
    while i < len(out):
        if not (fresh[i] and out[i].strip() and _indent(out[i]) == 0 and not fresh[i - 1]):
            i += 1
            continue
        j = i + 1
        while j < len(out) and fresh[j] and out[j].strip():
            j += 1
        before = not out[i - 1].strip()
        after = j < len(out) and not out[j].strip()
        if before and not after and j < len(out) and _indent(out[j]) == 0:
            out.insert(j, out[i - 1])
            fresh.insert(j, False)
        elif after and not before and j + 1 < len(out) and out[j + 1].strip() and _indent(out[j + 1]) == 0:
            out.insert(i, out[j])
            fresh.insert(i, False)
            j += 1
        i = j + 1
    return out


# --------------------------------------------------------------------------- values


def _key(k: Any) -> Any:
    """Keys of value tables come from JSON as strings."""
    if isinstance(k, str):
        s = k.strip()
        try:
            return int(s, 16) if s.lower().startswith(("0x", "-0x")) else int(s)
        except ValueError:
            return k
    return k


def to_node(value: Any, key: Any = None, old: Any = None) -> Any:
    """JSON value → ruamel node."""
    if isinstance(value, dict):
        m = CommentedMap()
        for k, v in value.items():
            kk = _key(k) if key in ("values",) else k
            m[kk] = to_node(v, k)
        if isinstance(old, CommentedMap) and old.fa.flow_style():
            m.fa.set_flow_style()           # a replaced "{…}" stays on its line
        return m
    if isinstance(value, list):
        s = CommentedSeq()
        for v in value:
            s.append(to_node(v, key))
        if (isinstance(old, CommentedSeq) and old.fa.flow_style()) or (old is None and key in FLOW_LISTS):
            s.fa.set_flow_style()           # receivers: [a, b] stays a "[…]" list
        return s
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        if isinstance(old, (HexInt, HexCapsInt)) and value >= 0:
            cls = type(old)                                 # keep the case and the width of the notation
            return cls(value, width=getattr(old, "_width", None))
        if key in HEX_KEYS and value >= 0:
            return HexCapsInt(value, width=4 if key == "pgn" else (2 if value <= 0xFF else None))
        return value
    if isinstance(value, float) and value.is_integer() and isinstance(old, int) and not isinstance(old, bool):
        return int(value)
    if key == "date" and isinstance(value, str):
        try:
            return _dt.date.fromisoformat(value)
        except ValueError:
            return value
    return value


def plain(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [plain(v) for v in node]
    if isinstance(node, bool):
        return bool(node)
    if isinstance(node, int):
        return int(node)
    if isinstance(node, float):
        return float(node)
    return node


# --------------------------------------------------------------------------- navigation


def _get(doc, path: list) -> Any:
    node = doc
    for el in path:
        try:
            if isinstance(node, list):
                node = node[int(el)]
            elif isinstance(node, dict):
                node = node[_find_key(node, el)]
            else:
                raise KeyError(el)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise OpError(_("path not found: {path}", path=path)) from e
    return node


def _find_key(m: dict, key: Any) -> Any:
    if key in m:
        return key
    k2 = _key(key)
    if k2 in m:
        return k2
    raise KeyError(key)


def _parent(doc, path: list) -> tuple[Any, Any]:
    if not path:
        raise OpError(_("empty path"))
    return _get(doc, path[:-1]), path[-1]


# --------------------------------------------------------------------------- operations


def _ensure_parent(doc, path: list) -> None:
    """Create the missing intermediate mappings (e.g. ``value`` of an SDO exchange)."""
    node = doc
    for el in path[:-1]:
        if isinstance(node, dict) and el not in node and _key(el) not in node:
            node[el] = CommentedMap()
        node = node[int(el)] if isinstance(node, list) else node[_find_key(node, el)]


# --------------------------------------------------------------------------- deprecated keys


def _kind(path: list) -> str | None:
    return node_kind(_kind_path(path))


def upgrade_map(m: Any, kind: str | None, only: str | None = None) -> bool:
    """Replace the deprecated keys of the mapping ``m`` with the current ones in place (see upgrade.py): the
    current key takes the position and the comment of the old one. ``only``: just the keys that this current key
    replaces. Whether anything changed."""
    if not isinstance(m, CommentedMap):
        return False
    changed = False
    for r in renames(kind):
        if only is not None and r.new != only:
            continue
        present = r.present(m)
        if not present or (r.nest and r.new in m):
            continue        # keys to move next to the mapping already written: left for the author (an error)
        changed = True
        if r.nest:
            _nest_keys(m, present, r.new)
            continue
        value = DROP if r.new in m else r.value({k: plain(m[k]) for k in present})
        if value is not DROP:
            pos = list(m.keys()).index(present[0])
            comment = m.ca.items.pop(present[0], None)
            m.insert(pos, r.new, to_node(value, r.new, m[present[0]]))
            if comment is not None:
                m.ca.items[r.new] = comment
        for k in present:
            if k in m:
                keys = list(m.keys())
                before = keys[keys.index(k) - 1] if keys.index(k) > 0 else None
                comment = m.ca.items.pop(k, None)
                del m[k]
                # The comment after a removed key (and the comment lines below it) goes to the key before it
                if comment is not None and before is not None and before not in m.ca.items:
                    m.ca.items[before] = comment
    return changed


def _nest_keys(m: CommentedMap, keys: list[str], new: str) -> None:
    """Move the keys of ``m`` with their nodes and comments into a mapping ``new`` at the place of the first one."""
    inner = CommentedMap()
    if m.fa.flow_style():
        inner.fa.set_flow_style()
    for k in keys:
        inner[k] = m[k]
        if k in m.ca.items:
            inner.ca.items[k] = m.ca.items.pop(k)
    pos = list(m.keys()).index(keys[0])
    for k in keys:
        del m[k]
    m.insert(pos, new, inner)


def migrate_doc(doc) -> int:
    """Rewrite every deprecated key of a map document; the number of nodes changed."""
    count = 0

    def walk(node, path):
        nonlocal count
        if isinstance(node, dict):
            count += upgrade_map(node, _kind(path))
            for k in list(node.keys()):
                walk(node[k], path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [i])

    walk(doc, [])
    return count


def migrate_text(text: str) -> str:
    """The map's text with every deprecated key rewritten, the frames' deprecated direction removed
    (migrate_directions) and a map of format version 1 rewritten in version 2 (migrate_format); the rest of the
    text stays as it was."""
    return migrate_format_text(migrate_version_text(migrate_directions_text(migrate_renames_text(text))))


# The schema of each format version (schema.py), as written in the first line of a map
_SCHEMA_V1 = re.compile(r"^(# yaml-language-server: \$schema=\S*?)(part-)?v1\.json\s*$", re.M)


def migrate_format_text(text: str) -> str:
    """The text of a map (or of a file it includes) of format version 1 in version 2 (migrate_format); other text
    as it is."""
    y = make_yaml(text)
    doc = y.load(text)
    if not isinstance(doc, dict) or doc.get("mapcan") != 1:
        return text
    canon_old = dump(y, doc)
    migrate_format(doc)
    return _SCHEMA_V1.sub(lambda m: f"{m.group(1)}{m.group(2) or ''}v{FORMAT_VERSION}.json",
                          merge_text(text, canon_old, dump(y, doc)))


def migrate_format(doc) -> bool:
    """A map document of format version 1 in version 2 (upgrade.v1_encoding): the encodings of its signals and SDO
    values, with the keys that keep their meaning added after them. True if it was version 1."""
    if doc.get("mapcan") != 1:
        return False

    def walk(node, path):
        if isinstance(node, dict):
            change = v1_encoding(node) if node_kind(_kind_path(path)) in V1_KINDS else None
            if change is not None and isinstance(node, CommentedMap):
                new, add = change
                node["encoding"] = new
                pos = list(node.keys()).index("encoding")
                for i, (k, v) in enumerate(add.items()):
                    node.insert(pos + 1 + i, k, v)
            for k in list(node.keys()):
                walk(node[k], path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [i])

    walk(doc, [])
    doc["mapcan"] = FORMAT_VERSION
    return True


def migrate_renames_text(text: str) -> str:
    """The map's text with every deprecated key rewritten. Keys are renamed in the text itself, so flow mappings
    keep their line breaks; if a change cannot be made that way (or the result reads differently), the document is
    rewritten through ruamel instead."""
    y = make_yaml(text)
    doc = y.load(text)
    if doc is None:
        return text
    edits = _migration_edits(doc, text.splitlines(keepends=True))
    if not edits and edits is not _UNSUPPORTED:
        return text
    if edits is not _UNSUPPORTED:
        new = _apply_text_edits(text, edits)
        try:
            if _upgraded_data(new) == _upgraded_data(text):
                return new
        except Exception:  # noqa: BLE001 — the text edit broke the YAML: fall back
            pass
    canon_old = dump(y, doc)
    migrate_doc(doc)
    return merge_text(text, canon_old, dump(y, doc))


def migrate_version_text(text: str) -> str:
    """The map's text without the document's version and date that repeat the revision history
    (migrate_version)."""
    y = make_yaml(text)
    doc = y.load(text)
    if not isinstance(doc, dict):
        return text
    canon_old = dump(y, doc)
    if not migrate_version(doc):
        return text
    return merge_text(text, canon_old, dump(y, doc))


def migrate_version(doc) -> bool:
    """document.version and document.date out of a map document where they are those of the latest revision
    history entry (they follow from it); True if something changed. A different value is left for the author
    (the warning history-version)."""
    document = doc.get("document")
    history = document.get("history") if isinstance(document, dict) else None
    if not isinstance(history, list) or not history or not isinstance(history[0], dict):
        return False
    changed = False
    for key in ("version", "date"):
        if key in document and history[0].get(key) is not None and str(document[key]) == str(history[0][key]):
            del document[key]
            changed = True
    return changed


def migrate_directions_text(text: str) -> str:
    """The map's text without the deprecated direction of frames (migrate_directions)."""
    y = make_yaml(text)
    doc = y.load(text)
    if not isinstance(doc, dict):
        return text
    canon_old = dump(y, doc)
    if not migrate_directions(doc):
        return text
    return merge_text(text, canon_old, dump(y, doc))


def migrate_directions(doc) -> bool:
    """The deprecated direction of frames out of a map document; True if something changed.

    Where it follows from the CANopen function and the sender (resolve.derived_direction) it is removed, as on a
    frame of the bus, where it means nothing. An RX frame of a device without a sender is a frame from outside the
    map: it moves to the frames of its bus, with the device in its receivers, which reads the same. A direction
    that contradicts the function or the sender is left for the author (the warning direction-deprecated)."""
    from ..canopen import default_direction
    from ..resolve import derived_direction

    changed = False
    for bus in doc.get("buses") or []:
        if not isinstance(bus, dict):
            continue
        for frame in bus.get("frames") or []:
            if isinstance(frame, dict) and "direction" in frame:
                _drop_key(frame, "direction")
                changed = True
        for dev in bus.get("devices") or []:
            frames = dev.get("frames") if isinstance(dev, dict) else None
            if not isinstance(frames, list):
                continue
            owner = dev.get("name")
            for i in reversed(range(len(frames))):
                frame = frames[i]
                if not isinstance(frame, dict) or "direction" not in frame:
                    continue
                direction, sender, kind = frame["direction"], frame.get("sender"), frame.get("canopen") or "raw"
                if direction == derived_direction(kind, sender, owner):
                    _drop_key(frame, "direction")
                elif direction == "rx" and sender is None and default_direction(kind) is None and owner:
                    _drop_key(frame, "direction")
                    receivers = frame.get("receivers")
                    if not isinstance(receivers, list):
                        receivers = CommentedSeq()
                        receivers.fa.set_flow_style()
                        frame["receivers"] = receivers
                    if owner not in receivers:
                        receivers.append(owner)
                    del frames[i]
                    _frames_of_bus(bus).append(frame)
                else:
                    continue
                changed = True
    return changed


def _frames_of_bus(bus: CommentedMap) -> CommentedSeq:
    """The frames of a bus, the list put before its devices if it has none."""
    frames = bus.get("frames")
    if not isinstance(frames, list):
        frames = CommentedSeq()
        keys = list(bus.keys())
        bus.insert(keys.index("devices") if "devices" in keys else len(keys), "frames", frames)
    return frames


def _drop_key(m: CommentedMap, key: str) -> None:
    """Remove a key; the comment after it (and the comment lines below it) goes to the key before it."""
    keys = list(m.keys())
    before = keys[keys.index(key) - 1] if keys.index(key) > 0 else None
    comment = m.ca.items.pop(key, None)
    del m[key]
    if comment is not None and before is not None and before not in m.ca.items:
        m.ca.items[before] = comment


_UNSUPPORTED: list = []
_SCALAR_END = re.compile(r"""^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^,\]}#\n]*?)\s*(?=[,\]}]|\s#|\s*$)""")


def _upgraded_data(text: str) -> Any:
    return upgrade_tree(plain(make_yaml(text).load(text)))


def _migration_edits(doc, lines: list[str]) -> list:
    """Text edits (line, col, end_line, end_col, new text) that rename the deprecated keys of the document."""
    edits: list = []

    def scalar_end(line: int, col: int) -> int | None:
        m = _SCALAR_END.match(lines[line][col:]) if line < len(lines) else None
        return col + len(m.group(1)) if m else None

    def remove(m: CommentedMap, key: str) -> bool:
        kl, kc = m.lc.key(key)
        vl, vc = m.lc.value(key)
        end = scalar_end(vl, vc) if vl == kl else None
        if end is None:
            return False
        line = lines[kl]
        if m.fa.flow_style():
            after = re.match(r"\s*,\s*", line[end:])
            if after:
                edits.append((kl, kc, kl, end + after.end(), ""))
                return True
            before = re.search(r",\s*$", line[:kc])
            if not before:
                return False
            edits.append((kl, before.start(), kl, end, ""))
            return True
        if line[:kc].strip():
            return False        # "- key: …" or another key before it on the line
        edits.append((kl, 0, kl + 1, 0, ""))
        return True

    def nest(node: CommentedMap, keys: list[str], new: str) -> bool:
        """Move block-style keys into a mapping ``new`` written at the place of the first one, one level deeper."""
        if node.fa.flow_style():
            return False
        kcol = node.lc.key(keys[0])[1]
        if any(lines[node.lc.key(k)[0]][:kcol].strip() for k in keys):
            return False        # "- key: …": the key shares its line with the sequence dash

        def indent(ln: str) -> int:
            return len(ln) - len(ln.lstrip())

        def loose(ln: str) -> bool:     # a blank line or a comment line at the level of the keys or above
            return not ln.strip() or (ln.lstrip().startswith("#") and indent(ln) <= kcol)

        # Lines of a key: from the comment lines just above it to the next line at its level or above
        starts, ends = {}, {}
        for k in keys:
            line = node.lc.key(k)[0]
            start = line
            while start > 0 and lines[start - 1].strip().startswith("#") and indent(lines[start - 1]) == kcol:
                start -= 1
            end = line + 1
            while end < len(lines) and (not lines[end].strip() or lines[end].lstrip().startswith("#")
                                        or indent(lines[end]) > kcol):
                end += 1
            while end > line + 1 and loose(lines[end - 1]):
                end -= 1        # blank lines and comments of what follows stay in place
            starts[k], ends[k] = start, end
        step = " " * max(2, kcol - parent_col.get(id(node), 0))
        moved = [" " * kcol + new + ":\n"]
        for k in keys:
            moved += [step + ln if ln.strip() else ln for ln in lines[starts[k]:ends[k]]]
            edits.append((starts[k], 0, ends[k], 0, ""))
        first = keys[0]
        edits.append((starts[first], 0, starts[first], 0, "".join(moved)))
        return True

    parent_col: dict[int, int] = {}

    def walk(node, path) -> bool:
        if isinstance(node, CommentedMap):
            kind = _kind(path)
            for k in node:
                if isinstance(node[k], CommentedMap):
                    parent_col[id(node[k])] = node.lc.key(k)[1]
            for r in renames(kind):
                present = r.present(node)
                if not present:
                    continue
                if r.nest:
                    if r.new in node:
                        continue        # see upgrade_map
                    if not nest(node, present, r.new):
                        return False
                    continue
                value = DROP if r.new in node else r.value({k: plain(node[k]) for k in present})
                first = present[0]
                if value is DROP:
                    drop = present
                else:
                    kl, kc = node.lc.key(first)
                    edits.append((kl, kc, kl, kc + len(first), r.new))
                    if value != plain(node[first]):
                        vl, vc = node.lc.value(first)
                        end = scalar_end(vl, vc)
                        if end is None:
                            return False
                        edits.append((vl, vc, vl, end, _yaml_scalar_text(value)))
                    drop = present[1:]
                for k in drop:
                    if not remove(node, k):
                        return False
            items = [(k, node[k]) for k in node]
        elif isinstance(node, CommentedSeq):
            items = list(enumerate(node))
        else:
            return True
        return all(walk(v, path + [k]) for k, v in items)

    if not walk(doc, []):
        return _UNSUPPORTED
    return edits


def _yaml_scalar_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _apply_text_edits(text: str, edits: list) -> str:
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    def offset(line: int, col: int) -> int:
        return starts[line] + col if line < len(lines) else len(text)

    for l1, c1, l2, c2, new in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        text = text[:offset(l1, c1)] + new + text[offset(l2, c2):]
    return text


def op_set(doc, path: list, value: Any) -> None:
    """Set a value. ``None`` removes the key of a mapping."""
    _upgrade_parent(doc, path)
    if value is not None and value != "":
        try:
            _ensure_parent(doc, path)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise OpError(_("path not found: {path}", path=path)) from e
    parent, last = _parent(doc, path)
    if isinstance(parent, list):
        idx = int(last)
        if not 0 <= idx < len(parent):
            raise OpError(_("index out of range: {path}", path=path))
        parent[idx] = to_node(value, None, parent[idx])
        return
    if not isinstance(parent, dict):
        raise OpError(_("parent is not a mapping: {path}", path=path))
    if last in parent or _key(last) in parent:
        key = _find_key(parent, last)
    else:
        # A new row of a value table: the key from JSON is a number, not the string "'99'"
        key = _key(last) if len(path) >= 2 and path[-2] == "values" else last
    if value is None or value == "":
        if key in parent:
            del parent[key]
        return
    if key not in parent and isinstance(parent, CommentedMap):
        # A new key goes to its place in the canonical order (mapcan fmt), not to the end
        from ..fmt import insert_position

        pos = insert_position(_kind_path(path[:-1]), list(parent.keys()), key)
        if pos is not None:
            parent.insert(pos, key, to_node(value, key))
            return
    parent[key] = to_node(value, key, parent.get(key))


def _upgrade_parent(doc, path: list) -> bool:
    """Before a current key is written or removed (or a key inside it), the deprecated keys it replaces in its node
    are renamed."""
    changed = False
    for i in renamed_along(_kind_path(path)):
        try:
            node = _get(doc, path[:i])
        except OpError:
            continue
        changed |= upgrade_map(node, _kind(path[:i]), only=path[i])
    return changed


def _kind_path(path: list) -> tuple:
    return tuple(int(x) if isinstance(x, str) and x.isdigit() else x for x in path)


def op_remove(doc, path: list) -> None:
    if _upgrade_parent(doc, path) and isinstance(p := _get(doc, path[:-1]), dict) and path[-1] not in p:
        return      # the deprecated key meant the default: nothing is left to remove
    parent, last = _parent(doc, path)
    if isinstance(parent, list):
        idx = int(last)
        if not 0 <= idx < len(parent):
            raise OpError(_("index out of range: {path}", path=path))
        del parent[idx]
    elif isinstance(parent, dict):
        try:
            del parent[_find_key(parent, last)]
        except KeyError as e:
            raise OpError(_("key not found: {path}", path=path)) from e
    else:
        raise OpError(_("cannot remove: {path}", path=path))


def op_insert(doc, path: list, value: Any, index: int | None = None) -> None:
    """Insert an item into the list at ``path`` (the list and the mappings above it are created if missing)."""
    _upgrade_parent(doc, path)
    try:
        _ensure_parent(doc, path)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        raise OpError(_("path not found: {path}", path=path)) from e
    parent, last = _parent(doc, path)
    if isinstance(parent, dict) and last not in parent and _key(last) not in parent:
        op_set(doc, path, [])           # a new list goes to its place in the canonical order, as a new key does
    elif isinstance(parent, dict) and parent[_find_key(parent, last)] is None:
        parent[_find_key(parent, last)] = to_node([], last)
    seq = _get(doc, path)
    if not isinstance(seq, list):
        raise OpError(_("not a list: {path}", path=path))
    node = to_node(value, path[-1] if path else None)
    if index is None or index >= len(seq):
        seq.append(node)
    else:
        seq.insert(max(0, int(index)), node)


def op_move(doc, path: list, to: int) -> None:
    parent, last = _parent(doc, path)
    if not isinstance(parent, list):
        raise OpError(_("only list items can be moved: {path}", path=path))
    idx, to = int(last), int(to)
    if not (0 <= idx < len(parent) and 0 <= to < len(parent)):
        raise OpError(_("index out of range"))
    item = parent.pop(idx)
    parent.insert(to, item)


def op_rename_key(doc, path: list, new_key: Any) -> None:
    """Rename a key of a mapping keeping its position (e.g. a number in a value table)."""
    parent, last = _parent(doc, path)
    if not isinstance(parent, CommentedMap):
        raise OpError(_("not a mapping: {path}", path=path))
    old = _find_key(parent, last)
    new = _key(new_key) if isinstance(old, int) or path[-2:-1] == ["values"] else new_key
    if new == old:
        return
    if new in parent:
        raise OpError(_("key {key!r} already exists", key=new))
    pos = list(parent.keys()).index(old)
    value = parent.pop(old)
    parent.insert(pos, new, value)


def layout_keys(start: int, length: int, big_endian: bool) -> dict:
    """The canonical notation of a position (#117), which parses back to the same start/length: by bytes when the
    signal takes whole bytes from a byte boundary (``byte`` + ``byte_length``) or fits in one byte (``byte`` + ``bit``
    + ``bit_length``), else ``start_bit`` + ``bit_length``."""
    candidates: list[dict] = []
    byte, bit = divmod(start, 8)
    if big_endian:
        if bit == 0 and length % 8 == 0:
            nbytes = length // 8
            first = byte - nbytes + 1
            if first >= 0:
                candidates.append({"byte": first, "byte_length": nbytes})
        if bit + length <= 8:
            candidates.append({"byte": byte, "bit": bit, "bit_length": length})
    else:
        if bit == 0 and length % 8 == 0:
            candidates.append({"byte": byte, "byte_length": length // 8})
        if bit + length <= 8:
            candidates.append({"byte": byte, "bit": bit, "bit_length": length})
    candidates.append({"start_bit": start, "bit_length": length})
    for c in candidates:
        try:
            s = Signal(name="x", encoding="number",
                       byte_order="big_endian" if big_endian else "little_endian", **c)
        except ValueError:
            continue
        if (s.start_bit, s.bit_length) == (start, length):
            return c
    return candidates[-1]


def op_set_layout(doc, path: list, start_bit: int, bit_length: int) -> None:
    sig = _get(doc, path)
    if not isinstance(sig, CommentedMap):
        raise OpError(_("not a signal: {path}", path=path))
    if (not all(isinstance(v, int) and not isinstance(v, bool) for v in (start_bit, bit_length))
            or not 0 <= start_bit < MAX_FRAME_BITS or not 1 <= bit_length <= 64):
        raise OpError(_("invalid position"))
    _write_layout(sig, start_bit, bit_length)


def _signal_of(sig: CommentedMap, keys: dict) -> Signal | None:
    """The signal's position with ``keys`` as its layout keys; None when it does not parse."""
    encoding = sig.get("encoding")
    order = sig.get("byte_order")
    # A float without a length is 32 bits long
    rep = "float" if sig.get("representation") == "float" else "unsigned"
    try:
        return Signal(name="x", encoding=encoding if encoding in ("number", "enum", "bitfield", "bytes") else "number",
                      representation=rep,
                      byte_order=order if order in ("big_endian", "little_endian") else "little_endian", **keys)
    except (ValueError, TypeError):
        return None


def _canonical_keys(sig: CommentedMap, start_bit: int, bit_length: int) -> dict | None:
    """The layout keys of the position in the canonical notation; None when the signal has them already. In the
    notation by bytes, a length the signal implies (a float's 32 bits) and ``bit: 0`` stay implicit
    when they are."""
    current = {k: sig[k] for k in LAYOUT_KEYS if k in sig}
    new = layout_keys(start_bit, bit_length, sig.get("byte_order") == "big_endian")
    if "byte" in new:
        drop = set()
        if "bit_length" not in current and "byte_length" not in current:
            drop |= {"bit_length", "byte_length"}
        if new.get("bit") == 0 and "byte" in current and "bit" not in current:
            drop.add("bit")
        short = {k: v for k, v in new.items() if k not in drop}
        if short != new and (s := _signal_of(sig, short)) is not None and (s.start_bit, s.bit_length) == (
                start_bit, bit_length):
            new = short
    return None if new == current else new


def canonical_position(sig: Any) -> dict | None:
    """The layout keys of a signal in the canonical notation (#117) when it has others and its position parses."""
    if not isinstance(sig, CommentedMap):
        return None
    s = _signal_of(sig, {k: sig[k] for k in LAYOUT_KEYS if k in sig})
    if s is None or s.start_bit is None or s.bit_length is None:
        return None
    return _canonical_keys(sig, s.start_bit, s.bit_length)


def _write_layout(sig: CommentedMap, start_bit: int, bit_length: int) -> None:
    """Write a position in the canonical notation where the layout keys of the signal are."""
    new = _canonical_keys(sig, start_bit, bit_length)
    if new is None:
        return
    keys = list(sig.keys())
    pos = min((keys.index(k) for k in LAYOUT_KEYS if k in sig), default=None)
    if pos is None:
        pos = max((keys.index(k) for k in ("name", "encoding", "description") if k in sig), default=-1) + 1
    for k in LAYOUT_KEYS:
        if k in sig:
            del sig[k]
    for i, (k, v) in enumerate(new.items()):
        sig.insert(pos + i, k, v)


def canonical_layout(sig: Any) -> None:
    """Rewrite the position of a signal in the canonical notation (#117), if it parses: the form edits its fields
    one by one, and ``bit_length: 12`` written next to ``byte: 1`` becomes ``start_bit: 8``."""
    s = _signal_of(sig, {k: sig[k] for k in LAYOUT_KEYS if k in sig}) if isinstance(sig, CommentedMap) else None
    if s is not None and s.start_bit is not None and s.bit_length is not None:
        _write_layout(sig, s.start_bit, s.bit_length)


OPS = {
    "set": lambda d, o: op_set(d, o["path"], o.get("value")),
    "remove": lambda d, o: op_remove(d, o["path"]),
    "insert": lambda d, o: op_insert(d, o["path"], o.get("value"), o.get("index")),
    "move": lambda d, o: op_move(d, o["path"], o["to"]),
    "rename_key": lambda d, o: op_rename_key(d, o["path"], o["new_key"]),
    "set_layout": lambda d, o: op_set_layout(d, o["path"], o["start_bit"], o["bit_length"]),
}


def check_editable(source, ops: list[dict]) -> None:
    """Nodes of included files (include) are edited only in their own file, not through the main one."""
    for o in ops:
        if isinstance(o.get("path"), list) and source.is_included(tuple(o["path"])):
            raise OpError(_("the node is described in the included file {file}: edit it there",
                            file=Path(source.file_of(tuple(o["path"])) or "").name))


def apply_ops(doc, ops: list[dict]) -> None:
    # Signals whose position fields were written one by one: their position is made canonical after the batch
    positioned: list[tuple[list, Any]] = []
    for o in ops:
        kind = o.get("op")
        if kind not in OPS:
            raise OpError(_("unknown operation: {op!r}", op=kind))
        path = o.get("path")
        if not isinstance(path, list):
            raise OpError(_("path must be a list"))
        try:
            OPS[kind](doc, o)
        except OpError:
            raise
        except (KeyError, TypeError, ValueError) as e:
            raise OpError(f"{kind}: {e}") from e
        if kind in ("set", "remove") and len(path) >= 3 and path[-3] == "signals" \
                and path[-1] in (*LAYOUT_KEYS, "byte_order"):
            sig = _get_or_none(doc, path[:-1])
            if isinstance(sig, CommentedMap):
                positioned.append((path[:-1], sig.get("name")))
    for path, name in positioned:
        # A later operation of the batch may have moved or removed the signal: only the same one is touched
        sig = _get_or_none(doc, path)
        if isinstance(sig, CommentedMap) and sig.get("name") == name:
            canonical_layout(sig)


def _get_or_none(doc, path: list) -> Any:
    try:
        return _get(doc, path)
    except (OpError, KeyError, IndexError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------- renaming devices

def _names(items: Any) -> list:
    return [d.get("name") if isinstance(d, dict) else None for d in items] if isinstance(items, list) else []


def _bus_frames(bus: dict, bp: list) -> list[tuple[list, dict]]:
    """All frames of the bus with their paths: the bus's own and the devices' frames."""
    out = []
    frames = bus.get("frames")
    if isinstance(frames, list):
        out += [([*bp, "frames", i], f) for i, f in enumerate(frames)]
    devices = bus.get("devices")
    if isinstance(devices, list):
        for di, d in enumerate(devices):
            frames = d.get("frames") if isinstance(d, dict) else None
            if isinstance(frames, list):
                out += [([*bp, "devices", di, "frames", i], f) for i, f in enumerate(frames)]
    return [(p, f) for p, f in out if isinstance(f, dict)]


def device_rename_ops(old: Any, new: Any) -> list[dict]:
    """Operations that carry device renames (made by editing the text) over to sender/receivers of the frames.

    A rename is recognized by place: the device at the same position of the same bus has another name,
    the old name is no longer among the bus devices, and the new one was not there before.
    Only references still pointing to the old name change. `old` and `new` are plain data.
    """
    ops: list[dict] = []
    old_buses = old.get("buses") if isinstance(old, dict) else None
    new_buses = new.get("buses") if isinstance(new, dict) else None
    if not isinstance(old_buses, list) or not isinstance(new_buses, list):
        return ops
    for bi, (ob, nb) in enumerate(zip(old_buses, new_buses, strict=False)):
        if not isinstance(ob, dict) or not isinstance(nb, dict):
            continue
        od, nd = _names(ob.get("devices")), _names(nb.get("devices"))
        renames = {a: b for a, b in zip(od, nd, strict=False)
                   if isinstance(a, str) and isinstance(b, str) and a and b and a != b
                   and a not in nd and b not in od}
        if not renames:
            continue
        for fp, f in _bus_frames(nb, ["buses", bi]):
            sender = f.get("sender")
            if isinstance(sender, str) and sender in renames:
                ops.append({"op": "set", "path": [*fp, "sender"], "value": renames[sender]})
            rec = f.get("receivers")
            if isinstance(rec, list) and any(isinstance(r, str) and r in renames for r in rec):
                ops.append({"op": "set", "path": [*fp, "receivers"],
                            "value": [renames.get(r, r) if isinstance(r, str) else r for r in rec]})
    return ops
