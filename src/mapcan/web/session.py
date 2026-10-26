"""State of the edited map: text, ruamel document, undo/redo, syncing with the disk."""

from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ruamel.yaml.error import YAMLError

from .. import bits as B
from ..diagnostics import Report
from ..docmodel import PALETTE
from ..i18n import _
from ..loader import LoadResult, loads, map_of
from ..model import Frame, MapCan, enum_entries
from ..units import UNITS
from ..upgrade import upgrade_data
from ..validate import bus_load_note, bus_load_text, check
from .devicefile import device_file_target, device_file_text, exclude_ops, include_ops, named_after_file, part_is_empty
from .yamlops import OpError, apply_ops, device_rename_ops, dump, make_yaml, merge_text, plain

HISTORY_LIMIT = 200


class ConflictError(RuntimeError):
    """The file on disk was changed outside."""


class ReadOnlyError(RuntimeError):
    pass


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _write(path: Path, data: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data.encode("utf-8"))
    tmp.replace(path)


class _Part:
    """A file included by the map, edited together with it (#49). Its ``text`` is None while it does not exist:
    a file made by the editor (a device in a file of its own, #136) is not on the disk until saved, and one left
    empty by a delete is removed from the disk by Save."""

    def __init__(self, path: Path, created: bool = False):
        self.path = path
        if created:
            self.newline = "\n"
            self.text: str | None = None
            self.saved_text: str | None = None
            self.disk_hash: str | None = None
            return
        raw = path.read_bytes().decode("utf-8")
        self.newline = "\r\n" if "\r\n" in raw else "\n"
        self.text = self.saved_text = raw.replace("\r\n", "\n")
        self.disk_hash = _hash(self.text)

    @property
    def created(self) -> bool:
        """Made by the editor and not saved yet."""
        return self.disk_hash is None

    @property
    def dirty(self) -> bool:
        return self.text != self.saved_text

    def write(self) -> None:
        if self.text is None:
            self.path.unlink(missing_ok=True)
            self.saved_text = self.disk_hash = None
            return
        if self.created:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        _write(self.path, self.text.replace("\n", self.newline))
        self.saved_text = self.text
        self.disk_hash = _hash(self.text)

    def disk_changed(self) -> bool:
        if self.created:
            return self.path.exists()        # made by another program meanwhile
        try:
            return _hash(self.path.read_bytes().decode("utf-8").replace("\r\n", "\n")) != self.disk_hash
        except (OSError, UnicodeDecodeError):
            return True


# The state of all files for undo: the map's text and the texts of the included files (resolved path → text)
Snapshot = tuple[str, dict[str, str]]


