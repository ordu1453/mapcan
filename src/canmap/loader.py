"""Загрузка YAML с сохранением позиций узлов и построение модели."""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError

from .diagnostics import Diagnostic, Report
from .model import CanMap
from .resolve import resolve

# Ключи, значения которых обязаны быть числами.
NUMERIC_KEYS = {
    "factor", "offset", "min", "max", "id", "node_id", "start_bit", "bit_length",
    "byte", "bit", "byte_length", "dlc", "cycle_ms", "bitrate", "command",
    "index", "subindex", "mux",
}
_COMMA_NUMBER = re.compile(r"^\s*[+-]?\d+,\d+\s*$")
_CYR_HEX = re.compile(r"^\s*0[хХ]([0-9a-fA-F]+)\s*$")  # кириллическая «х»
_HEX_STR = re.compile(r"^\s*0[xX]([0-9a-fA-F]+)\s*$")


Path_ = tuple


@dataclass
class SourceMap:
    """Позиции узлов YAML: путь → (строка, колонка), 1-based."""

    file: str | None
    positions: dict[Path_, tuple[int, int]] = field(default_factory=dict)

    def locate(self, path: Path_) -> tuple[int | None, int | None]:
        """Позиция ближайшего существующего узла для (возможно, неточного) пути."""
        cur: tuple = ()
        for el in path:
            if cur + (el,) in self.positions:
                cur = cur + (el,)
        pos = self.positions.get(cur)
        return pos if pos else (None, None)

    def diag(self, level, code, message, path: Path_ = ()) -> Diagnostic:
        line, col = self.locate(path)
        return Diagnostic(level, code, message, self.file, line, col, format_path(path), list(path))


def format_path(path: Path_) -> str:
    out = ""
    for el in path:
        if isinstance(el, int):
            out += f"[{el}]"
        else:
            out += ("." if out else "") + str(el)
    return out


@dataclass
class LoadResult:
    map: CanMap | None
    report: Report
    source: SourceMap
    raw: Any = None  # ruamel-документ (для сохранения с комментариями)


def _plain(node, path: Path_, src: SourceMap, report: Report, parent_key=None):
    """ruamel-узел → обычные dict/list/скаляры + запись позиций + мягкие исправления."""
    if isinstance(node, CommentedMap):
        out = {}
        for k in node:
            key = _plain_scalar(k)
            if parent_key == "values":
                key = _fix_number(key, path + (key,), src, report, is_key=True)
            try:
                line, col = node.lc.value(k)
                src.positions[path + (key,)] = (line + 1, col + 1)
            except (KeyError, TypeError):
                pass
            out[key] = _plain(node[k], path + (key,), src, report, parent_key=key)
        return out
    if isinstance(node, CommentedSeq):
        out = []
        for i, item in enumerate(node):
            try:
                line, col = node.lc.item(i)
                src.positions[path + (i,)] = (line + 1, col + 1)
            except (KeyError, TypeError):
                pass
            out.append(_plain(item, path + (i,), src, report, parent_key=parent_key))
        return out
    value = _plain_scalar(node)
    if parent_key in NUMERIC_KEYS:
        value = _fix_number(value, path, src, report)
    return value


def _plain_scalar(v):
    if isinstance(v, bool):
        return bool(v)
    if isinstance(v, int):
        return int(v)
    if isinstance(v, float):
        return float(v)
    if isinstance(v, _dt.datetime):
        return v.date() if (v.hour, v.minute, v.second) == (0, 0, 0) else v
    if isinstance(v, str):
        return str(v)
    return v


def _fix_number(value, path, src: SourceMap, report: Report, is_key=False):
    """Распознать типичные ошибки записи чисел, сообщить и исправить для продолжения проверки."""
    if not isinstance(value, str):
        return value
    what = "ключ" if is_key else "значение"
    if _COMMA_NUMBER.match(value):
        fixed = float(value.replace(",", "."))
        report.add(src.diag(
            "error", "number-comma",
            f"{what} {value!r}: дробная часть отделена запятой, нужно {fixed!r}", path))
        return fixed
    m = _CYR_HEX.match(value)
    if m:
        report.add(src.diag(
            "error", "number-cyrillic-x",
            f"{what} {value!r}: в префиксе 0x используется кириллическая «х»", path))
        return int(m.group(1), 16)
    m = _HEX_STR.match(value)
    if m:
        report.add(src.diag(
            "warning", "number-quoted",
            f"{what} {value!r} записано строкой; уберите кавычки", path))
        return int(m.group(1), 16)
    return value


def _pydantic_messages(err: ValidationError, src: SourceMap, report: Report) -> None:
    seen = set()
    for e in err.errors():
        loc = tuple(e["loc"])
        # Для union pydantic добавляет имена вариантов в путь — убираем их.
        clean = tuple(x for x in loc if isinstance(x, int) or x in _known_keys(src))
        msg = e["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        if e["type"] == "extra_forbidden":
            msg = f"неизвестное поле {loc[-1]!r}"
        elif e["type"] == "missing":
            msg = f"отсутствует обязательное поле {loc[-1]!r}"
        key = (clean, msg)
        if key in seen:
            continue
        seen.add(key)
        report.add(src.diag("error", "schema", msg, clean if e["type"] != "missing" else clean))


_KEYS_CACHE: dict[int, set] = {}


def _known_keys(src: SourceMap) -> set:
    k = id(src)
    if k not in _KEYS_CACHE:
        _KEYS_CACHE[k] = {el for p in src.positions for el in p if not isinstance(el, int)}
    return _KEYS_CACHE[k]


def _make_yaml() -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    return y


def loads(text: str, filename: str | None = None, base_dir: str | Path | None = None) -> LoadResult:
    report = Report()
    src = SourceMap(filename)
    try:
        raw = _make_yaml().load(text)
    except MarkedYAMLError as e:
        mark = e.problem_mark or e.context_mark
        line = mark.line + 1 if mark else None
        col = mark.column + 1 if mark else None
        problem = e.problem or str(e)
        if "duplicate key" in str(e):
            problem = "повторяющийся ключ: " + (e.problem or "")
        report.add(Diagnostic("error", "yaml", problem.strip(), filename, line, col))
        return LoadResult(None, report, src)
    if raw is None:
        report.add(Diagnostic("error", "yaml", "пустой файл", filename, 1, 1))
        return LoadResult(None, report, src, raw)

    data = _plain(raw, (), src, report)
    src.positions.setdefault((), (1, 1))
    try:
        cmap = CanMap.model_validate(data)
    except ValidationError as err:
        _pydantic_messages(err, src, report)
        return LoadResult(None, report, src, raw)
    cmap._source = filename
    if base_dir is not None:
        cmap._base_dir = Path(base_dir)
    elif filename:
        cmap._base_dir = Path(filename).resolve().parent
    resolve(cmap)
    return LoadResult(cmap, report, src, raw)


def load(path: str | Path) -> LoadResult:
    p = Path(path)
    return loads(p.read_text(encoding="utf-8"), str(p))
