"""Загрузка YAML с сохранением позиций узлов и построение модели."""

from __future__ import annotations

import copy
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
from .i18n import _
from .model import MapCan
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
    """Позиции узлов YAML: путь → (строка, колонка), 1-based.

    Узлы из подключённых файлов (include) записаны в ``files``: путь → имя файла, позиция — в нём."""

    file: str | None
    positions: dict[Path_, tuple[int, int]] = field(default_factory=dict)
    files: dict[Path_, str] = field(default_factory=dict)
    includes: list[tuple[int, str]] = field(default_factory=list)   # (номер в include, файл)

    def _nearest(self, path: Path_) -> Path_:
        cur: tuple = ()
        for el in path:
            if cur + (el,) in self.positions:
                cur = cur + (el,)
        return cur

    def locate(self, path: Path_) -> tuple[int | None, int | None]:
        """Позиция ближайшего существующего узла для (возможно, неточного) пути."""
        pos = self.positions.get(self._nearest(path))
        return pos if pos else (None, None)

    def file_of(self, path: Path_) -> str | None:
        """Файл, в котором описан узел: основной или подключённый."""
        return self.files.get(self._nearest(path), self.file)

    def is_included(self, path: Path_) -> bool:
        """Узел описан в подключённом файле (или внутри такого узла)."""
        return any(path[:n] in self.files for n in range(2, len(path) + 1, 2))

    def included_roots(self) -> list[tuple[Path_, str]]:
        """Узлы, целиком добавленные подключёнными файлами: шины, а к шинам основного — устройства и кадры."""
        return [(p, f) for p, f in self.files.items()
                if p[:1] == ("buses",) and (len(p) == 2 or len(p) == 4 and p[:2] not in self.files)]

    def diag(self, level, code, message, path: Path_ = ()) -> Diagnostic:
        line, col = self.locate(path)
        return Diagnostic(level, code, message, self.file_of(path), line, col, format_path(path), list(path))

    def in_main_file(self, d: Diagnostic) -> Diagnostic:
        """Сообщение о подключённом файле — для редактора основного: на строке include, с местом в тексте."""
        if d.file is None or d.file == self.file or not self.files:
            return d
        include = next((i for i, f in self.includes if f == d.file), None)
        line, col = self.positions.get(("include", include), (1, 1)) if include is not None else (1, 1)
        where = Path(d.file).name + (f":{d.line}" if d.line else "")
        return Diagnostic(d.level, d.code, f"{where}: {d.message}", self.file, line, col, d.path, d.node)


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
    map: MapCan | None
    report: Report
    source: SourceMap
    raw: Any = None  # ruamel-документ (для сохранения с комментариями)
    # Данные вместе с подключёнными файлами (до подстановки таблиц значений); None — файлов не подключено
    merged: Any = None


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
    what = _("key") if is_key else _("value")
    if _COMMA_NUMBER.match(value):
        fixed = float(value.replace(",", "."))
        report.add(src.diag(
            "error", "number-comma",
            _("{what} {value!r}: decimal comma used, should be {fixed!r}",
              what=what, value=value, fixed=fixed), path))
        return fixed
    m = _CYR_HEX.match(value)
    if m:
        report.add(src.diag(
            "error", "number-cyrillic-x",
            _("{what} {value!r}: the 0x prefix uses a Cyrillic “х”", what=what, value=value), path))
        return int(m.group(1), 16)
    m = _HEX_STR.match(value)
    if m:
        report.add(src.diag(
            "warning", "number-quoted",
            _("{what} {value!r} is written as a string; remove the quotes", what=what, value=value), path))
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
            msg = _(msg[len("Value error, "):])      # сообщения валидаторов модели помечены N_()
        dash_keys = [k for k in e.get("input") or {} if str(k).startswith("-")] \
            if isinstance(e.get("input"), dict) else []
        if e["type"] == "extra_forbidden" and str(loc[-1]).startswith("-"):
            msg = _("unknown field {name!r}: if this is meant to be a list item, add a space after '-'",
                    name=loc[-1])
        elif e["type"] == "list_type" and dash_keys:
            msg = _("a list is expected: if {name!r} is meant to be a list item, add a space after '-'",
                    name=dash_keys[0])
        elif e["type"] == "extra_forbidden":
            msg = _("unknown field {name!r}", name=loc[-1])
        elif e["type"] == "missing":
            msg = _("missing required field {name!r}", name=loc[-1])
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