class EditorSession:
    """The edited map and the files it includes: one undo history, and saving writes every changed file."""

    def __init__(self, path: str | Path, readonly: bool = False):
        # A file included by a map opens that map: the file's nodes are edited in it, in their file
        self.opened = Path(path).resolve()
        self.path = map_of(self.opened)
        self.readonly = readonly
        self.lock = threading.RLock()
        self.version = 0
        self.undo_stack: list[Snapshot] = []
        self.redo_stack: list[Snapshot] = []
        # The file (None: the map) and its text before a series of edits in the YAML tab while typing
        self._live_base: tuple[str | None, str] | None = None
        self._result: LoadResult | None = None
        self._report = None
        self._last_check: tuple | None = None      # (text and included files, result, report) of check_text
        self.parts: dict[str, _Part] = {}       # included files read so far, by resolved path
        self.reload()

    # ------------------------------------------------------------------ disk

    def _read_disk(self) -> str:
        raw = self.path.read_bytes().decode("utf-8")
        self.newline = "\r\n" if "\r\n" in raw else "\n"
        return raw.replace("\r\n", "\n")

    def _read_part(self, path: str) -> str | None:
        """Text of an included file for the loader: the edited one, read from the disk the first time."""
        part = self.parts.get(path)
        if part is None:
            try:
                part = self.parts[path] = _Part(Path(path))
            except (OSError, UnicodeDecodeError):
                return None
        return part.text

    def _load(self, text: str, override: tuple[str, str] | None = None) -> LoadResult:
        """Load the map; ``override``: an included file (its key in parts) read with another text."""
        def read(path: str) -> str | None:
            return override[1] if override is not None and path == override[0] else self._read_part(path)
        return loads(text, str(self.path.name), self.path.parent, read=read)

    def _parts_key(self, override: tuple[str, str] | None = None) -> tuple:
        return tuple((p, override[1] if override is not None and p == override[0] else part.text)
                     for p, part in sorted(self.parts.items()))

    def part_key(self, file: str) -> str:
        """An included file by its path relative to the map (as the state names it): its key in parts."""
        for k, part in self.parts.items():
            if part.text is not None and self._rel(part.path) == file:
                return k
        raise OpError(_("the included file {file} cannot be read", file=file))

    def _checked(self, text: str) -> tuple[LoadResult, Report]:
        """The load and validation of a text: those of the live validation of the same text (and the same
        included files) are reused, so typing in the YAML tab analyses each pause once, not twice."""
        last = self._last_check
        key = (text, self._parts_key())
        if last is not None and last[0] == key:
            return last[1], last[2]
        result = self._load(text)
        return result, check(result)

    def disk_changed(self) -> bool:
        """The map or an included file was changed outside since the last load/save."""
        try:
            main = _hash(self.path.read_bytes().decode("utf-8").replace("\r\n", "\n")) != self.disk_hash
        except (OSError, UnicodeDecodeError):
            main = True
        return main or any(p.disk_changed() for p in self.parts.values())

    @property
    def dirty(self) -> bool:
        return self.text != self.saved_text or any(p.dirty for p in self.parts.values())

    def part_paths(self) -> list[Path]:
        """The files included by the map (those the current text includes)."""
        if self._result is None:
            return []
        return [Path(f).resolve() for _i, f in self._result.source.includes]

    def reload(self) -> None:
        with self.lock:
            text = self._read_disk()
            self.disk_hash = _hash(text)
            self.saved_text = text
            self.parts = {}
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._live_base = None
            self._set_text(text)

    def save(self, force: bool = False) -> None:
        """Write the map and every included file with unsaved edits."""
        with self.lock:
            self._check_writable()
            if self.disk_changed() and not force:
                raise ConflictError(_("the file was changed on disk by another program"))
            for part in self.parts.values():
                if part.dirty:
                    part.write()
            _write(self.path, self.text.replace("\n", self.newline))
            self.disk_hash = _hash(self.text)
            self.saved_text = self.text
            self.version += 1

    def save_as(self, path: str | Path, overwrite: bool = False) -> None:
        """Save the current text to another file and go on working with it."""
        with self.lock:
            self._check_writable()
            target = Path(path).resolve()
            if target.exists() and not overwrite and target != self.path:
                raise FileExistsError(_("file already exists: {path}", path=target))
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
            except FileExistsError as e:
                # A file stands where a folder of the path should be: not "the file already exists"
                raise NotADirectoryError(e.errno, e.strerror, e.filename) from e
            target.write_bytes(self.text.replace("\n", self.newline).encode("utf-8"))
            # The included files stay where they are: their unsaved edits are written there
            for part in self.parts.values():
                if part.dirty:
                    part.write()
            self.path = target
            self.disk_hash = _hash(self.text)
            self.saved_text = self.text
            self._result = self._load(self.text)
            self._report = check(self._result)
            self.version += 1

    # ------------------------------------------------------------------ editing

    def _check_writable(self) -> None:
        if self.readonly:
            raise ReadOnlyError(_("the editor is running in read-only mode"))

    def _set_text(self, text: str) -> None:
        """Take a text: parse it into a ruamel document and redo the validation."""
        self.text = text
        self.yaml = make_yaml(text)
        try:
            self.doc = self.yaml.load(text)
        except YAMLError:
            self.doc = None           # syntax error: only the YAML tab is available
        self._result, self._report = self._checked(text)
        self.version += 1

    def check_text(self, text: str, file: str | None = None) -> list[dict]:
        """Validate a text without applying it (live validation in the YAML tab). ``file``: the text is that of
        an included file (relative to the map), with the map's current text."""
        text = text.replace("\r\n", "\n")
        with self.lock:
            override = (self.part_key(file), text) if file is not None else None
            main = self.text if override is not None else text
            key = (main, self._parts_key(override))
            result = self._load(main, override)
        report = check(result)
        self._last_check = (key, result, report)
        return self._diag_dicts(result, report)

    def _diag_dicts(self, result: LoadResult, report: Report) -> list[dict]:
        """Messages for the editor, on the include line in the map; one about an included file also has its place
        in that file (``part``: the file relative to the map, line, column) for the YAML tab of that file."""
        out = []
        for d in report.sorted():
            item = asdict(result.source.in_main_file(d))
            if d.file is not None and d.file != result.source.file:
                item["part"] = {"file": self._rel(d.file), "line": d.line, "column": d.column}
            out.append(item)
        return out

    def recheck(self) -> None:
        """Rebuild the validation messages (after the interface language changed)."""
        with self.lock:
            self._result = self._load(self.text)
            self._report = check(self._result)
            self.version += 1

    def _snapshot(self) -> Snapshot:
        return self.text, {k: p.text for k, p in self.parts.items()}

    def _restore(self, snap: Snapshot) -> None:
        text, parts = snap
        for k, part in self.parts.items():
            if k in parts:
                part.text = parts[k]
            elif part.created:
                part.text = None         # a file made after this state: it is not there again
        self._set_text(text)

    def _commit(self, new_text: str, new_parts: dict[str, str | None] | None = None) -> bool:
        """A new state of the map (and of included files): one undo step."""
        self._live_base = None
        changed_parts = {k: t for k, t in (new_parts or {}).items() if self.parts[k].text != t}
        if new_text == self.text and not changed_parts:
            return False
        self.undo_stack.append(self._snapshot())
        del self.undo_stack[:-HISTORY_LIMIT]
        self.redo_stack.clear()
        for k, t in changed_parts.items():
            self.parts[k].text = t
        self._set_text(new_text)
        return True

    def _route(self, ops: list[dict]) -> dict[str | None, list[dict]]:
        """Operations by the file they change (None: the map), with the paths of that file. A node of an included
        file has another path there: the second device of a bus may be the first of the included file."""
        src = self._result.source if self._result is not None else None
        out: dict[str | None, list[dict]] = {}
        for o in ops:
            path = o.get("path")
            target, local = None, path
            if src is not None and isinstance(path, list):
                file, lp = src.origin(tuple(int(x) if isinstance(x, str) and x.isdigit() else x for x in path))
                if file is not None and file != src.file:
                    target, local = str(Path(file).resolve()), list(lp)
            out.setdefault(target, []).append({**o, "path": local} if target else o)
        return out

    def _apply_to(self, text: str, ops: list[dict]) -> str:
        """The text with the operations applied (through its ruamel document, keeping the rest of the text)."""
        y = make_yaml(text)
        doc = y.load(text)
        canon_old = dump(y, doc)
        apply_ops(doc, ops)
        return merge_text(text, canon_old, dump(y, doc))

    def apply(self, ops: list[dict]) -> bool:
        """Apply operations atomically: to the map and to the included files whose nodes they change.
        Returns True if a text changed."""
        with self.lock:
            self._check_writable()
            if self.doc is None:
                raise OpError(_("the YAML has a syntax error; fix the text in the YAML tab"))
            routed = self._route(ops)
            new_parts = {}
            for file, part_ops in list(routed.items()):
                if file is None:
                    continue
                if file not in self.parts:
                    raise OpError(_("the included file {file} cannot be read", file=Path(file).name))
                new_parts[file] = self._apply_to(self.parts[file].text, part_ops)
                if any(o.get("op") == "remove" for o in part_ops) and part_is_empty(new_parts[file]):
                    # The file adds nothing to the map any more (its device was deleted): it goes, with its line of
                    # include
                    new_parts[file] = None
                    routed.setdefault(None, []).extend(
                        exclude_ops(plain(self.doc).get("include"), self.path, Path(file)))
            new_text = self.text
            if routed.get(None):
                canon_old = dump(self.yaml, self.doc)
                try:
                    apply_ops(self.doc, routed[None])
                    canon_new = dump(self.yaml, self.doc)
                except Exception:
                    self.doc = self.yaml.load(self.text)     # roll back
                    raise
                new_text = merge_text(self.text, canon_old, canon_new)
            return self._commit(new_text, new_parts)

    def add_device_file(self, bus_path: list, device: dict[str, Any], file: str) -> None:
        """A new device of the bus at ``bus_path`` in a file of its own (#136): the file is made with the device
        and added to ``include`` of the map, as one undo step; Save writes both."""
        with self.lock:
            self._check_writable()
            if self.doc is None:
                raise OpError(_("the YAML has a syntax error; fix the text in the YAML tab"))
            data = self._result.merged if self._result.merged is not None else self._result.raw
            buses = data.get("buses") if isinstance(data, dict) else None
            bus = (buses[int(bus_path[1])] if len(bus_path) == 2 and bus_path[0] == "buses"
                   and isinstance(buses, list) and 0 <= int(bus_path[1]) < len(buses) else None)
            if not isinstance(bus, dict) or not isinstance(bus.get("name"), str):
                raise OpError(_("path not found: {path}", path=bus_path))
            try:
                target, line = device_file_target(self.path, file)
                ops = include_ops(plain(self.doc).get("include"), line)
            except ValueError as e:
                raise OpError(str(e)) from e
            taken = [d.get("name") for d in bus.get("devices") or [] if isinstance(d, dict)]
            device = named_after_file(device, target, taken)
            key = str(target)
            if key in self.parts and self.parts[key].text is not None:
                raise OpError(_("file already exists: {path}", path=target))
            canon_old = dump(self.yaml, self.doc)
            try:
                apply_ops(self.doc, ops)
                canon_new = dump(self.yaml, self.doc)
            except Exception:
                self.doc = self.yaml.load(self.text)     # roll back
                raise
            self.parts.setdefault(key, _Part(target, created=True))
            self._commit(merge_text(self.text, canon_old, canon_new),
                         {key: device_file_text(self.path, target, bus["name"], device)})

    def _carry_renames(self, base: str, text: str) -> str:
        """A device renamed in the text is carried over to sender/receivers of the frames, as when edited in the
        form."""
        y = make_yaml(text)
        try:
            old = plain(make_yaml(base).load(base))
            doc = y.load(text)
        except YAMLError:
            return text
        ops = device_rename_ops(old, plain(doc))
        if not ops:
            return text
        canon_old = dump(y, doc)
        try:
            apply_ops(doc, ops)
        except OpError:
            return text
        return merge_text(text, canon_old, dump(y, doc))

    def set_text(self, text: str, live: bool = False, file: str | None = None) -> bool:
        """Take the text of the YAML tab: of the map, or of the included file ``file`` (relative to the map).

        `live`: an intermediate application while typing; such edits in a row merge into one undo
        step until a normal application or another edit comes. Device renames are counted
        from the text before the series started, so the intermediate names break nothing.
        """
        with self.lock:
            self._check_writable()
            key = self.part_key(file) if file is not None else None
            current = self.text if key is None else self.parts[key].text
            live_base = self._live_base
            self._live_base = None
            # A series goes on only in the same file
            base = live_base[1] if live_base is not None and live_base[0] == key else None
            text = self._carry_renames(current if base is None else base, text.replace("\r\n", "\n"))
            if base is None:
                changed = self._commit(text) if key is None else self._commit(self.text, {key: text})
                if live and changed:
                    self._live_base = (key, current)
                return changed
            if text == base:                     # the series brought the text back: no undo step needed
                self.undo_stack.pop()
            elif live:
                self._live_base = (key, base)
            if text == current:
                return False
            self.redo_stack.clear()
            if key is not None:
                self.parts[key].text = text
                text = self.text
            self._set_text(text)
            return True

    def undo(self) -> bool:
        with self.lock:
            self._check_writable()
            self._live_base = None
            if not self.undo_stack:
                return False
            self.redo_stack.append(self._snapshot())
            self._restore(self.undo_stack.pop())
            return True

    def redo(self) -> bool:
        with self.lock:
            self._check_writable()
            self._live_base = None
            if not self.redo_stack:
                return False
            self.undo_stack.append(self._snapshot())
            self._restore(self.redo_stack.pop())
            return True

    # ------------------------------------------------------------------ reading

    def _included(self) -> dict[str, Any]:
        """Included files (include): the buses together with them (for the tree and the read-only form)
        and the nodes they added, with the file's path relative to the map."""
        merged = self._result.merged if self._result else None
        if not isinstance(merged, dict) or not isinstance(merged.get("buses"), list):
            return {"included_buses": None, "included": [], "parts": {}}
        src = self._result.source
        roots = src.included_roots()
        files = dict.fromkeys(str(Path(f).resolve()) for _i, f in src.includes)
        return {"included_buses": merged["buses"],
                # local: the node's path in its file (the second device of a bus may be the first of the file)
                "included": [{"path": list(p), "file": self._rel(f), "local": list(src.origin(p)[1])}
                             for p, f in sorted(roots, key=lambda r: r[0])],
                # Texts of the included files (relative to the map), for the YAML tab
                "parts": {self._rel(self.parts[k].path): self.parts[k].text for k in files
                          if k in self.parts and self.parts[k].text is not None}}

    def _rel(self, f: str | Path) -> str:
        try:
            return Path(os.path.relpath(f, self.path.parent)).as_posix()
        except ValueError:          # another drive
            return Path(f).name

    @property
    def map(self) -> MapCan | None:
        return self._result.map if self._result else None

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "file": self.path.name,
                "path": str(self.path),
                "version": self.version,
                "dirty": self.dirty,
                # Included files with unsaved edits (paths relative to the map): Save writes them too
                "dirty_files": [self._rel(p.path) for p in self.parts.values() if p.dirty],
                # The included file asked for, when its map was opened in its place
                "opened_part": self._rel(self.opened) if self.opened != self.path else None,
                "readonly": self.readonly,
                "can_undo": bool(self.undo_stack),
                "can_redo": bool(self.redo_stack),
                "disk_changed": self.disk_changed(),
                "text": self.text,
                # Deprecated keys under their current names and the encodings of format version 2: the editors
                # know only those (see upgrade.py)
                "data": upgrade_data(plain(self.doc)) if self.doc is not None else None,
                "resolved": resolved_view(self.map) if self.map else None,
                **self._included(),
                "diagnostics": self._diag_dicts(self._result, self._report),
                "palette": PALETTE,
                "units": UNITS,
            }


