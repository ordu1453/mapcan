"""``mapcan fmt``: maps written in one key order.

Only the order of the keys of each node changes, to the order below (the order of docs/format.md, with
the notes after the description and the child lists last). Everything else stays as the author wrote it:
comments (they move with their key), blank lines, block or flow style, the position notation
(``start_bit`` or ``byte``) and the number base. A key the format does not know keeps its place after the
known ones. Value tables keep their order.

The text is rewritten line by line, not dumped again, so a map that is already in order is not touched
at all; the result is checked to read as the same data.
"""

from __future__ import annotations

from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .i18n import _
from .upgrade import node_kind
from .web.yamlops import make_yaml, plain

ORDER: dict[str, tuple[str, ...]] = {
    "root": ("mapcan", "part_of", "document", "include", "lint", "value_tables", "buses"),
    "document": ("title", "subtitle", "version", "date", "author", "organization", "language", "bit_numbering",
                 "print", "history"),
    "print": ("logo", "designation", "litera", "city", "signatures", "approve", "agree"),
    "history": ("version", "date", "author", "github", "changes"),
    "lint": ("signal_name", "frame_name", "device_name", "value_name", "disable"),
    "bus": ("name", "title", "description", "protocol", "connector", "bitrate", "sample_point", "fd",
            "data_bitrate", "data_sample_point", "brs", "frames", "devices"),
    "device": ("name", "short", "title", "description", "node_id", "address", "frames"),
    "frame": ("name", "title", "description", "comment", "canopen", "id", "extended", "pgn", "priority",
              "destination", "length", "brs", "direction", "cycle_ms", "trigger", "inhibit_ms",
              "timeout_ms", "sender",
              "receivers", "signals", "sdo"),
    "signal": ("name", "title", "description", "comment", "encoding", "start_bit", "byte", "bit", "bit_length",
               "byte_length", "byte_order", "representation", "charset", "terminator", "factor", "offset", "unit",
               "min", "max", "values", "value_format", "flags", "multiplexer", "mux", "initial", "source",
               "invalid_raw", "spn", "index", "subindex"),
    "flag": ("name", "bit", "bit_length", "description", "values"),
    "sdo": ("name", "description", "command", "index", "subindex", "value"),
    "sdo_value": ("name", "encoding", "description", "bit_length", "representation", "factor", "offset", "unit",
                  "min", "max", "values"),
}

WIDTH = 120      # the longest line a flow mapping written over several lines is wrapped to when its order changes


class FmtError(ValueError):
    pass


def kind_of(path: tuple) -> str | None:
    if path == ():
        return "root"
    if path == ("document", "print"):
        return "print"
    if path == ("lint",):
        return "lint"
    if len(path) == 3 and path[:2] == ("document", "history") and isinstance(path[2], int):
        return "history"
    return node_kind(path)


def ordered(kind: str | None, keys: list) -> list:
    """The keys in the canonical order of the node's kind; unknown keys after the known ones, in their order."""
    order = ORDER.get(kind or "")
    if not order:
        return list(keys)
    rank = {k: i for i, k in enumerate(order)}
    known = sorted((k for k in keys if k in rank), key=lambda k: rank[k])
    return known + [k for k in keys if k not in rank]


def insert_position(path: tuple, keys: list, key: Any) -> int | None:
    """Where a new ``key`` goes among the ``keys`` of the node at ``path``: before the first key that comes after
    it in the canonical order; None to add it at the end."""
    order = ORDER.get(kind_of(tuple(path)) or "")
    if not order or key not in order:
        return None
    rank = {k: i for i, k in enumerate(order)}
    return next((i for i, k in enumerate(keys) if k in rank and rank[k] > rank[key]), None)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _blank(line: str) -> bool:
    return not line.strip()


