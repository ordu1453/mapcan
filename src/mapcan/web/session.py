"""Состояние редактируемой карты: текст, ruamel-документ, undo/redo, синхронизация с диском."""

from __future__ import annotations

import hashlib
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
from ..validate import check
from .yamlops import OpError, apply_ops, dump, make_yaml, merge_text, plain

HISTORY_LIMIT = 200


class ConflictError(RuntimeError):
    """Файл на диске изменён извне."""


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
        self._result: LoadResult | None = None
        self._report = None
        self.reload()

    # ------------------------------------------------------------------ диск

    def _read_disk(self) -> str:
        raw = self.path.read_bytes().decode("utf-8")
        self.newline = "\r\n" if "\r\n" in raw else "\n"
        return raw.replace("\r\n", "\n")

    def disk_changed(self) -> bool:
        """Файл изменён извне с момента последней загрузки/сохранения."""
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
            self._set_text(text)

    def save(self, force: bool = False) -> None:
        with self.lock:
            self._check_writable()
            if self.disk_changed() and not force:
                raise ConflictError(_("файл изменён на диске другой программой"))
            data = self.text.replace("\n", self.newline)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_bytes(data.encode("utf-8"))
            tmp.replace(self.path)
            self.disk_hash = _hash(self.text)
            self.saved_text = self.text
            self.version += 1

    def save_as(self, path: str | Path, overwrite: bool = False) -> None:
        """Сохранить текущий текст в другой файл и продолжить работу с ним."""
        with self.lock:
            self._check_writable()
            target = Path(path).resolve()
            if target.exists() and not overwrite and target != self.path:
                raise FileExistsError(_("файл уже существует: {path}", path=target))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.text.replace("\n", self.newline).encode("utf-8"))
            self.path = target
            self.disk_hash = _hash(self.text)
            self.saved_text = self.text
            self._result = loads(self.text, target.name, target.parent)
            self._report = check(self._result)
            self.version += 1

    # ------------------------------------------------------------------ правка

    def _check_writable(self) -> None:
        if self.readonly:
            raise ReadOnlyError(_("редактор запущен в режиме только для чтения"))

    def _set_text(self, text: str) -> None:
        """Принять текст: разобрать в ruamel-документ и пересчитать проверку."""
        self.text = text
        self.yaml = make_yaml(text)
        try:
            self.doc = self.yaml.load(text)
        except YAMLError:
            self.doc = None           # синтаксическая ошибка: доступна только вкладка YAML
        self._result = loads(text, str(self.path.name), self.path.parent)
        self._report = check(self._result)
        self.version += 1

    def check_text(self, text: str) -> list[dict]:
        """Проверить текст, не применяя его (живая проверка во вкладке YAML)."""
        report = check(loads(text.replace("\r\n", "\n"), str(self.path.name), self.path.parent))
        return [asdict(d) for d in report.sorted()]

    def recheck(self) -> None:
        """Пересобрать сообщения проверки (после смены языка интерфейса)."""
        with self.lock:
            self._result = loads(self.text, str(self.path.name), self.path.parent)
            self._report = check(self._result)
            self.version += 1

    def _commit(self, new_text: str) -> bool:
        if new_text == self.text:
            return False
        self.undo_stack.append(self.text)
        del self.undo_stack[:-HISTORY_LIMIT]
        self.redo_stack.clear()
        self._set_text(new_text)
        return True

    def apply(self, ops: list[dict]) -> bool:
        """Применить операции атомарно. Возвращает True, если текст изменился."""
        with self.lock:
            self._check_writable()
            if self.doc is None:
                raise OpError(_("в YAML синтаксическая ошибка — исправьте текст во вкладке YAML"))
            canon_old = dump(self.yaml, self.doc)
            try:
                apply_ops(self.doc, ops)
                canon_new = dump(self.yaml, self.doc)
            except Exception:
                self.doc = self.yaml.load(self.text)     # откат
                raise
            return self._commit(merge_text(self.text, canon_old, canon_new))

    def set_text(self, text: str) -> bool:
        with self.lock:
            self._check_writable()
            return self._commit(text.replace("\r\n", "\n"))

    def undo(self) -> bool:
        with self.lock:
            self._check_writable()
            if not self.undo_stack:
                return False
            self.redo_stack.append(self.text)
            self._set_text(self.undo_stack.pop())
            return True

    def redo(self) -> bool:
        with self.lock:
            self._check_writable()
            if not self.redo_stack:
                return False
            self.undo_stack.append(self.text)
            self._set_text(self.redo_stack.pop())
            return True

    # ------------------------------------------------------------------ чтение

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
                "data": plain(self.doc) if self.doc is not None else None,
                "resolved": resolved_view(self.map) if self.map else None,
                "diagnostics": [asdict(d) for d in self._report.sorted()],
                "palette": PALETTE,
                "units": UNITS,
            }


# --------------------------------------------------------------------------- resolved


def _frame_view(f: Frame) -> dict:
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
            "kind": s.kind,
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
        "dlc": f.dlc,
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
            frames.append(_frame_view(f))
    return {"frames": frames, "language": cmap.lang}