# Элемент списка без пробела после «-»: «-name: x» читается как ключ «-name», а не как элемент.
_DASH_NO_SPACE = re.compile(r"^(\s*)-([A-Za-z_\"'{\[][^\n]*)$")


def _yaml_error(e: MarkedYAMLError, text: str) -> tuple[str, int | None, int | None]:
    """Понятное сообщение о синтаксической ошибке YAML: (текст, строка, колонка).

    Сообщения ruamel.yaml («expected <block end>, but found '-'») указывают на место, где разбор
    сломался, а не на причину. Для частых ошибок ищем причину в строках между началом блока
    (``context_mark``) и местом сбоя и объясняем, как исправить.
    """
    pm, cm = e.problem_mark, e.context_mark
    mark = pm or cm
    line = mark.line + 1 if mark else None
    col = mark.column + 1 if mark else None
    problem = (e.problem or str(e)).strip()
    ctx_line = cm.line + 1 if cm else None

    if "duplicate key" in str(e):
        return _("duplicate key: {problem}", problem=e.problem or ""), line, col

    lines = text.splitlines()
    if pm is not None:
        first = cm.line if cm is not None and cm.line <= pm.line else max(pm.line - 1, 0)
        for i in range(pm.line, first - 1, -1):
            m = _DASH_NO_SPACE.match(lines[i]) if i < len(lines) else None
            if m:
                return (_("missing space after '-': write the list item as '- {item}'",
                          item=m.group(2).strip()), i + 1, len(m.group(1)) + 1)

    if "cannot start any token" in problem and "\\t" in problem:
        problem = _("tab character: YAML indentation must use spaces only")
    elif problem.startswith("expected <block end>"):
        if "'-'" in problem:
            problem = _("unexpected list item '-': a key of the block that starts on line {start} was expected here; "
                        "check the indentation", start=ctx_line)
        else:
            problem = _("bad indentation: this line does not line up with the block that starts on line {start}",
                        start=ctx_line)
    elif problem.startswith("mapping values are not allowed"):
        problem = _("unexpected ':': quote a value that contains ': ', or check that the previous line has ':' after "
                    "its key")
    elif "end of stream" in problem and e.context and "quoted scalar" in e.context:
        problem = _("the quote opened on line {start} is never closed", start=ctx_line)
    elif problem.startswith("expected ',' or ']'"):
        problem = _("the '[' opened on line {start} is not closed, or its items are not separated by commas",
                    start=ctx_line)
    elif problem.startswith("expected ',' or '}'"):
        problem = _("the '{{' opened on line {start} is not closed, or its items are not separated by commas",
                    start=ctx_line)
    return problem, line, col


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
        problem, line, col = _yaml_error(e, text)
        report.add(Diagnostic("error", "yaml", problem, filename, line, col))
        return LoadResult(None, report, src)
    if raw is None:
        report.add(Diagnostic("error", "yaml", _("empty file"), filename, 1, 1))
        return LoadResult(None, report, src, raw)

    data = _plain(raw, (), src, report)
    src.positions.setdefault((), (1, 1))
    if isinstance(data, dict):
        base = Path(base_dir) if base_dir is not None else Path(filename).resolve().parent if filename else None
        _include(data, base, src, report)
        merged = copy.deepcopy(data) if src.includes else None
        _value_tables(data, src, report)
    else:
        merged = None
    try:
        cmap = MapCan.model_validate(data)
    except ValidationError as err:
        _pydantic_messages(err, src, report)
        return LoadResult(None, report, src, raw, merged)
    cmap._source = filename
    if base_dir is not None:
        cmap._base_dir = Path(base_dir)
    elif filename:
        cmap._base_dir = Path(filename).resolve().parent
    resolve(cmap)
    return LoadResult(cmap, report, src, raw, merged)


# --------------------------------------------------------------------------- #
# Подключаемые файлы (include) и именованные таблицы значений (value_tables)
# --------------------------------------------------------------------------- #

INCLUDE_KEYS = {"buses", "value_tables"}
# Шину, описанную в основном файле, подключаемый файл может только дополнить устройствами и кадрами
BUS_EXTENSION_KEYS = {"name", "devices", "frames"}


