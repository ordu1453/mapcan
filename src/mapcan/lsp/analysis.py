"""Analysis of a map's text for the language server: diagnostics, outline, hints.

The module does not depend on pygls: positions here are 0-based (line, column), as in LSP,
and :mod:`mapcan.lsp.server` converts them to the protocol's types.
"""

from __future__ import annotations

import re
import typing
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from .. import model as M
from ..bits import msb_position, occupied_bits
from ..diagnostics import Diagnostic
from ..docmodel import fmt_num
from ..i18n import _, normalize_language
from ..loader import PART_OF_RE, LoadResult, SourceMap, loads, paused_gc
from ..model import MapCan, enum_entries
from ..validate import check

Pos = tuple[int, int]          # 0-based (line, column)
Path_ = tuple

_HEADER = re.compile(r"^mapcan\s*:", re.MULTILINE)
_WORD = r"[^\s,\[\]{}#:]+(?::[^\s,\[\]{}#:]+)*"
_TOKEN = re.compile(rf"""("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|{_WORD}(?:[ \t]+{_WORD})*)""")
_KEY = re.compile(r"([A-Za-z_][\w]*)\s*:(?=\s|$)")


_PART = re.compile(r"^part_of\s*:", re.MULTILINE)


def is_mapcan(text: str) -> bool:
    """Whether the YAML looks like a mapcan map (the top-level key ``mapcan:``). A file included by a map
    (``part_of:``) is not one: it is checked as a part of its map."""
    return _HEADER.search(text) is not None and _PART.search(text) is None


def is_part(text: str) -> bool:
    """A file included by a map (``part_of: <map>``): analysed as a part of that map."""
    return PART_OF_RE.search(text) is not None


def part_of(text: str) -> str | None:
    m = PART_OF_RE.search(text)
    return next((g for g in m.groups() if g), None) if m else None


def handled(text: str) -> bool:
    """A map or a part of one: the documents the language server works with."""
    return is_mapcan(text) or is_part(text)


