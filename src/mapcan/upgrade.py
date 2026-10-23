"""Deprecated keys of the format: their current names and how old values are converted.

Format v1 keeps every map that was valid readable (see "Versioning and compatibility" in docs/format.md).
When a key is renamed, its old spelling stays accepted: the loader rewrites it to the current one and reports
``deprecated-key``, the editors read and write the current key in place of the old one, and ``mapcan migrate``
rewrites a file. Everything after the loader (model, outputs, forms) knows only the current keys.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Path_ = tuple

# Returned by a converter when the current key is not written at all (its default applies).
DROP = object()


@dataclass(frozen=True)
class Rename:
    kind: str                       # node kind, see node_kind()
    old: tuple[str, ...]            # deprecated keys; the current key takes the place of the first one present
    new: str
    convert: Callable[[dict], Any] | None = None    # old key → value: the current key's value (or DROP)
    since: str = ""                 # mapcan version that introduced the current key
    nest: bool = False              # the old keys move as they are into the mapping ``new`` (old key → new.old key)

    def present(self, node) -> list[str]:
        """The deprecated keys written in ``node``: keys moved into a mapping keep their order in the node."""
        return [k for k in node if k in self.old] if self.nest else [k for k in self.old if k in node]

    def value(self, old: dict) -> Any:
        if self.nest:
            return dict(old)
        if self.convert is not None:
            return self.convert(old)
        return old[self.old[0]] if self.old[0] in old else DROP


def _representation(old: dict) -> Any:
    # signed_code without signed: true was ignored: the value is unsigned
    return old.get("signed_code") or "twos_complement" if old.get("signed") is True else DROP


PRINT_KEYS = ("logo", "designation", "litera", "city", "signatures", "approve", "agree")

RENAMES: list[Rename] = [
    # Print details of the title page belong to the templates, not to the map's metadata
    Rename("document", PRINT_KEYS, "print", nest=True, since="0.21"),
    Rename("bus", ("interface",), "connector", since="0.21"),
    Rename("frame", ("dlc",), "length", since="0.21"),
    # type: raw meant "no CANopen function": the current field is not written then
    Rename("frame", ("type",), "canopen", lambda old: DROP if old.get("type") == "raw" else old["type"], since="0.21"),
    Rename("signal", ("signed", "signed_code"), "representation", _representation, since="0.21"),
    Rename("signal", ("invalid",), "invalid_raw", since="0.21"),
    Rename("sdo_value", ("signed",), "representation",
           lambda old: "twos_complement" if old.get("signed") is True else DROP, since="0.21"),
]

_BY_KIND: dict[str, list[Rename]] = {}
for _r in RENAMES:
    _BY_KIND.setdefault(_r.kind, []).append(_r)


def renames(kind: str | None) -> list[Rename]:
    return _BY_KIND.get(kind or "", [])


def deprecated_of(kind: str | None, new: str) -> tuple[str, ...]:
    """Deprecated keys the current key ``new`` replaces in a node of this kind."""
    return next((r.old for r in renames(kind) if r.new == new), ())


def renamed_along(path: Path_) -> list[int]:
    """Positions ``i`` of ``path`` whose key ``path[i]`` replaces deprecated keys of the node ``path[:i]``: before
    a value is written there, the node has to be upgraded (``document.print.logo`` → ``i`` of ``print``)."""
    p = tuple(path)
    return [i for i in range(len(p)) if isinstance(p[i], str) and deprecated_of(node_kind(p[:i]), p[i])]


def node_kind(path: Path_) -> str | None:
    """Kind of the mapping at ``path`` of a map: document, bus, device, frame, signal, flag, sdo, sdo_value."""
    p = tuple(path)
    if p == ("document",):
        return "document"
    if len(p) < 2 or p[0] != "buses" or not isinstance(p[1], int):
        return None
    rest = p[2:]
    if not rest:
        return "bus"
    if rest[0] == "devices" and len(rest) >= 2:
        if len(rest) == 2:
            return "device"
        rest = rest[2:]
    if len(rest) < 2 or rest[0] != "frames" or not isinstance(rest[1], int):
        return None
    rest = rest[2:]
    if not rest:
        return "frame"
    if rest[0] == "signals" and len(rest) >= 2:
        if len(rest) == 2:
            return "signal"
        return "flag" if len(rest) == 4 and rest[2] == "flags" else None
    if rest[0] == "sdo" and len(rest) >= 2:
        if len(rest) == 2:
            return "sdo"
        return "sdo_value" if rest[2:] == ("value",) else None
    return None


@dataclass
class Upgraded:
    """A deprecated spelling found in a node: ``path`` is the node, ``old`` the keys present."""

    path: Path_
    rename: Rename
    old: tuple[str, ...]
    conflict: bool      # the current key is written too: the deprecated ones are ignored


def upgrade_node(kind: str | None, node: dict, path: Path_ = ()) -> tuple[dict, list[Upgraded]]:
    """The node with its deprecated keys replaced by the current ones (keeping the key order), and what was
    replaced. ``node`` itself is not changed."""
    found = []
    out = node
    for r in renames(kind):
        present = tuple(r.present(out))
        if not present:
            continue
        conflict = r.new in out
        found.append(Upgraded(path, r, present, conflict))
        value = DROP if conflict else r.value({k: out[k] for k in present})
        items = []
        for k, v in out.items():
            if k == present[0] and value is not DROP:
                items.append((r.new, value))
            if k not in present:
                items.append((k, v))
        out = dict(items)
    return out, found


def upgrade_tree(data: Any, on_found: Callable[[Upgraded], None] | None = None) -> Any:
    """Plain data of a map with every deprecated key replaced (a new structure; ``data`` is not changed)."""

    def walk(node, path):
        if isinstance(node, dict):
            node, found = upgrade_node(node_kind(path), node, path)
            for f in found:
                if on_found:
                    on_found(f)
            return {k: walk(v, path + (k,)) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, path + (i,)) for i, v in enumerate(node)]
        return node

    return walk(data, ())


# --------------------------------------------------------------------------- format version 1

# Version 2 of the format (#140) has four signal encodings; version 1 had eight. A map of version 1 is read with
# its encodings converted, and mapcan migrate rewrites it. Version 2 itself does not read them.
V1_ENCODINGS = {"raw": "number", "scaled": "number", "float": "number", "flag": "enum", "string": "bytes"}
V1_KINDS = ("signal", "sdo_value")


def v1_encoding(node: dict) -> tuple[str, dict] | None:
    """The version 2 encoding of a signal (or SDO value) of version 1 and the keys to add after it, which keep its
    meaning: a float's representation, a flag's length, a string's charset. None: nothing to change."""
    old = node.get("encoding")
    if not isinstance(old, str) or old not in V1_ENCODINGS:
        return None
    add: dict = {}
    if old == "float" and "representation" not in node:
        add["representation"] = "float"
    elif old == "flag" and "bit_length" not in node and "byte_length" not in node:
        add["bit_length"] = 1
    elif old == "string" and "charset" not in node:
        add["charset"] = "ascii"         # the default of version 1
    return V1_ENCODINGS[old], add