def _include(data: dict, base: Path | None, src: SourceMap, report: Report) -> None:
    """Подключить файлы из ``include``: их шины, устройства, кадры и таблицы значений добавляются к карте.

    Узлы подключённых файлов получают пути после узлов основного файла (индексы основного не меняются),
    позиции и имя файла — из подключённого файла."""
    files = data.get("include")
    if files is None:
        return
    if not isinstance(files, list):
        return          # тип поля проверит схема
    for i, name in enumerate(files):
        if not isinstance(name, str):
            continue
        if base is None:
            report.add(src.diag("error", "include", _("include: the map has no path to resolve included files from"),
                                ("include", i)))
            continue
        path = base / name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            report.add(src.diag("error", "include", _("include: file {name!r} not found", name=name), ("include", i)))
            continue
        fname = str(path)
        try:
            raw = _make_yaml().load(text)
        except MarkedYAMLError as e:
            problem, line, col = _yaml_error(e, text)
            report.add(Diagnostic("error", "yaml", problem, fname, line, col))
            continue
        sub_src = SourceMap(fname)
        part = _plain(raw, (), sub_src, report) if raw is not None else {}
        src.includes.append((i, fname))
        if not isinstance(part, dict):
            report.add(Diagnostic("error", "include", _("an included file must be a YAML mapping"), fname, 1, 1))
            continue
        for key in part:
            if key not in INCLUDE_KEYS:
                report.add(sub_src.diag("error", "include",
                                        _("key {key!r} cannot be included: only buses and value_tables", key=key),
                                        (key,)))
        _merge_tables(data, part, sub_src, src, report)
        _merge_buses(data, part, sub_src, src, report)


def _copy_positions(sub_src: SourceMap, src: SourceMap, remap) -> None:
    for p, pos in sub_src.positions.items():
        q = remap(p)
        if q is not None:
            src.positions[q] = pos
            src.files[q] = sub_src.file


def _merge_tables(data: dict, part: dict, sub_src: SourceMap, src: SourceMap, report: Report) -> None:
    tables = part.get("value_tables")
    if not isinstance(tables, dict):
        return
    own = data.setdefault("value_tables", {})
    if not isinstance(own, dict):
        return
    added = set()
    for name, table in tables.items():
        if name in own:
            report.add(sub_src.diag("error", "include", _("value table {name!r} is already defined", name=name),
                                    ("value_tables", name)))
            continue
        own[name] = table
        added.add(name)
    _copy_positions(sub_src, src, lambda p: p if p[:1] == ("value_tables",) and len(p) > 1 and p[1] in added
                    else None)


def _merge_buses(data: dict, part: dict, sub_src: SourceMap, src: SourceMap, report: Report) -> None:
    buses = part.get("buses")
    if not isinstance(buses, list):
        return
    own = data.setdefault("buses", [])
    if not isinstance(own, list):
        return
    for j, bus in enumerate(buses):
        if not isinstance(bus, dict):
            continue
        target = next((k for k, b in enumerate(own) if isinstance(b, dict) and b.get("name") == bus.get("name")),
                      None)
        if target is None:
            own.append(bus)
            new = len(own) - 1
            _copy_positions(sub_src, src, lambda p, j=j, new=new: ("buses", new) + p[2:] if p[:2] == ("buses", j)
                            else None)
            continue
        for key in bus:
            if key not in BUS_EXTENSION_KEYS:
                report.add(sub_src.diag("error", "include",
                                        _("bus {name!r} is already defined: an included file can only add devices and "
                                          "frames to it, not {key!r}", name=bus.get("name"), key=key),
                                        ("buses", j, key)))
        mine = own[target]
        offsets = {}
        for key in ("devices", "frames"):
            items = bus.get(key)
            if isinstance(items, list):
                lst = mine.setdefault(key, [])
                if isinstance(lst, list):
                    offsets[key] = len(lst)
                    lst.extend(items)

        def remap(p, j=j, target=target, offsets=offsets):
            if p[:2] != ("buses", j) or len(p) < 4 or p[2] not in offsets:
                return None
            return ("buses", target, p[2], p[3] + offsets[p[2]]) + p[4:]

        _copy_positions(sub_src, src, remap)


def _value_tables(data: dict, src: SourceMap, report: Report) -> None:
    """Подставить именованные таблицы: ``values: dc_states`` → таблица из ``value_tables``."""
    tables = data.get("value_tables") if isinstance(data.get("value_tables"), dict) else {}

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "values" and isinstance(v, str):
                    if v in tables:
                        node[k] = tables[v]
                    else:
                        report.add(src.diag("error", "value-table",
                                            _("value table {name!r} is not defined in value_tables", name=v),
                                            path + (k,)))
                        node[k] = None
                elif k != "value_tables":
                    walk(v, path + (k,))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + (i,))

    walk(data, ())


def load(path: str | Path) -> LoadResult:
    p = Path(path)
    return loads(p.read_text(encoding="utf-8"), str(p))