def _same_file(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and Path(a).resolve() == Path(b).resolve()


# --------------------------------------------------------------------------- #
# Nodes and their ranges in the text
# --------------------------------------------------------------------------- #


@dataclass
class Node:
    path: Path_
    start: Pos
    end: Pos = (0, 0)


def _is_prefix(a: Path_, b: Path_) -> bool:
    return len(a) < len(b) and b[: len(a)] == a


def node_ranges(src: SourceMap, lines: list[str], file: str | None = None) -> dict[Path_, Node]:
    """Range of each node: from its start to the start of the next node outside its subtree.

    Nodes of the main file, or with ``file`` the nodes of that included file (positions in it)."""
    nodes = [Node(p, (ln - 1, col - 1)) for p, (ln, col) in src.positions.items() if src.files.get(p) == file]
    nodes.sort(key=lambda n: (n.start, len(n.path)))
    doc_end = (len(lines), 0)
    stack: list[Node] = []
    for n in nodes:
        while stack and not _is_prefix(stack[-1].path, n.path):
            stack.pop().end = n.start
        stack.append(n)
    for n in stack:
        n.end = doc_end
    return {n.path: n for n in nodes}


@dataclass
class Analysis:
    text: str
    result: LoadResult
    diagnostics: list[Diagnostic]
    lines: list[str] = field(default_factory=list)
    nodes: dict[Path_, Node] = field(default_factory=dict)
    # The other files of the map: file name → its text and the ranges of the nodes in it. For the main file,
    # the included files; for an included file (own_file), the main file and the other included files.
    included: dict[str, Analysis] = field(default_factory=dict)
    # The file this text is, if it is a file included by the map (its name as the loader has it); None: the main
    # file. Paths stay the map's: an included device that extends a bus of the main file is buses[0].devices[2].
    own_file: str | None = None
    # Texts of the other files read for the analysis (file → text): a change in any of them makes it outdated
    deps: dict[str, str] = field(default_factory=dict)

    @property
    def map(self) -> MapCan | None:
        return self.result.map

    @property
    def data(self):
        """Data of the map for the tree and the form: together with the included files, if any."""
        return self.result.merged if self.result.merged is not None else self.result.raw

    @property
    def raw(self):
        """The data at the paths of :attr:`nodes`: the main file's YAML, or for an included file the whole map."""
        return self.data if self.own_file else self.result.raw

    def file_of(self, path: Path_) -> str | None:
        src = self.result.source
        return src.file_of(path) if src.is_included(path) else src.file

    def included_file(self, path: Path_) -> str | None:
        """The other file the node is described in; None for a node of this text."""
        f = self.file_of(path)
        return None if f == (self.own_file or self.result.source.file) else f

    def view_of(self, path: Path_) -> Analysis | None:
        """The analysis that has the text of the node: this one or one of :attr:`included`."""
        f = self.included_file(path)
        return self.included.get(f) if f else self

    def token_end(self, start: Pos) -> Pos:
        """End of the scalar (or the first word) that starts at ``start``."""
        line, col = start
        if line >= len(self.lines):
            return start
        m = _TOKEN.match(self.lines[line], col)
        return (line, m.end()) if m and m.end() > col else (line, min(col + 1, len(self.lines[line])))

    def block(self, path: Path_) -> tuple[Pos, Pos] | None:
        """The whole text of a node: from its start to the end of the last line with content.

        The range of a node (:func:`node_ranges`) ends where the value of the next node starts,
        so it takes in that node's key or "- " and the empty lines and comments before it; here they
        are cut off.
        """
        n = self.nodes.get(path)
        if n is None:
            return None
        (sl, sc), (el, ec) = n.start, n.end
        if sl < len(self.lines) and self.lines[sl][sc:sc + 1] in ("{", "["):
            end = self._closing(n.start)
            if end is not None:
                return n.start, end
        if el > sl:
            # The next node is on another line: the node ends on the last line before it that has
            # something besides a comment and an indent not less than at the node's start (a line with a
            # smaller indent is a key of the parent, e.g. "sdo:" after the last signal).
            last = el - 1
            while last > sl:
                text = self.lines[last]
                code = _strip_comment(text).rstrip()
                if code.strip() and len(text) - len(text.lstrip()) >= sc:
                    break
                last -= 1
            line = self.lines[last]
            return n.start, (last, len(_strip_comment(line).rstrip()))
        # The next node is on the same line (flow "{…}" or "[…]"): up to the separator before it
        line = self.lines[sl] if sl < len(self.lines) else ""
        end = len(line) if el > sl else ec
        text = line[sc:end]
        m = re.search(r"\s*(?:,\s*)?(?:[A-Za-z_]\w*\s*:\s*|-\s+)?$", text)
        return n.start, (sl, sc + (m.start() if m else len(text)))

    def _closing(self, start: Pos) -> Pos | None:
        """Position after the bracket that matches the opening one at ``start`` (minding quotes and nesting)."""
        depth, quote = 0, ""
        line, col = start
        while line < len(self.lines):
            text = self.lines[line]
            while col < len(text):
                ch = text[col]
                if quote:
                    if ch == "\\" and quote == '"':
                        col += 1
                    elif ch == quote:
                        quote = ""
                elif ch in "\"'":
                    quote = ch
                elif ch == "#" and (col == 0 or text[col - 1] in " \t"):
                    break
                elif ch in "{[":
                    depth += 1
                elif ch in "}]":
                    depth -= 1
                    if depth == 0:
                        return line, col + 1
                col += 1
            line, col = line + 1, 0
        return None

    def path_at(self, pos: Pos) -> Path_:
        """The deepest node whose range contains the position."""
        best: Path_ = ()
        for n in self.nodes.values():
            if n.start <= pos < n.end and len(n.path) >= len(best):
                best = n.path
        return best


_COMMENT = re.compile(r"""^((?:[^#"']|"(?:[^"\\]|\\.)*"|'(?:[^']|'')*')*?)\s+#.*$""")


def _strip_comment(line: str) -> str:
    """The line without a trailing comment (" # …" outside quotes)."""
    if line.lstrip().startswith("#"):
        return ""
    m = _COMMENT.match(line)
    return m.group(1) if m else line


Reader = typing.Callable[[str], "str | None"]


def read_disk(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _views(a: Analysis, result: LoadResult, read: Reader, skip: str | None) -> None:
    """Analyses of the included files (all but ``skip``) for :attr:`Analysis.included`."""
    for _i, fname in result.source.includes:
        if fname == skip:
            continue
        sub_text = read(str(Path(fname).resolve()))
        if sub_text is None:
            continue
        a.deps[str(Path(fname).resolve())] = sub_text
        sub_lines = sub_text.splitlines()
        a.included[fname] = Analysis(sub_text, result, [], sub_lines, node_ranges(result.source, sub_lines, fname),
                                     own_file=fname)


def analyze(text: str, filename: str | None = None, read: Reader = read_disk) -> Analysis:
    """Analysis of a map; ``read`` gives the texts of its included files (the editor's, if they are open)."""
    with paused_gc():
        return _analyze(text, filename, read)


def _analyze(text: str, filename: str | None, read: Reader) -> Analysis:
    result = loads(text, filename, read=read)
    report = check(result)
    lines = text.splitlines()
    # Messages about included files (include) are shown on the include line of the main file
    diags = [result.source.in_main_file(d) for d in report.sorted()]
    a = Analysis(text, result, diags, lines, node_ranges(result.source, lines))
    _views(a, result, read, None)
    return a


def analyze_part(text: str, filename: str, read: Reader = read_disk) -> Analysis:
    """Analysis of a file included by a map (``part_of``), as a part of that map: its messages in its own text,
    the map's tree with the nodes of the other files marked with their file."""
    of = part_of(text) or ""
    main = str((Path(filename).resolve().parent / of).resolve())
    own = str(Path(filename).resolve())
    lines = text.splitlines()
    main_text = read(main)
    result = loads(main_text, main, read=lambda p: text if _same_file(p, own) else read(p)) \
        if main_text is not None else None
    fname = next((f for _i, f in result.source.includes if _same_file(f, own)), None) if result else None
    if result is None or fname is None:
        # The map is not there or does not include this file: the file is read on its own
        alone = loads(text, filename)
        line, col = alone.source.positions.get(("part_of",), (1, 1))
        msg = (_("part_of: the map {map!r} is not found", map=of) if result is None else
               _("part_of: the map {map!r} does not include this file", map=of))
        return Analysis(text, alone, [Diagnostic("error", "include", msg, filename, line, col, "part_of",
                                                 ["part_of"])], lines, {}, own_file=own,
                        deps={main: main_text} if main_text is not None else {})
    report = check(result)
    mine = [d for d in report.sorted() if _same_file(d.file, own)]
    elsewhere = [d for d in report.sorted() if d.level == "error" and not _same_file(d.file, own)]
    if elsewhere:
        line, col = _part_of_pos(lines)
        mine.insert(0, Diagnostic("warning", "include",
                                  _("the map {map!r} has {n} error(s) outside this file: open it to see them",
                                    map=of, n=len(elsewhere)), own, line, col, "part_of", ["part_of"]))
    a = Analysis(text, result, mine, lines, node_ranges(result.source, lines, fname), own_file=fname,
                 deps={main: main_text})
    main_lines = main_text.splitlines()
    a.included[result.source.file] = Analysis(main_text, result, [], main_lines,
                                              node_ranges(result.source, main_lines, None))
    _views(a, result, read, fname)
    return a


def _part_of_pos(lines: list[str]) -> tuple[int, int]:
    """1-based position of the value of ``part_of`` (the key is not a node of the map)."""
    for i, ln in enumerate(lines):
        m = PART_OF_RE.match(ln)
        if m:
            return i + 1, m.start(next(g for g in range(1, 4) if m.group(g))) + 1
    return 1, 1


def diagnostic_range(a: Analysis, d: Diagnostic) -> tuple[Pos, Pos]:
    if d.line is None:
        return (0, 0), (0, 0)
    start = (d.line - 1, (d.column or 1) - 1)
    return start, a.token_end(start)


# --------------------------------------------------------------------------- #
# Outline
# --------------------------------------------------------------------------- #


@dataclass
class Symbol:
    name: str
    kind: str            # bus | device | frame | signal | flag
    detail: str
    range: tuple[Pos, Pos]
    selection: tuple[Pos, Pos]
    children: list[Symbol] = field(default_factory=list)


_CHILDREN = {"bus": (("frames", "frame"), ("devices", "device")),
             "device": (("frames", "frame"),),
             "frame": (("signals", "signal"),),
             "signal": (("flags", "flag"),)}


def symbols(a: Analysis) -> list[Symbol]:
    """Tree of buses, devices, frames and signals from the raw YAML (it works even if the model has errors).

    In an included file a node written in another file (a bus of the main file that the included file extends)
    is left out, and its children in this file take its place."""
    raw = a.raw
    if not isinstance(raw, dict):
        return []

    def children(node, path: Path_, kind: str) -> list[Symbol]:
        out = []
        for key, child_kind in _CHILDREN.get(kind, ()):
            items = node.get(key)
            if isinstance(items, list):
                for i, item in enumerate(items):
                    out += build(item, path + (key, i), child_kind)
        return out

    def build(node, path: Path_, kind: str) -> list[Symbol]:
        if not isinstance(node, dict):
            return []
        if path not in a.nodes:
            return children(node, path, kind) if a.own_file else []
        n = a.nodes[path]
        name_path = path + ("name",)
        sel_start = a.nodes[name_path].start if name_path in a.nodes else n.start
        sym = Symbol(str(node.get("name", "?")), kind, _detail(a, node, path, kind),
                     (n.start, n.end), (sel_start, a.token_end(sel_start)))
        sym.children = children(node, path, kind)
        return [sym]

    buses = raw.get("buses")
    if not isinstance(buses, list):
        return []
    return [s for i, b in enumerate(buses) for s in build(b, ("buses", i), "bus")]


def _detail(a: Analysis, node: dict, path: Path_, kind: str) -> str:
    """Label of a node: from the model (computed ID, bits) if the map parses, otherwise from the raw YAML."""
    obj = _find(a.map, path) if a.map is not None and kind in ("frame", "signal") else None
    if isinstance(obj, M.Frame) and obj.can_id is not None:
        return _hex(obj.can_id, obj.extended)
    if isinstance(obj, M.Signal):
        return f"{obj.encoding} · {signal_bits(obj)}"
    if kind == "bus":
        return str(node.get("protocol", "canopen"))
    if kind == "frame":
        for key in ("id", "pgn"):
            if isinstance(node.get(key), int):
                return f"{key} 0x{node[key]:X}" if key == "pgn" else f"0x{node[key]:X}"
        return str(node.get("canopen", node.get("type", "")))
    if kind == "signal":
        return str(node.get("encoding", ""))
    return ""


# --------------------------------------------------------------------------- #
# Map tree (side bar): the same nodes and labels as in the web editor's tree
# --------------------------------------------------------------------------- #


def _hexw(v, width: int) -> str:
    return f"0x{v:0{width}X}" if isinstance(v, int) else "—"


def _txt(value, lang: str) -> str:
    """Text of the raw YAML (a string or {ru, en}) in the document language, falling back to any available."""
    if isinstance(value, dict):
        return str(value.get(lang) or next((v for v in value.values() if v), "") or "")
    return "" if value is None else str(value)


def doc_language(a: Analysis) -> str:
    raw = a.result.raw
    doc = raw.get("document") if isinstance(raw, dict) else None
    lang = doc.get("language") if isinstance(doc, dict) else None
    return normalize_language(lang) or "ru"


def display_name(d: dict, lang: str) -> str:
    """Label of a node as in the web editor: the title for people, the identifier if there is no title;
    a device has its abbreviation before the title."""
    title = _txt(d.get("title"), lang) or ("—" if d.get("name") is None else str(d["name"]))
    return f"{d['short']} · {title}" if d.get("short") else title


def device_label(d: dict, lang: str) -> str:
    """Short label of a device in references to it: the abbreviation, else the full name."""
    return str(d["short"]) if d.get("short") else display_name(d, lang)


def map_tree(a: Analysis) -> list[dict]:
    """Nodes: kind, label, ident, description, dir (frames), from (received frames), range, selection, children.

    Labels are as in the web editor's tree: titles in the document language, the identifier (``ident``)
    only if there is no title. Built from the raw YAML; computed IDs and bits come from the model if the map parses.

    Nodes of included files (include) are in their places in the tree, with ``file`` (the file's full path):
    their ranges are in the text of that file, and they can be edited only there.
    """
    raw = a.data
    buses = raw.get("buses") if isinstance(raw, dict) else None
    if not isinstance(buses, list):
        return []
    lang = doc_language(a)

    def rng(path: Path_) -> dict | None:
        part = a.view_of(path)
        # In an included file opened on its own every node has its file: the tree's add and delete are not
        # offered there yet, the form edits it (through mapcan.lsp.set)
        file = a.included_file(path) or a.own_file
        block = part.block(path) if part is not None else None
        if block is None:
            return None
        (sl, sc), end = block
        # The cursor on the indent or on the "- " before a node belongs to it too
        own_line = re.fullmatch(r"\s*(?:-\s+)*", part.lines[sl][:sc]) is not None
        name = part.nodes.get(path + ("name",))
        out = {"range": [sl, 0 if own_line else sc, *end], "selection": [sl, sc, *end], "path": list(path),
               "name": list(name.start) if name else None}
        if file:
            out["file"] = file
        return out

    def name_of(d: dict) -> str:
        return "—" if d.get("name") is None else str(d["name"])

    def model(path: Path_):
        return _find(a.map, path) if a.map is not None else None

    def frame_node(f: dict, path: Path_) -> dict | None:
        loc = rng(path)
        if loc is None:
            return None
        rf = model(path)
        sub = ""
        if isinstance(f.get("pgn"), int):
            sub = f"PGN {_hexw(f['pgn'], 4)}"
        elif isinstance(rf, M.Frame) and rf.can_id is not None:
            sub = _hex(rf.can_id, rf.extended)
        node = {"kind": "frame", "label": display_name(f, lang), "ident": name_of(f), "description": sub,
                "dir": rf.direction if isinstance(rf, M.Frame) and rf.device is not None else None,
                "children": [], **loc}
        for si, s in enumerate(_items(f.get("signals"))):
            sp = path + ("signals", si)
            if (sl := rng(sp)) is None:
                continue
            rs = model(sp)
            sub = ""
            if isinstance(rs, M.Signal):
                bits = occupied_bits(rs.start_bit or 0, rs.bit_length or 1, rs.byte_order == "big_endian")
                lo, hi = min(bits), max(bits)
                sub = str(lo) if lo == hi else f"{lo}–{hi}"
            snode = {"kind": "signal", "label": display_name(s, lang), "ident": name_of(s), "description": sub,
                     "children": [], **sl}
            for fi, fl in enumerate(_items(s.get("flags"))):
                if (fll := rng(sp + ("flags", fi))) is not None:
                    snode["children"].append({"kind": "flag", "label": name_of(fl), "ident": name_of(fl),
                                              "description": _("bit {bit}", bit=fl.get("bit")),
                                              "children": [], **fll})
            node["children"].append(snode)
        for ei, e in enumerate(_items(f.get("sdo"))):
            if (el := rng(path + ("sdo", ei))) is not None:
                node["children"].append({"kind": "sdo", "label": name_of(e), "ident": name_of(e),
                                         "description": f"{_hexw(e.get('index'), 4)}:{e.get('subindex', 0)}",
                                         "children": [], **el})
        return node

    out = []
    for bi, bus in enumerate(_items(buses)):
        bp = ("buses", bi)
        if (bl := rng(bp)) is None:
            continue
        bnode = {"kind": "bus", "label": display_name(bus, lang), "ident": name_of(bus), "description": "",
                 "children": [], **bl}
        for fi, f in enumerate(_items(bus.get("frames"))):
            if (fn := frame_node(f, bp + ("frames", fi))) is not None:
                bnode["children"].append(fn)
        mbus = model(bp)
        devices = _items(bus.get("devices"))
        for di, d in enumerate(devices):
            dp = bp + ("devices", di)
            if (dl := rng(dp)) is None:
                continue
            sub = (_hexw(d["node_id"], 2) if isinstance(d.get("node_id"), int)
                   else f"SA {_hexw(d['address'], 2)}" if isinstance(d.get("address"), int) else "")
            dnode = {"kind": "device", "label": display_name(d, lang), "ident": name_of(d), "description": sub,
                     "children": [], **dl}
            for fi, f in enumerate(_items(d.get("frames"))):
                if (fn := frame_node(f, dp + ("frames", fi))) is not None:
                    dnode["children"].append(fn)
            # Frames of other devices that the device receives: links after its own; the frame's title may
            # not tell whose it is, so the link's label names the sender
            for rf in mbus.all_frames() if isinstance(mbus, M.Bus) else []:
                own = rf.device is not None and rf.device.name == d.get("name")
                if own or d.get("name") not in rf.receivers or (loc := rng(rf._path)) is None:
                    continue
                sender = next((x for x in devices if x.get("name") == rf.sender_name), None)
                sender_label = device_label(sender, lang) if sender else ""
                frame = raw_at_path(raw, rf._path)
                title = display_name(frame if isinstance(frame, dict) else {"name": rf.name}, lang)
                dnode["children"].append({
                    "kind": "frame", "label": f"{sender_label} · {title}" if sender_label else title,
                    "ident": rf.name, "dir": "rx", "from": sender_label or rf.sender_name or "",
                    "description": _hex(rf.can_id, rf.extended) if rf.can_id is not None else "",
                    "children": [], **loc})
            bnode["children"].append(dnode)
        out.append(bnode)
    return out


def raw_at_path(raw, path: Path_):
    for el in path:
        try:
            raw = raw[el]
        except (KeyError, IndexError, TypeError):
            return None
    return raw


def _items(v) -> list[dict]:
    return [x if isinstance(x, dict) else {} for x in v] if isinstance(v, list) else []


# --------------------------------------------------------------------------- #
# Finding the model by path
# --------------------------------------------------------------------------- #


def _model_of(annotation) -> type[BaseModel] | None:
    """Model class inside an annotation like ``X | None``, ``list[X]``, ``dict[int, X]``."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in typing.get_args(annotation):
        found = _model_of(arg)
        if found is not None:
            return found
    return None


def model_for(path: Path_) -> type[BaseModel] | None:
    """Model class of a node by its path in the YAML (list indices are skipped)."""
    cls: type[BaseModel] | None = MapCan
    for el in path:
        if isinstance(el, int):
            continue
        if cls is None or el not in cls.model_fields:
            return None
        cls = _model_of(cls.model_fields[el].annotation)
    return cls


def _literals(annotation) -> list:
    if typing.get_origin(annotation) is typing.Literal:
        return list(typing.get_args(annotation))
    out = []
    for arg in typing.get_args(annotation):
        out.extend(v for v in _literals(arg) if v not in out)
    return out


def enum_choices() -> dict[str, list[str]]:
    """YAML key → allowed string values (from the Literal annotations of all models)."""
    out: dict[str, list[str]] = {}
    for obj in vars(M).values():
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == M.__name__:
            for name, f in obj.model_fields.items():
                vals = [v for v in _literals(f.annotation) if isinstance(v, str)]
                if vals:
                    out.setdefault(name, [])
                    out[name].extend(v for v in vals if v not in out[name])
    return out


# --------------------------------------------------------------------------- #
# Hover
# --------------------------------------------------------------------------- #


def _key_at(line: str, col: int) -> tuple[str, int] | None:
    for m in _KEY.finditer(line):
        if m.start(1) <= col <= m.end(1):
            return m.group(1), m.end()
    return None


def _owner(path: Path_, kind: str) -> Path_ | None:
    """The nearest ancestor that is an item of a ``signals``/``frames`` list."""
    for i in range(len(path) - 1, 0, -1):
        if path[i - 1] == kind and isinstance(path[i], int):
            return path[: i + 1]
    return None


def _find(cmap: MapCan, path: Path_):
    obj = cmap
    for el in path:
        obj = obj[el] if isinstance(el, int) else getattr(obj, el, None)
        if obj is None:
            return None
    return obj


def hover(a: Analysis, pos: Pos) -> str | None:
    line, col = pos
    if line >= len(a.lines):
        return None
    key = _key_at(a.lines[line], col)
    if key:
        doc = _field_doc(a, key[0], (line, key[1]))
        if doc:
            return doc
    if a.map is None:
        return None
    path = a.path_at(pos)
    sig_path, frame_path = _owner(path, "signals"), _owner(path, "frames")
    frame = _find(a.map, frame_path) if frame_path else None
    if sig_path:
        sig = _find(a.map, sig_path)
        if sig is not None:
            return signal_markdown(sig)
    if frame is not None:
        return frame_markdown(frame)
    return None


def _field_doc(a: Analysis, key: str, after: Pos) -> str | None:
    """Description of the model field for the key whose value starts after ``after``."""
    best = None
    for p, n in a.nodes.items():
        if p and p[-1] == key and n.start >= after and (best is None or n.start < a.nodes[best].start):
            best = p
    if best is None:
        return None
    cls = model_for(best[:-1])
    if cls is None or key not in cls.model_fields:
        return None
    desc = cls.model_fields[key].description
    return f"**{key}** — {_(desc)}" if desc else None


def _hex(v: int, extended: bool) -> str:
    return f"0x{v:08X}" if extended else f"0x{v:03X}"


def signal_bits(sig: M.Signal) -> str:
    start, length = sig.start_bit or 0, sig.bit_length or 1
    if sig.byte_order == "big_endian":
        return _("bits {msb}…{lsb} (BE)", msb=msb_position(start, length, True), lsb=start)
    if length == 1:
        return _("bit {bit}", bit=start)
    return _("bits {lo}–{hi}", lo=start, hi=start + length - 1)


def signal_markdown(sig: M.Signal) -> str:
    out = [f"**{sig.name}** · `{sig.encoding}` · {signal_bits(sig)} · {sig.bit_length} bit"]
    desc = M.text(sig.description, "en")
    if desc:
        out.append(desc)
    facts = []
    if sig.signed:
        facts.append("signed")
    if sig.factor != 1 or sig.offset != 0:
        facts.append(f"phys = raw × {sig.factor:g} + {sig.offset:g}")
    if sig.unit:
        facts.append(_("unit: {unit}", unit=sig.unit))
    if sig.min is not None or sig.max is not None:
        lo = "…" if sig.min is None else f"{sig.min:g}"
        hi = "…" if sig.max is None else f"{sig.max:g}"
        facts.append(_("range: {lo} … {hi}", lo=lo, hi=hi))
    if sig.mux_values is not None:
        facts.append("mux = " + ", ".join(str(v) for v in sig.mux_values))
    if facts:
        out.append(" · ".join(facts))
    values = enum_entries(sig.values)
    if values:
        fmt = (lambda v: f"0x{v:X}") if sig.value_format == "hex" else str
        out.append("| " + _("Value") + " | " + _("Name") + " |\n|---:|---|\n"
                   + "\n".join(f"| {fmt(k)} | {v.name} |" for k, v in values))
    if sig.flags:
        out.append("| " + _("Bit") + " | " + _("Flag") + " |\n|---:|---|\n"
                   + "\n".join(f"| {f.bit if f.bit_length == 1 else f'{f.bit}–{f.bit + f.bit_length - 1}'} "
                               f"| {f.name} |" for f in sig.flags))
    return "\n\n".join(out)


def frame_markdown(frame: M.Frame) -> str:
    head = f"**{frame.name}**"
    if frame.can_id is not None:
        head += f" · `{_hex(frame.can_id, frame.extended)}`" + (" ext" if frame.extended else "")
    head += " · " + _("length {n}", n=frame.length)
    out = [head]
    facts = []
    if frame.mode == "cyclic":
        facts.append(_("cycle {ms} ms", ms=frame.cycle_ms))
    elif frame.mode == "cyclic_event":
        facts.append(_("cycle {ms} ms and on event", ms=frame.cycle_ms))
    if frame.inhibit_ms is not None:
        facts.append(_("min. interval {ms} ms", ms=fmt_num(frame.inhibit_ms)))
    if frame.sender_name or frame.receiver_names:
        facts.append(f"{frame.sender_name or '—'} → {', '.join(frame.receiver_names) or '—'}")
    if facts:
        out.append(" · ".join(facts))
    layout = frame_layout(frame)
    if layout:
        out.append(layout)
    return "\n\n".join(out)


def frame_layout(frame: M.Frame) -> str:
    """Bit map of a frame as a markdown table: rows are bytes, columns are bits 7…0."""
    sigs = frame.layout
    if not sigs or frame.length == 0:
        return ""
    cells: dict[int, list[int]] = {}
    for i, s in enumerate(sigs, 1):
        for b in occupied_bits(s.start_bit or 0, s.bit_length or 1, s.byte_order == "big_endian"):
            cells.setdefault(b, []).append(i)
    rows = ["| " + _("Byte") + " | " + " | ".join(str(b) for b in range(7, -1, -1)) + " |",
            "|---:|" + ":-:|" * 8]
    for byte in range(frame.length):
        row = [",".join(map(str, cells.get(byte * 8 + bit, []))) or "·" for bit in range(7, -1, -1)]
        rows.append(f"| {byte} | " + " | ".join(row) + " |")
    legend = "\n".join(f"{i}. `{s.name}` — {signal_bits(s)}" for i, s in enumerate(sigs, 1))
    return "\n".join(rows) + "\n\n" + legend


# --------------------------------------------------------------------------- #
# Inlay hints
# --------------------------------------------------------------------------- #


@dataclass
class Hint:
    pos: Pos
    label: str


def inlay_hints(a: Analysis) -> list[Hint]:
    """Computed values next to the names: IDs of frames without an explicit ``id``, and bits of signals."""
    if a.map is None:
        return []
    hints: list[Hint] = []

    def after_name(path: Path_) -> Pos | None:
        n = a.nodes.get(path + ("name",))
        return a.token_end(n.start) if n else None

    for bus in a.map.buses:
        for frame in bus.all_frames():
            if frame.id is None and frame.can_id is not None and (pos := after_name(frame._path)):
                hints.append(Hint(pos, f"→ {_hex(frame.can_id, frame.extended)}"))
            for sig in frame.signals:
                if pos := after_name(sig._path):
                    hints.append(Hint(pos, signal_bits(sig)))
    return hints


# --------------------------------------------------------------------------- #
# Completion of values
# --------------------------------------------------------------------------- #

# Snippets of list items: label, description, text with indents relative to "-".
SNIPPET_CTX = re.compile(r"^\s*(-\s+)([A-Za-z_]*)$")
SNIPPETS = [
    ("device", "mapcan device",
     "- name: ${1:device}\n  node_id: ${2:0x01}\n  frames:\n    - name: ${3:frame}\n      canopen: ${4:pdo_tx1}\n"
     "      cycle_ms: ${5:100}\n      signals: []"),
    ("frame", "mapcan frame",
     "- name: ${1:frame}\n  id: ${2:0x100}\n  cycle_ms: ${3:100}\n  receivers: [$4]\n  signals:\n"
     "    - name: ${5:signal}\n      byte: ${6:0}"),
    ("signal", "mapcan signal",
     "- name: ${1:signal}\n  description: ${2:Description}\n  byte: ${3:0}"),
    ("signal enum", "mapcan signal with a value table",
     "- name: ${1:state}\n  description: ${2:State}\n  byte: ${3:0}\n  values:\n    0: ${4:OFF}\n    1: ${5:ON}"),
    ("signal quantity", "mapcan physical quantity",
     "- name: ${1:value}\n  description: ${2:Value}\n  byte: ${3:0}\n  byte_length: ${4:2}\n"
     "  factor: ${5:0.1}\n  unit: ${6:V}\n  min: ${7:0}\n  max: ${8:100}"),
    ("signal flags", "mapcan bit field",
     "- name: ${1:status}\n  description: ${2:Status}\n  byte: ${3:0}\n  flags:\n"
     "    - {bit: 0, name: ${4:ready}}\n    - {bit: 1, name: ${5:fault}}"),
]

_VALUE_CTX = re.compile(r"(?:^|[\s{,])([A-Za-z_]\w*)\s*:\s*([^\s,{}\[\]]*)$")
_LIST_CTX = re.compile(r"(?:^|[\s{,])(receivers)\s*:\s*\[[^\]]*?([^\s,\[]*)$")
_ITEM_CTX = re.compile(r"^\s*-\s+([^\s,]*)$")
DEVICE_KEYS = ("sender", "receivers")


def device_names(a: Analysis | None) -> list[str]:
    """Names of the devices of all buses from the raw YAML of the last analysis."""
    out: list[str] = []
    raw = a.result.raw if a else None
    buses = raw.get("buses") if isinstance(raw, dict) else None
    for bus in buses if isinstance(buses, list) else []:
        devices = bus.get("devices") if isinstance(bus, dict) else None
        for dev in devices if isinstance(devices, list) else []:
            name = dev.get("name") if isinstance(dev, dict) else None
            if isinstance(name, str) and name not in out:
                out.append(name)
    return out


def completions(text: str, pos: Pos, last: Analysis | None) -> tuple[str, list[str]] | None:
    """(key, options) for the value under the cursor, or None.

    ``last`` is the last analysis of the document: the device names come from it even if
    the current text does not parse yet.
    """
    lines = text.splitlines()
    line, col = pos
    if line >= len(lines) + 1:
        return None
    before = (lines[line] if line < len(lines) else "")[:col]
    if m := _LIST_CTX.search(before):
        return m.group(1), device_names(last)
    if m := _VALUE_CTX.search(before):
        key = m.group(1)
        if key in DEVICE_KEYS:
            return key, device_names(last)
        choices = enum_choices().get(key)
        return (key, choices) if choices else None
    if _ITEM_CTX.match(before):
        # An item of the block list "receivers:" on one of the lines above
        for prev in reversed(lines[:line]):
            stripped = prev.strip()
            if stripped.startswith("- "):
                continue
            if re.match(r"^receivers\s*:\s*$", stripped):
                return "receivers", device_names(last)
            break
    return None
