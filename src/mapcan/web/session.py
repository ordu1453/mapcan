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
from ..docmodel import PALETTE
from ..i18n import _
from ..loader import LoadResult, loads
from ..model import Frame, MapCan, enum_entries
from ..units import UNITS
from ..upgrade import upgrade_tree
from ..validate import check
from .yamlops import OpError, apply_ops, check_editable, device_rename_ops, dump, make_yaml, merge_text, plain

HISTORY_LIMIT = 200


class ConflictError(RuntimeError):
    """The file on disk was changed outside."""


class ReadOnlyError(RuntimeError):
    pass


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class EditorSession:
    def __init__(self, path: str | Path, readonly: bool = False):
        self.path = Path(path).resolve()
        self.readonly = readonly
        self.lock = threading.RLock()
        self.version = 0
        self.undo_stack: list[str] = []
        self.redo_stack: list[str] = []
        self._live_base: str | None = None     # text before a series of edits in the YAML tab while typing
        self._result: LoadResult | None = None
        self._report = None
        self.reload()

    # ------------------------------------------------------------------ disk

    def _read_disk(self) -> str:
        raw = self.path.read_bytes().decode("utf-8")
        self.newline = "\r\n" if "\r\n" in raw else "\n"
        return raw.replace("\r\n", "\n")

    def disk_changed(self) -> bool:
        """The file was changed outside since the last load/save."""
        try:
            return _hash(self.path.read_bytes().decode("utf-8").replace("\r\n", "\n")) != self.disk_hash
        except (OSError, UnicodeDecodeError):
            return True

    def reload(self) -> None:
        with self.lock:
            text = self._read_disk()
            self.disk_hash = _hash(text)
            self.saved_text = text
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._live_base = None
            self._set_text(text)

    def save(self, force: bool = False) -> None:
        with self.lock:
            self._check_writable()
            if self.disk_changed() and not force:
                raise ConflictError(_("the file was changed on disk by another program"))
            data = self.text.replace("\n", self.newline)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_bytes(data.encode("utf-8"))
            tmp.replace(self.path)
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
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.text.replace("\n", self.newline).encode("utf-8"))
            self.path = target
            self.disk_hash = _hash(self.text)
            self.saved_text = self.text
            self._result = loads(self.text, target.name, target.parent)
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
        self._result = loads(text, str(self.path.name), self.path.parent)
        self._report = check(self._result)
        self.version += 1

    def check_text(self, text: str) -> list[dict]:
        """Validate a text without applying it (live validation in the YAML tab)."""
        result = loads(text.replace("\r\n", "\n"), str(self.path.name), self.path.parent)
        return [asdict(result.source.in_main_file(d)) for d in check(result).sorted()]

    def recheck(self) -> None:
        """Rebuild the validation messages (after the interface language changed)."""
        with self.lock:
            self._result = loads(self.text, str(self.path.name), self.path.parent)
            self._report = check(self._result)
            self.version += 1

    def _commit(self, new_text: str) -> bool:
        self._live_base = None
        if new_text == self.text:
            return False
        self.undo_stack.append(self.text)
        del self.undo_stack[:-HISTORY_LIMIT]
        self.redo_stack.clear()
        self._set_text(new_text)
        return True

    def apply(self, ops: list[dict]) -> bool:
        """Apply operations atomically. Returns True if the text changed."""
        with self.lock:
            self._check_writable()
            if self.doc is None:
                raise OpError(_("the YAML has a syntax error; fix the text in the YAML tab"))
            if self._result is not None:
                check_editable(self._result.source, ops)
            canon_old = dump(self.yaml, self.doc)
            try:
                apply_ops(self.doc, ops)
                canon_new = dump(self.yaml, self.doc)
            except Exception:
                self.doc = self.yaml.load(self.text)     # roll back
                raise
            return self._commit(merge_text(self.text, canon_old, canon_new))

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

    def set_text(self, text: str, live: bool = False) -> bool:
        """Take the text of the YAML tab.

        `live`: an intermediate application while typing; such edits in a row merge into one undo
        step until a normal application or another edit comes. Device renames are counted
        from the text before the series started, so the intermediate names break nothing.
        """
        with self.lock:
            self._check_writable()
            base = self._live_base
            self._live_base = None
            text = self._carry_renames(self.text if base is None else base, text.replace("\r\n", "\n"))
            if base is None:
                changed = self._commit(text)
                if live and changed:
                    self._live_base = self.undo_stack[-1]
                return changed
            if text == base:                     # the series brought the text back: no undo step needed
                self.undo_stack.pop()
            elif live:
                self._live_base = base
            if text == self.text:
                return False
            self.redo_stack.clear()
            self._set_text(text)
            return True

    def undo(self) -> bool:
        with self.lock:
            self._check_writable()
            self._live_base = None
            if not self.undo_stack:
                return False
            self.redo_stack.append(self.text)
            self._set_text(self.undo_stack.pop())
            return True

    def redo(self) -> bool:
        with self.lock:
            self._check_writable()
            self._live_base = None
            if not self.redo_stack:
                return False
            self.undo_stack.append(self.text)
            self._set_text(self.redo_stack.pop())
            return True

    # ------------------------------------------------------------------ reading

    def _included(self) -> dict[str, Any]:
        """Included files (include): the buses together with them (for the tree and the read-only form)
        and the nodes they added, with the file's path relative to the map."""
        merged = self._result.merged if self._result else None
        if not isinstance(merged, dict) or not isinstance(merged.get("buses"), list):
            return {"included_buses": None, "included": []}

        def rel(f: str) -> str:
            try:
                return Path(os.path.relpath(f, self.path.parent)).as_posix()
            except ValueError:          # another drive
                return Path(f).name

        roots = self._result.source.included_roots()
        return {"included_buses": merged["buses"],
                "included": [{"path": list(p), "file": rel(f)} for p, f in sorted(roots, key=lambda r: r[0])]}

    @property
    def map(self) -> MapCan | None:
        return self._result.map if self._result else None

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "file": self.path.name,
                "path": str(self.path),
                "version": self.version,
                "dirty": self.text != self.saved_text,
                "readonly": self.readonly,
                "can_undo": bool(self.undo_stack),
                "can_redo": bool(self.redo_stack),
                "disk_changed": self.disk_changed(),
                "text": self.text,
                # Deprecated keys under their current names: the editors know only those (see upgrade.py)
                "data": upgrade_tree(plain(self.doc)) if self.doc is not None else None,
                "resolved": resolved_view(self.map) if self.map else None,
                **self._included(),
                "diagnostics": [asdict(self._result.source.in_main_file(d)) for d in self._report.sorted()],
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
    return {"frames": frames, "language": cmap.lang}