# --------------------------------------------------------------------------- resolved


def frame_view(f: Frame) -> dict:
    sigs = []
    explicit = bool(f.signals)
    for i, s in enumerate(f.layout):
        be = s.byte_order == "big_endian"
        occ = B.occupied_bits(s.start_bit, s.bit_length, be)
        flags = []
        for fl in s.flags or []:
            flags.append({"name": fl.name, "bit": fl.bit, "bit_length": fl.bit_length,
                          "occupied": occ[fl.bit: fl.bit + fl.bit_length]})
        sigs.append({
            "index": i if explicit else None,
            "path": list(s._path),
            "name": s.name,
            "encoding": s.encoding,
            "start_bit": s.start_bit,
            "bit_length": s.bit_length,
            "byte_order": s.byte_order,
            "signed": s.signed,
            "multiplexer": s.multiplexer,
            "mux": s.mux_values,
            "occupied": occ,
            "flags": flags,
            "values": [{"value": v, "name": ev.name} for v, ev in enum_entries(s.values)],
            "synthetic": not explicit,
        })
    return {
        "path": list(f._path),
        "name": f.name,
        "can_id": f.can_id,
        "extended": f.extended,
        "length": f.length,
        "type": f.type,
        "direction": f.direction,
        "device": f.device.name if f.device else None,
        "sender": f.sender_name,
        "receivers": f.receiver_names,
        "signals": sigs,
    }


def resolved_view(cmap: MapCan) -> dict:
    frames = []
    for bus in cmap.buses:
        for f in bus.all_frames():
            frames.append(frame_view(f))
    # The estimated load of each bus for the tree ("≥" when frames without a known period are not counted), and
    # its tooltip
    loads = [{"path": list(bus._path), "load": bus_load_text(bus), "note": bus_load_note(bus)} for bus in cmap.buses]
    return {"frames": frames, "buses": loads, "language": cmap.lang}