class _Formatter:
    def __init__(self, text: str):
        self.text = text
        self.lines = text.splitlines(keepends=True)
        self.doc = make_yaml(text).load(text)

    # ------------------------------------------------------------------ regions

    def _end(self, line: int, col: int) -> int:
        """End (exclusive) of the lines of a key or an item at ``line`` whose content is deeper than ``col``:
        blank lines and comments of what follows stay outside."""
        lines, n = self.lines, len(self.lines)
        end = line + 1
        while end < n and (_blank(lines[end]) or _comment(lines[end]) or _indent(lines[end]) > col):
            end += 1
        while end > line + 1 and (_blank(lines[end - 1]) or (_comment(lines[end - 1])
                                                               and _indent(lines[end - 1]) <= col)):
            end -= 1
        return end

    def spans(self, m: CommentedMap, on_dash: bool) -> list[tuple[Any, int, int]]:
        """(key, first line, end line) of each key of a block mapping; a key's comment lines just above it
        belong to it (not those above the first key of a list item: they belong to the item)."""
        keys = list(m.keys())
        kcol = m.lc.key(keys[0])[1]
        out = []
        for i, k in enumerate(keys):
            kl = m.lc.key(k)[0]
            start = kl
            if not (on_dash and i == 0):
                while start > 0 and _comment(self.lines[start - 1]) and _indent(self.lines[start - 1]) == kcol:
                    start -= 1
            out.append((k, start, self._end(kl, kcol)))
        return out

    def seq_end(self, s: CommentedSeq) -> int:
        last = s.lc.item(len(s) - 1)[0]
        dash = self.lines[last].index("-") if "-" in self.lines[last] else 0
        return self._end(last, dash)

    # ------------------------------------------------------------------ emitting

    def block_map(self, m: CommentedMap, path: tuple, on_dash: bool) -> tuple[int, int, list[str]]:
        """Region (first line, end line) of a block mapping and its lines in the canonical order."""
        spans = self.spans(m, on_dash)
        pieces = {k: self.key_lines(m, k, s, e, path) for k, s, e in spans}
        gaps = [self.lines[spans[i][2]:spans[i + 1][1]] for i in range(len(spans) - 1)]
        keys = [k for k, _s, _e in spans]
        new = ordered(kind_of(path), keys)
        if on_dash and new[0] != keys[0]:
            first = pieces[new[0]]
            if not first or _comment(first[0]):
                new = keys          # the new first key has comments above it: the item keeps its order
        out: list[str] = []
        for i, k in enumerate(new):
            out += pieces[k]
            if i < len(gaps):
                out += gaps[i]
        if on_dash and new[0] != keys[0]:
            kcol = m.lc.key(keys[0])[1]
            # "- " moves to the line of the new first key, the former first key gets plain indentation
            old_first = pieces[keys[0]][0]
            prefix = old_first[:kcol]
            out = [ln for ln in out]
            i_old = out.index(old_first)
            out[i_old] = " " * kcol + old_first[kcol:]
            i_new = out.index(pieces[new[0]][0]) if pieces[new[0]][0] in out else 0
            out[i_new] = prefix + out[i_new][kcol:]
        return spans[0][1], spans[-1][2], out

    @staticmethod
    def _first_line(v: Any) -> int | None:
        if isinstance(v, CommentedMap) and len(v):
            return v.lc.key(next(iter(v)))[0]
        if isinstance(v, CommentedSeq) and len(v):
            return v.lc.item(0)[0]
        return None

    def key_lines(self, m: CommentedMap, k: Any, start: int, end: int, path: tuple) -> list[str]:
        v = m[k]
        p = path + (k,)
        first = self._first_line(v)
        if first is not None and not start <= first < end:
            return self.lines[start:end]        # an alias (*name): the node is written at its anchor
        if isinstance(v, CommentedMap) and len(v) and not v.fa.flow_style():
            cs, ce, inner = self.block_map(v, p, False)
            return self.lines[start:cs] + inner + self.lines[ce:end]
        if isinstance(v, CommentedSeq) and len(v) and not v.fa.flow_style():
            cs, ce, inner = self.block_seq(v, p)
            return self.lines[start:cs] + inner + self.lines[ce:end]
        if isinstance(v, CommentedMap) and len(v):
            return self.flow_in(self.lines[start:end], start, m.lc.value(k), v, p)
        return self.lines[start:end]

    def block_seq(self, s: CommentedSeq, path: tuple) -> tuple[int, int, list[str]]:
        starts = [s.lc.item(i)[0] for i in range(len(s))]
        end = self.seq_end(s)
        out: list[str] = []
        for i, item in enumerate(s):
            item_start = starts[i]
            item_end = starts[i + 1] if i + 1 < len(s) else end
            p = path + (i,)
            first = self._first_line(item)
            if first is not None and not item_start <= first < max(item_end, item_start + 1):
                out += self.lines[item_start:item_end]      # an alias
            elif isinstance(item, CommentedMap) and len(item) and not item.fa.flow_style():
                kl, kcol = item.lc.key(next(iter(item)))
                on_dash = self.lines[kl][:kcol].strip().startswith("-")
                ms, me, inner = self.block_map(item, p, on_dash)
                out += self.lines[item_start:ms] + inner + self.lines[me:item_end]
            elif isinstance(item, CommentedMap) and len(item):
                out += self.flow_in(self.lines[item_start:item_end], item_start, s.lc.item(i), item, p)
            else:
                out += self.lines[item_start:item_end]
        return starts[0], end, out

    # ------------------------------------------------------------------ flow mappings

    def flow_in(self, chunk: list[str], first: int, pos: tuple[int, int], m: CommentedMap,
                path: tuple) -> list[str]:
        """``chunk`` (lines from ``first``) with the flow mapping at ``pos`` in the canonical order."""
        keys = list(m.keys())
        new = ordered(kind_of(path), keys)
        if new == keys:
            return chunk
        line, col = pos[0] - first, pos[1]
        found = _flow_items(chunk, line, col)
        if found is None:
            return chunk            # a comment inside, or a form not understood: left as written
        items, end_line, end_col = found
        if [k for k, _t in items] != [str(k) for k in keys]:
            return chunk
        text = dict(items)
        parts = [text[str(k)] for k in new]
        prefix, suffix = chunk[line][:col], chunk[end_line][end_col:]
        if end_line == line:
            return chunk[:line] + [prefix + "{" + ", ".join(parts) + "}" + suffix] + chunk[line + 1:]
        cont = " " * _indent(chunk[line + 1])
        # Wrapped at the width the author wrapped it at, so it keeps its shape
        width = min(WIDTH, max(len(r.rstrip("\n")) for r in chunk[line:end_line + 1]))
        rows, cur = [], prefix + "{"
        for i, part in enumerate(parts):
            piece = part + ("," if i + 1 < len(parts) else "}")
            sep = "" if cur.endswith("{") else " "
            if len(cur) + len(sep) + len(piece) > width and not cur.endswith("{"):
                rows.append(cur + "\n")
                cur = cont + piece
            else:
                cur += sep + piece
        rows.append(cur + suffix)
        return chunk[:line] + rows + chunk[end_line + 1:]

    # ------------------------------------------------------------------

    def run(self) -> str:
        d = self.doc
        if not isinstance(d, CommentedMap) or not len(d) or d.fa.flow_style():
            return self.text
        start, end, out = self.block_map(d, (), False)
        return "".join(self.lines[:start] + out + self.lines[end:])