def upgrade_v1_node(kind: str | None, node: dict) -> dict:
    """A node of a version 1 map as version 2 reads it (``node`` itself is not changed)."""
    change = v1_encoding(node) if kind in V1_KINDS else None
    if change is None:
        return node
    new, add = change
    items = []
    for k, v in node.items():
        items.append((k, new if k == "encoding" else v))
        if k == "encoding":
            items += list(add.items())
    return dict(items)


def upgrade_v1(data: Any, on_found: Callable[[Path_], None] | None = None) -> Any:
    """Plain data of a version 1 map as version 2 (a new structure; ``data`` is not changed). ``on_found`` gets the
    path of each converted node."""

    def walk(node, path):
        if isinstance(node, dict):
            new = upgrade_v1_node(node_kind(path), node)
            if new is not node and on_found:
                on_found(path)
            return {k: walk(v, path + (k,)) for k, v in new.items()}
        if isinstance(node, list):
            return [walk(v, path + (i,)) for i, v in enumerate(node)]
        return node

    out = walk(data, ())
    if isinstance(out, dict) and out.get("mapcan") == 1:
        out["mapcan"] = 2
    return out


def upgrade_data(data: Any) -> Any:
    """Plain data of a map with the current names and, for a map of version 1, the encodings of version 2: what the
    editors show."""
    data = upgrade_tree(data)
    return upgrade_v1(data) if isinstance(data, dict) and data.get("mapcan") == 1 else data
