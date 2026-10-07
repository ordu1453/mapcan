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
    map: MapCan | None
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
    what = _("ключ") if is_key else _("значение")
    if _COMMA_NUMBER.match(value):
        fixed = float(value.replace(",", "."))
        report.add(src.diag(
            "error", "number-comma",
            _("{what} {value!r}: дробная часть отделена запятой, нужно {fixed!r}",
              what=what, value=value, fixed=fixed), path))
        return fixed
    m = _CYR_HEX.match(value)
    if m:
        report.add(src.diag(
            "error", "number-cyrillic-x",
            _("{what} {value!r}: в префиксе 0x используется кириллическая «х»", what=what, value=value), path))
        return int(m.group(1), 16)
    m = _HEX_STR.match(value)
    if m:
        report.add(src.diag(
            "warning", "number-quoted",
            _("{what} {value!r} записано строкой; уберите кавычки", what=what, value=value), path))
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
            msg = _("неизвестное поле {name!r}: если это элемент списка, после «-» нужен пробел",
                    name=loc[-1])
        elif e["type"] == "list_type" and dash_keys:
            msg = _("ожидается список: если {name!r} — его элемент, после «-» нужен пробел",
                    name=dash_keys[0])
        elif e["type"] == "extra_forbidden":
            msg = _("неизвестное поле {name!r}", name=loc[-1])
        elif e["type"] == "missing":
            msg = _("отсутствует обязательное поле {name!r}", name=loc[-1])
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
        return _("повторяющийся ключ: {problem}", problem=e.problem or ""), line, col

    lines = text.splitlines()
    if pm is not None:
        first = cm.line if cm is not None and cm.line <= pm.line else max(pm.line - 1, 0)
        for i in range(pm.line, first - 1, -1):
            m = _DASH_NO_SPACE.match(lines[i]) if i < len(lines) else None
            if m:
                return (_("после «-» нужен пробел: элемент списка записывается как «- {item}»",
                          item=m.group(2).strip()), i + 1, len(m.group(1)) + 1)

    if "cannot start any token" in problem and "\\t" in problem:
        problem = _("символ табуляции: отступы в YAML делаются только пробелами")
    elif problem.startswith("expected <block end>"):
        if "'-'" in problem:
            problem = _("элемент списка «-» не на своём месте: здесь ожидался ключ блока, начатого "
                        "в строке {start}; проверьте отступ", start=ctx_line)
        else:
            problem = _("неверный отступ: строка не выровнена по блоку, начатому в строке {start}",
                        start=ctx_line)
    elif problem.startswith("mapping values are not allowed"):
        problem = _("лишнее «:» — возьмите значение, содержащее «: », в кавычки или проверьте, "
                    "что у предыдущей строки есть «:» после ключа")
    elif "end of stream" in problem and e.context and "quoted scalar" in e.context:
        problem = _("кавычка, открытая в строке {start}, не закрыта", start=ctx_line)
    elif problem.startswith("expected ',' or ']'"):
        problem = _("«[», открытая в строке {start}, не закрыта или элементы не разделены запятой",
                    start=ctx_line)
    elif problem.startswith("expected ',' or '}'"):
        problem = _("«{{», открытая в строке {start}, не закрыта или элементы не разделены запятой",
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
        report.add(Diagnostic("error", "yaml", _("пустой файл"), filename, 1, 1))
        return LoadResult(None, report, src, raw)

    data = _plain(raw, (), src, report)
    src.positions.setdefault((), (1, 1))
    try:
        cmap = MapCan.model_validate(data)
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