def _flow_items(chunk: list[str], line: int, col: int) -> tuple[list[tuple[str, str]], int, int] | None:
    """The top-level ``key: value`` items of the flow mapping whose "{" is at (line, col), and the position
    after its "}"; None if it has a comment or cannot be split."""
    items: list[tuple[str, str]] = []
    depth, quote, cur = 0, "", ""
    ln, c = line, col
    while ln < len(chunk):
        s = chunk[ln]
        while c < len(s):
            ch = s[c]
            if quote:
                cur += ch
                if ch == quote:
                    quote = ""
            elif ch in "\"'":
                quote = ch
                cur += ch
            elif ch == "#" and (c == 0 or s[c - 1] in " \t"):
                return None
            elif ch in "{[":
                depth += 1
                if depth > 1:
                    cur += ch
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    if cur.strip():
                        items.append(cur.strip())
                    pairs = []
                    for it in items:
                        key, sep, _rest = it.partition(":")
                        if not sep:
                            return None
                        pairs.append((key.strip().strip("\"'"), it))
                    return pairs, ln, c + 1
                cur += ch
            elif ch == "," and depth == 1:
                items.append(cur.strip())
                cur = ""
            elif ch == "\n" and depth == 1:
                cur += " "
            else:
                cur += ch
            c += 1
        ln, c = ln + 1, 0
    return None


def format_text(text: str) -> str:
    """The map's text with the keys of every node in the canonical order (see the module)."""
    try:
        new = _Formatter(text).run()
    except Exception as e:  # noqa: BLE001 — not YAML, or a layout not handled: reported, the file is kept
        raise FmtError(_("cannot format: {error}", error=e)) from e
    if new != text and (plain(make_yaml(new).load(new)) != plain(make_yaml(text).load(text))
                        or new.count("#") != text.count("#")):
        raise FmtError(_("cannot format: the result would read differently; the file is left as it is"))
    return new


def position_notes(text: str) -> list[tuple[int, str, str]]:
    """Signals whose position is not written in the canonical notation the editors use (#117): (line from 1, signal,
    the canonical keys as YAML). ``mapcan fmt`` does not rewrite them: they are reported by ``--check`` only."""
    from .web.yamlops import canonical_position

    try:
        doc = make_yaml(text).load(text)
    except Exception:  # noqa: BLE001 — not YAML: format_text reports it
        return []
    out = []

    def frames(node: Any) -> list:
        items = node.get("frames") if isinstance(node, CommentedMap) else None
        return items if isinstance(items, CommentedSeq) else []

    buses = doc.get("buses") if isinstance(doc, CommentedMap) else None
    for bus in buses if isinstance(buses, CommentedSeq) else []:
        devices = bus.get("devices") if isinstance(bus, CommentedMap) else None
        owners = [bus, *(devices if isinstance(devices, CommentedSeq) else [])]
        for frame in (f for o in owners for f in frames(o)):
            signals = frame.get("signals") if isinstance(frame, CommentedMap) else None
            for sig in signals if isinstance(signals, CommentedSeq) else []:
                if (keys := canonical_position(sig)) is not None:
                    written = ", ".join(f"{k}: {v}" for k, v in keys.items())
                    out.append((sig.lc.line + 1, str(sig.get("name", "?")), written))
    return out
