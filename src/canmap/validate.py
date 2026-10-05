"""Семантические проверки карты.

Каждое правило имеет код (``Diagnostic.code``); правила стиля можно
отключить через ``lint.disable`` в YAML или опцией ``--disable`` CLI.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from . import bits as B
from .canopen import FUNCTION_CODES
from .diagnostics import Report
from .loader import LoadResult, SourceMap, load, loads
from .model import LOGO_FORMATS, CanMap, Frame, Signal, enum_entries

STYLE_RE = {
    "snake_case": re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"),
    "UPPER_SNAKE": re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$"),
    "camelCase": re.compile(r"^[a-z][a-zA-Z0-9]*$"),
    "PascalCase": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
}
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FD_DLC = {0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64}

# Правила, которые описаны в документации (для `canmap rules`).
RULES = {
    "yaml": ("error", "Синтаксическая ошибка YAML, повторяющийся ключ"),
    "schema": ("error", "Нарушение структуры: тип, обязательное поле, недопустимое значение"),
    "number-comma": ("error", "Число записано через запятую (0,1 вместо 0.1)"),
    "number-cyrillic-x": ("error", "Кириллическая «х» в шестнадцатеричном числе"),
    "number-quoted": ("warning", "Число записано строкой в кавычках"),
    "invalid-identifier": ("error", "Имя нельзя использовать как идентификатор C/Python"),
    "duplicate-device-name": ("error", "Повтор имени устройства на шине"),
    "duplicate-node-id": ("error", "Повтор node_id на шине"),
    "node-id-range": ("error", "node_id CANopen вне диапазона 1..127"),
    "duplicate-frame-name": ("error", "Повтор имени кадра на шине"),
    "frame-id-missing": ("error", "Невозможно определить CAN ID кадра"),
    "duplicate-can-id": ("error", "Повтор CAN ID на шине"),
    "can-id-range": ("error", "CAN ID не помещается в 11 бит (нужно extended: true)"),
    "dlc-range": ("error", "Недопустимый DLC"),
    "duplicate-signal-name": ("error", "Повтор имени сигнала/флага в кадре"),
    "signal-out-of-frame": ("error", "Сигнал выходит за пределы DLC"),
    "bit-overlap": ("error", "Пересечение сигналов по битам (с учётом мультиплексирования)"),
    "enum-overflow": ("error", "Значение enum не помещается в разрядность поля"),
    "duplicate-enum-name": ("warning", "Одинаковое имя у разных значений enum"),
    "flags-kind": ("error", "flags задан у сигнала не типа bitfield"),
    "flag-out-of-field": ("error", "Флаг выходит за пределы битового поля"),
    "flag-overlap": ("error", "Пересечение флагов внутри битового поля"),
    "flag-length": ("warning", "Сигнал типа flag длиной больше 1 бита"),
    "metric-factor": ("error", "Нулевой масштаб"),
    "metric-range": ("warning", "min/max вне диапазона, представимого полем"),
    "min-max": ("error", "min больше max"),
    "mux-no-selector": ("error", "Мультиплексированный сигнал в кадре без селектора"),
    "mux-multiple-selectors": ("error", "Больше одного селектора в кадре"),
    "mux-value-overflow": ("error", "Значение mux не помещается в селектор"),
    "mux-value-unknown": ("warning", "Значения mux нет в таблице значений селектора"),
    "mux-selector-muxed": ("error", "Селектор сам мультиплексирован"),
    "cycle-missing": ("error", "Режим cyclic без cycle_ms"),
    "cycle-unexpected": ("warning", "cycle_ms задан для нециклического кадра"),
    "direction-mismatch": ("warning", "Направление противоречит типу кадра CANopen"),
    "frame-type-protocol": ("warning", "Тип кадра CANopen на шине протокола can"),
    "sdo-frame-type": ("warning", "Описание sdo у кадра не типа sdo_tx/sdo_rx"),
    "sdo-duplicate": ("error", "Повтор SDO-обмена (команда, индекс, субиндекс)"),
    "name-style": ("warning", "Имя не соответствует правилу стиля (lint)"),
    "name-inconsistent": ("warning", "Одно и то же имя значения записано по-разному"),
    "logo-missing": ("warning", "Файл логотипа не найден"),
    "logo-format": ("error", "Неподдерживаемый формат логотипа"),
    "missing-description": ("info", "Нет описания сигнала"),
    "empty-frame": ("info", "В кадре не описаны сигналы"),
}


class _Ctx:
    def __init__(self, cmap: CanMap, src: SourceMap, report: Report, disabled: set[str]):
        self.cmap, self.src, self.report, self.disabled = cmap, src, report, disabled

    def emit(self, code: str, message: str, path=(), level: str | None = None) -> None:
        if code in self.disabled:
            return
        lvl = level or RULES.get(code, ("error",))[0]
        self.report.add(self.src.diag(lvl, code, message, path))


def validate_map(cmap: CanMap, src: SourceMap, disable: Iterable[str] = ()) -> Report:
    report = Report()
    ctx = _Ctx(cmap, src, report, set(cmap.lint.disable) | set(disable))
    value_spellings: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    logo = cmap.logo_path
    if logo is not None:
        if logo.suffix.lower() not in LOGO_FORMATS:
            ctx.emit("logo-format", f"логотип {cmap.document.logo!r}: поддерживаются "
                     + ", ".join(LOGO_FORMATS), ("document", "logo"))
        elif not logo.is_file():
            ctx.emit("logo-missing", f"файл логотипа не найден: {logo}", ("document", "logo"))

    for bus in cmap.buses:
        _check_bus(ctx, bus)
        for frame in bus.all_frames():
            _check_frame(ctx, frame)
            for sig in frame.signals:
                for v, ev in enum_entries(sig.values):
                    value_spellings[_norm(ev.name)][ev.name].append(sig._path + ("values", v))
                for fl in sig.flags or []:
                    for v, ev in enum_entries(fl.values):
                        value_spellings[_norm(ev.name)][ev.name].append(fl._path + ("values", v))

    for spellings in value_spellings.values():
        if len(spellings) > 1:
            # Эталон — корректный идентификатор, затем самое частое написание.
            names = sorted(spellings, key=lambda n: (not IDENT_RE.match(n), -len(spellings[n])))
            main = names[0]
            for other in names[1:]:
                for p in spellings[other]:
                    ctx.emit("name-inconsistent",
                             f"значение {other!r} записано иначе, чем {main!r} в других местах", p)
    return report


def _norm(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def _ident(ctx: _Ctx, name: str, what: str, path, style: str | None) -> None:
    if not IDENT_RE.match(name):
        ctx.emit("invalid-identifier", f"{what} {name!r}: допустимы латинские буквы, цифры и _", path)
        return
    if style and style != "any" and not STYLE_RE[style].match(name):
        ctx.emit("name-style", f"{what} {name!r} не в стиле {style}", path)


def _check_bus(ctx: _Ctx, bus) -> None:
    lint = ctx.cmap.lint
    names, nodes = {}, {}
    for dev in bus.devices:
        _ident(ctx, dev.name, "имя устройства", dev._path + ("name",), lint.device_name)
        if dev.name in names:
            ctx.emit("duplicate-device-name", f"устройство {dev.name!r} уже описано", dev._path + ("name",))
        names[dev.name] = dev
        if dev.node_id is not None:
            if bus.protocol == "canopen" and not 1 <= dev.node_id <= 127:
                ctx.emit("node-id-range", f"node_id {dev.node_id:#x} вне 1..127", dev._path + ("node_id",))
            if dev.node_id in nodes:
                ctx.emit("duplicate-node-id",
                         f"node_id {dev.node_id:#04x} уже занят устройством {nodes[dev.node_id].name!r}",
                         dev._path + ("node_id",))
            nodes[dev.node_id] = dev

    frame_names, ids = {}, {}
    for frame in bus.all_frames():
        p = frame._path
        if frame.name in frame_names:
            ctx.emit("duplicate-frame-name", f"кадр {frame.name!r} уже описан на шине", p + ("name",))
        frame_names[frame.name] = frame
        if frame.can_id is None:
            if frame.type == "raw" or bus.protocol != "canopen":
                ctx.emit("frame-id-missing", f"кадр {frame.name!r}: для типа {frame.type} нужен явный id", p)
            else:
                ctx.emit("frame-id-missing",
                         f"кадр {frame.name!r}: нет node_id у устройства для вычисления ID {frame.type}", p)
            continue
        if frame.can_id in ids:
            other = ids[frame.can_id]
            ctx.emit("duplicate-can-id",
                     f"CAN ID {frame.can_id:#05x} кадра {frame.name!r} совпадает с кадром {other.name!r}",
                     p + (("id",) if frame.id is not None else ("type",)))
        else:
            ids[frame.can_id] = frame
        if frame.can_id > 0x7FF and not frame.extended:
            ctx.emit("can-id-range", f"CAN ID {frame.can_id:#x} > 0x7FF", p + ("id",))


def _check_frame(ctx: _Ctx, frame: Frame) -> None:
    p = frame._path
    bus = frame.bus
    _ident(ctx, frame.name, "имя кадра", p + ("name",), ctx.cmap.lint.frame_name)

    if bus.fd:
        if frame.dlc not in FD_DLC:
            ctx.emit("dlc-range", f"DLC {frame.dlc} недопустим для CAN FD", p + ("dlc",))
    elif frame.dlc > 8:
        ctx.emit("dlc-range", f"DLC {frame.dlc} > 8 (для CAN FD укажите fd: true у шины)", p + ("dlc",))

    fc = FUNCTION_CODES.get(frame.type)
    if bus.protocol == "can" and frame.type != "raw":
        ctx.emit("frame-type-protocol", f"тип {frame.type} на шине с протоколом can", p + ("type",))
    if fc and fc.direction and frame.direction and frame.direction != fc.direction and frame.device:
        ctx.emit("direction-mismatch",
                 f"кадр {frame.type} обычно {fc.direction.upper()} для устройства, указано "
                 f"{frame.direction.upper()}", p + ("direction",))

    tr = frame.transmission
    if tr is not None:
        if tr.mode == "cyclic" and tr.cycle_ms is None:
            ctx.emit("cycle-missing", "для режима cyclic нужен cycle_ms", p + ("transmission",))
        if tr.mode != "cyclic" and tr.cycle_ms is not None:
            ctx.emit("cycle-unexpected", f"cycle_ms задан для режима {tr.mode}", p + ("transmission",))

    if frame.sdo:
        if frame.type not in ("sdo_tx", "sdo_rx"):
            ctx.emit("sdo-frame-type", f"sdo у кадра типа {frame.type}", p + ("sdo",))
        seen = {}
        for ex in frame.sdo:
            key = (ex.command, ex.index, ex.subindex)
            if key in seen:
                ctx.emit("sdo-duplicate",
                         f"обмен {ex.name!r} повторяет {seen[key]!r} "
                         f"(0x{ex.command:02X}, 0x{ex.index:04X}:{ex.subindex})", ex._path)
            seen[key] = ex.name

    if not frame.layout:
        if frame.dlc > 0:
            ctx.emit("empty-frame", f"кадр {frame.name!r} без сигналов", p)
        return

    _check_signals(ctx, frame)


def _check_signals(ctx: _Ctx, frame: Frame) -> None:
    lint = ctx.cmap.lint
    sigs = frame.layout
    nbits = frame.dlc * 8

    # Имена
    names: dict[str, tuple] = {}
    for s in sigs:
        entries = [(s.name, s._path + ("name",), "сигнал")]
        entries += [(f.name, f._path + ("name",), "флаг") for f in s.flags or []]
        for name, path, what in entries:
            _ident(ctx, name, f"имя {'сигнала' if what == 'сигнал' else 'флага'}", path, lint.signal_name)
            if name in names:
                ctx.emit("duplicate-signal-name",
                         f"{what} {name!r} уже есть в кадре {frame.name!r} ({names[name][1]})", path)
            else:
                names[name] = (path, what)

    # Мультиплексирование
    selectors = [s for s in sigs if s.multiplexer]
    selector = selectors[0] if selectors else None
    for extra in selectors[1:]:
        ctx.emit("mux-multiple-selectors", f"второй селектор {extra.name!r}", extra._path + ("multiplexer",))
    for sel in selectors:
        if sel.mux is not None:
            ctx.emit("mux-selector-muxed", f"селектор {sel.name!r} не может иметь mux", sel._path + ("mux",))

    for s in sigs:
        sp = s._path
        be = s.byte_order == "big_endian"
        occ = B.occupied_bits(s.start_bit, s.bit_length, be)
        if min(occ) < 0 or max(occ) >= nbits:
            first, last = B.byte_span(s.start_bit, s.bit_length, be)
            ctx.emit("signal-out-of-frame",
                     f"сигнал {s.name!r} занимает байты {first}..{last}, а DLC = {frame.dlc}", sp)

        lo, hi = B.raw_range(s.bit_length, s.signed)
        for v, ev in enum_entries(s.values):
            _ident(ctx, ev.name, "имя значения", sp + ("values", v), lint.value_name)
            if not lo <= v <= hi:
                ctx.emit("enum-overflow",
                         f"значение {v} ({ev.name}) не помещается в {s.bit_length} бит "
                         f"({'знаковое' if s.signed else 'беззнаковое'}: {lo}..{hi})", sp + ("values", v))
        _dup_enum_names(ctx, s.values, sp)

        if s.flags and s.kind != "bitfield":
            ctx.emit("flags-kind", f"flags у сигнала типа {s.kind}", sp + ("flags",))
        if s.kind == "flag" and s.bit_length != 1:
            ctx.emit("flag-length", f"сигнал-флаг {s.name!r} длиной {s.bit_length} бит", sp)
        _check_flags(ctx, s)

        if s.factor == 0:
            ctx.emit("metric-factor", "factor = 0", sp + ("factor",))
        elif s.kind == "metric":
            phys = sorted((lo * s.factor + s.offset, hi * s.factor + s.offset))
            if s.min is not None and s.max is not None and s.min > s.max:
                ctx.emit("min-max", f"min {s.min} > max {s.max}", sp + ("min",))
            for k in ("min", "max"):
                val = getattr(s, k)
                if val is not None and not phys[0] - 1e-9 <= val <= phys[1] + 1e-9:
                    ctx.emit("metric-range",
                             f"{k} = {val:g} вне представимого диапазона "
                             f"{phys[0]:g}..{phys[1]:g} {s.unit or ''}".rstrip(), sp + (k,))

        if s.description is None and not s._path[-1:] == ("sdo",):
            ctx.emit("missing-description", f"сигнал {s.name!r} без описания", sp)

        if s.mux is not None:
            if selector is None:
                ctx.emit("mux-no-selector", f"у сигнала {s.name!r} задан mux, но в кадре нет multiplexer",
                         sp + ("mux",))
            else:
                slo, shi = B.raw_range(selector.bit_length, selector.signed)
                known = {v for v, _ in enum_entries(selector.values)}
                for mv in s.mux_values:
                    if not slo <= mv <= shi:
                        ctx.emit("mux-value-overflow",
                                 f"mux {mv} не помещается в селектор {selector.name!r}", sp + ("mux",))
                    elif known and mv not in known:
                        ctx.emit("mux-value-unknown",
                                 f"mux {mv} отсутствует в values селектора {selector.name!r}", sp + ("mux",))

    _check_overlap(ctx, frame, sigs, selector)


def _dup_enum_names(ctx: _Ctx, values, path) -> None:
    seen = {}
    for v, ev in enum_entries(values):
        if ev.name in seen:
            ctx.emit("duplicate-enum-name", f"имя {ev.name!r} у значений {seen[ev.name]} и {v}",
                     path + ("values", v))
        seen[ev.name] = v


def _check_flags(ctx: _Ctx, s: Signal) -> None:
    if not s.flags:
        return
    used: dict[int, str] = {}
    for fl in s.flags:
        if fl.bit + fl.bit_length > s.bit_length:
            ctx.emit("flag-out-of-field",
                     f"флаг {fl.name!r} (биты {fl.bit}..{fl.bit + fl.bit_length - 1}) вне поля "
                     f"длиной {s.bit_length} бит", fl._path + ("bit",))
        for b in range(fl.bit, fl.bit + fl.bit_length):
            if b in used:
                ctx.emit("flag-overlap", f"флаг {fl.name!r} пересекается с {used[b]!r} по биту {b}",
                         fl._path + ("bit",))
                break
            used[b] = fl.name
        lo, hi = B.raw_range(fl.bit_length, False)
        for v, ev in enum_entries(fl.values):
            _ident(ctx, ev.name, "имя значения", fl._path + ("values", v), ctx.cmap.lint.value_name)
            if not lo <= v <= hi:
                ctx.emit("enum-overflow", f"значение {v} не помещается во флаг {fl.name!r}",
                         fl._path + ("values", v))


def _check_overlap(ctx: _Ctx, frame: Frame, sigs: list[Signal], selector) -> None:
    def coexist(a: Signal, b: Signal) -> bool:
        if a.mux is None or b.mux is None:
            return True
        return bool(set(a.mux_values) & set(b.mux_values))

    occ = [set(B.occupied_bits(s.start_bit, s.bit_length, s.byte_order == "big_endian")) for s in sigs]
    for i, a in enumerate(sigs):
        for j in range(i):
            b = sigs[j]
            common = occ[i] & occ[j]
            if common and coexist(a, b):
                lo, hi = min(common), max(common)
                rng = f"бит {lo}" if lo == hi else f"биты {lo}..{hi}"
                ctx.emit("bit-overlap",
                         f"сигнал {a.name!r} пересекается с {b.name!r}: {rng} "
                         f"(байт {lo // 8}{'' if lo // 8 == hi // 8 else '..' + str(hi // 8)})",
                         a._path)


# --------------------------------------------------------------------------- #


def check(result: LoadResult, disable: Iterable[str] = ()) -> Report:
    """Объединить ошибки загрузки и семантической проверки."""
    report = Report()
    disabled = set(disable)
    report.extend(d for d in result.report.diagnostics if d.code not in disabled)
    if result.map is not None:
        report.extend(validate_map(result.map, result.source, disabled).diagnostics)
    return report


def validate_file(path, disable: Iterable[str] = ()) -> tuple[LoadResult, Report]:
    res = load(path)
    return res, check(res, disable)


def validate_text(text: str, filename: str = "<text>", disable: Iterable[str] = ()):
    res = loads(text, filename)
    return res, check(res, disable)
