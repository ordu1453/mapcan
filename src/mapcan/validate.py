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
from .i18n import N_, _
from .loader import LoadResult, SourceMap, load, loads
from .model import LOGO_FORMATS, Frame, MapCan, Signal, enum_entries
from .protocols import j1939_is_pdu1

STYLE_RE = {
    "snake_case": re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"),
    "UPPER_SNAKE": re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$"),
    "camelCase": re.compile(r"^[a-z][a-zA-Z0-9]*$"),
    "PascalCase": re.compile(r"^[A-Z][a-zA-Z0-9]*$"),
}
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FD_DLC = {0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64}

# Правила, которые описаны в документации (для `mapcan rules`).
RULES = {
    "yaml": ("error", N_("Синтаксическая ошибка YAML, повторяющийся ключ")),
    "schema": ("error", N_("Нарушение структуры: тип, обязательное поле, недопустимое значение")),
    "number-comma": ("error", N_("Число записано через запятую (0,1 вместо 0.1)")),
    "number-cyrillic-x": ("error", N_("Кириллическая «х» в шестнадцатеричном числе")),
    "number-quoted": ("warning", N_("Число записано строкой в кавычках")),
    "invalid-identifier": ("error", N_("Имя нельзя использовать как идентификатор C/Python")),
    "duplicate-device-name": ("error", N_("Повтор имени устройства на шине")),
    "duplicate-node-id": ("error", N_("Повтор node_id на шине")),
    "node-id-range": ("error", N_("node_id CANopen вне диапазона 1..127")),
    "duplicate-frame-name": ("error", N_("Повтор имени кадра на шине")),
    "frame-id-missing": ("error", N_("Невозможно определить CAN ID кадра")),
    "duplicate-can-id": ("error", N_("Повтор CAN ID на шине")),
    "can-id-range": ("error", N_("CAN ID не помещается в 11 бит (нужно extended: true)")),
    "dlc-range": ("error", N_("Недопустимый DLC")),
    "duplicate-signal-name": ("error", N_("Повтор имени сигнала/флага в кадре")),
    "signal-out-of-frame": ("error", N_("Сигнал выходит за пределы DLC")),
    "bit-overlap": ("error", N_("Пересечение сигналов по битам (с учётом мультиплексирования)")),
    "enum-overflow": ("error", N_("Значение enum не помещается в разрядность поля")),
    "duplicate-enum-name": ("warning", N_("Одинаковое имя у разных значений enum")),
    "flags-kind": ("error", N_("flags задан у сигнала не типа bitfield")),
    "flag-out-of-field": ("error", N_("Флаг выходит за пределы битового поля")),
    "flag-overlap": ("error", N_("Пересечение флагов внутри битового поля")),
    "flag-length": ("warning", N_("Сигнал типа flag длиной больше 1 бита")),
    "metric-factor": ("error", N_("Нулевой масштаб")),
    "metric-range": ("warning", N_("min/max вне диапазона, представимого полем")),
    "min-max": ("error", N_("min больше max")),
    "mux-no-selector": ("error", N_("Мультиплексированный сигнал в кадре без селектора")),
    "mux-multiple-selectors": ("error", N_("Больше одного селектора в кадре")),
    "mux-value-overflow": ("error", N_("Значение mux не помещается в селектор")),
    "mux-value-unknown": ("warning", N_("Значения mux нет в таблице значений селектора")),
    "mux-selector-muxed": ("error", N_("Селектор сам мультиплексирован")),
    "cycle-missing": ("error", N_("Режим cyclic без cycle_ms")),
    "cycle-unexpected": ("warning", N_("cycle_ms задан для нециклического кадра")),
    "direction-mismatch": ("warning", N_("Направление противоречит типу кадра CANopen")),
    "frame-type-protocol": ("warning", N_("Тип кадра CANopen на шине не CANopen")),
    "sdo-frame-type": ("warning", N_("Описание sdo у кадра не типа sdo_tx/sdo_rx")),
    "sdo-duplicate": ("error", N_("Повтор SDO-обмена (команда, индекс, субиндекс)")),
    "name-style": ("warning", N_("Имя не соответствует правилу стиля (lint)")),
    "name-inconsistent": ("warning", N_("Одно и то же имя значения записано по-разному")),
    "j1939-address": ("error", N_("Адрес J1939 вне 0..253 или повторяется на шине")),
    "j1939-pdu1-pgn": ("warning", N_("PDU1-PGN (PF < 240) с ненулевым младшим байтом")),
    "j1939-destination": ("warning", N_("destination задан для PDU2-PGN (PF ≥ 240) и не используется")),
    "j1939-field-protocol": ("warning", N_("pgn/priority/destination/address на шине не J1939")),
    "unknown-receiver": ("error", N_("Получатель кадра не описан на шине")),
    "float-length": ("error", N_("Сигнал float должен быть 32 или 64 бита")),
    "initial-range": ("warning", N_("Значение по умолчанию вне диапазона сигнала")),
    "invalid-overflow": ("error", N_("Значение invalid не помещается в разрядность сигнала")),
    "logo-missing": ("warning", N_("Файл логотипа не найден")),
    "logo-format": ("error", N_("Неподдерживаемый формат логотипа")),
    "signed-code": ("info", N_("Код знакового числа не поддерживается кодогенерацией "
                               "или задан у беззнакового сигнала")),
    "missing-description": ("info", N_("Нет описания сигнала")),
    "empty-frame": ("info", N_("В кадре не описаны сигналы")),
}


class _Ctx:
    def __init__(self, cmap: MapCan, src: SourceMap, report: Report, disabled: set[str]):
        self.cmap, self.src, self.report, self.disabled = cmap, src, report, disabled

    def emit(self, code: str, message: str, path=(), level: str | None = None) -> None:
        if code in self.disabled:
            return
        lvl = level or RULES.get(code, ("error",))[0]
        self.report.add(self.src.diag(lvl, code, message, path))


def validate_map(cmap: MapCan, src: SourceMap, disable: Iterable[str] = ()) -> Report:
    report = Report()
    ctx = _Ctx(cmap, src, report, set(cmap.lint.disable) | set(disable))
    value_spellings: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    logo = cmap.logo_path
    if logo is not None:
        if logo.suffix.lower() not in LOGO_FORMATS:
            ctx.emit("logo-format", _("логотип {logo!r}: поддерживаются {formats}",
                                      logo=cmap.document.logo, formats=", ".join(LOGO_FORMATS)), ("document", "logo"))
        elif not logo.is_file():
            ctx.emit("logo-missing", _("файл логотипа не найден: {path}", path=logo), ("document", "logo"))

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
                             _("значение {name!r} записано иначе, чем {main!r} в других местах",
                               name=other, main=main), p)
    return report


def _norm(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def _ident(ctx: _Ctx, name: str, what: str, path, style: str | None) -> None:
    if not IDENT_RE.match(name):
        ctx.emit("invalid-identifier", _("{what} {name!r}: допустимы латинские буквы, цифры и _",
                                         what=what, name=name), path)
        return
    if style and style != "any" and not STYLE_RE[style].match(name):
        ctx.emit("name-style", _("{what} {name!r} не в стиле {style}", what=what, name=name, style=style), path)


def _check_bus(ctx: _Ctx, bus) -> None:
    lint = ctx.cmap.lint
    names, nodes, addrs = {}, {}, {}
    for dev in bus.devices:
        if dev.address is not None:
            if bus.protocol != "j1939":
                ctx.emit("j1939-field-protocol", _("address у устройства на шине {protocol}", protocol=bus.protocol),
                         dev._path + ("address",))
            elif dev.address > 253:
                ctx.emit("j1939-address", _("адрес {address:#04x} вне 0..253 (254, 255 — служебные)",
                                            address=dev.address),
                         dev._path + ("address",))
            if dev.address in addrs:
                ctx.emit("j1939-address",
                         _("адрес {address:#04x} уже занят устройством {other!r}",
                           address=dev.address, other=addrs[dev.address].name),
                         dev._path + ("address",))
            addrs[dev.address] = dev
        _ident(ctx, dev.name, _("имя устройства"), dev._path + ("name",), lint.device_name)
        if dev.name in names:
            ctx.emit("duplicate-device-name", _("устройство {name!r} уже описано", name=dev.name),
                     dev._path + ("name",))
        names[dev.name] = dev
        if dev.node_id is not None:
            if bus.protocol == "canopen" and not 1 <= dev.node_id <= 127:
                ctx.emit("node-id-range", _("node_id {node_id:#x} вне 1..127", node_id=dev.node_id),
                         dev._path + ("node_id",))
            if dev.node_id in nodes:
                ctx.emit("duplicate-node-id",
                         _("node_id {node_id:#04x} уже занят устройством {other!r}",
                           node_id=dev.node_id, other=nodes[dev.node_id].name),
                         dev._path + ("node_id",))
            nodes[dev.node_id] = dev

    frame_names, ids = {}, {}
    for frame in bus.all_frames():
        p = frame._path
        if frame.name in frame_names:
            ctx.emit("duplicate-frame-name", _("кадр {name!r} уже описан на шине", name=frame.name), p + ("name",))
        frame_names[frame.name] = frame
        if frame.can_id is None:
            if bus.protocol == "j1939":
                # Сообщение — на поле, которое нужно заполнить (редактор подсвечивает его)
                if frame.pgn is None:
                    ctx.emit("frame-id-missing", _("кадр {name!r}: {why}", name=frame.name, why=_("нужен pgn (или id)")),
                             p + ("pgn",))
                else:
                    ctx.emit("frame-id-missing", _("кадр {name!r}: {why}", name=frame.name,
                                                   why=_("у устройства нет address")), p)
            elif frame.type == "raw" or bus.protocol != "canopen":
                ctx.emit("frame-id-missing", _("кадр {name!r}: для типа {type} нужен явный id",
                                               name=frame.name, type=frame.type), p + ("id",))
            else:
                ctx.emit("frame-id-missing",
                         _("кадр {name!r}: нет node_id у устройства для вычисления ID {type}",
                           name=frame.name, type=frame.type), p)
            continue
        if frame.can_id in ids:
            other = ids[frame.can_id]
            ctx.emit("duplicate-can-id",
                     _("CAN ID {can_id:#05x} кадра {name!r} совпадает с кадром {other!r}",
                       can_id=frame.can_id, name=frame.name, other=other.name),
                     p + (("id",) if frame.id is not None else ("type",)))
        else:
            ids[frame.can_id] = frame
        if frame.can_id > 0x7FF and not frame.extended:
            ctx.emit("can-id-range", _("CAN ID {can_id:#x} > 0x7FF", can_id=frame.can_id), p + ("id",))


def _check_frame(ctx: _Ctx, frame: Frame) -> None:
    p = frame._path
    bus = frame.bus
    _ident(ctx, frame.name, _("имя кадра"), p + ("name",), ctx.cmap.lint.frame_name)

    if bus.fd:
        if frame.dlc not in FD_DLC:
            ctx.emit("dlc-range", _("DLC {dlc} недопустим для CAN FD", dlc=frame.dlc), p + ("dlc",))
    elif frame.dlc > 8:
        ctx.emit("dlc-range", _("DLC {dlc} > 8 (для CAN FD укажите fd: true у шины)", dlc=frame.dlc), p + ("dlc",))

    fc = FUNCTION_CODES.get(frame.type)
    devices = {d.name for d in bus.devices}
    for i, r in enumerate(frame.receivers):
        if r not in devices:
            ctx.emit("unknown-receiver", _("получатель {name!r} не описан на шине {bus!r}", name=r, bus=bus.name),
                     p + ("receivers", i))
    j1939_fields = [k for k in ("pgn", "priority", "destination") if getattr(frame, k) is not None]
    if j1939_fields and bus.protocol != "j1939":
        ctx.emit("j1939-field-protocol", _("{fields} у кадра на шине {protocol}",
                                           fields=", ".join(j1939_fields), protocol=bus.protocol),
                 p + (j1939_fields[0],))
    if bus.protocol == "j1939" and frame.pgn is not None:
        if j1939_is_pdu1(frame.pgn) and frame.pgn & 0xFF:
            ctx.emit("j1939-pdu1-pgn", _("PGN {pgn:#06x} — PDU1: младший байт должен быть 0 "
                                         "(адрес получателя задаётся destination)", pgn=frame.pgn), p + ("pgn",))
        if not j1939_is_pdu1(frame.pgn) and frame.destination is not None:
            ctx.emit("j1939-destination", _("PGN {pgn:#06x} — PDU2 (широковещательный), "
                                            "destination не используется", pgn=frame.pgn), p + ("destination",))
    if bus.protocol != "canopen" and frame.type != "raw":
        ctx.emit("frame-type-protocol", _("тип {type} на шине с протоколом {protocol}",
                                          type=frame.type, protocol=bus.protocol), p + ("type",))
    if fc and fc.direction and frame.direction and frame.direction != fc.direction and frame.device:
        ctx.emit("direction-mismatch",
                 _("кадр {type} обычно {expected} для устройства, указано {actual}", type=frame.type,
                   expected=fc.direction.upper(), actual=frame.direction.upper()), p + ("direction",))

    tr = frame.transmission
    if tr is not None:
        if tr.mode == "cyclic" and tr.cycle_ms is None:
            ctx.emit("cycle-missing", _("для режима cyclic нужен cycle_ms"), p + ("transmission",))
        if tr.mode != "cyclic" and tr.cycle_ms is not None:
            ctx.emit("cycle-unexpected", _("cycle_ms задан для режима {mode}", mode=tr.mode), p + ("transmission",))

    if frame.sdo:
        if frame.type not in ("sdo_tx", "sdo_rx"):
            ctx.emit("sdo-frame-type", _("sdo у кадра типа {type}", type=frame.type), p + ("sdo",))
        seen = {}
        for ex in frame.sdo:
            key = (ex.command, ex.index, ex.subindex)
            if key in seen:
                ctx.emit("sdo-duplicate",
                         _("обмен {name!r} повторяет {other!r} (0x{command:02X}, 0x{index:04X}:{subindex})",
                           name=ex.name, other=seen[key], command=ex.command, index=ex.index,
                           subindex=ex.subindex), ex._path)
            seen[key] = ex.name

    if not frame.layout:
        if frame.dlc > 0:
            ctx.emit("empty-frame", _("кадр {name!r} без сигналов", name=frame.name), p)
        return

    _check_signals(ctx, frame)


def _check_signals(ctx: _Ctx, frame: Frame) -> None:
    lint = ctx.cmap.lint
    sigs = frame.layout
    nbits = frame.dlc * 8

    # Имена
    names: dict[str, tuple] = {}
    for s in sigs:
        entries = [(s.name, s._path + ("name",), False)]
        entries += [(f.name, f._path + ("name",), True) for f in s.flags or []]
        for name, path, is_flag in entries:
            _ident(ctx, name, _("имя флага") if is_flag else _("имя сигнала"), path, lint.signal_name)
            if name in names:
                other = _("флаг") if names[name][1] else _("сигнал")
                msg = (_("флаг {name!r} уже есть в кадре {frame!r} ({other})") if is_flag
                       else _("сигнал {name!r} уже есть в кадре {frame!r} ({other})"))
                ctx.emit("duplicate-signal-name", msg.format(name=name, frame=frame.name, other=other), path)
            else:
                names[name] = (path, is_flag)

    # Мультиплексирование
    selectors = [s for s in sigs if s.multiplexer]
    selector = selectors[0] if selectors else None
    for extra in selectors[1:]:
        ctx.emit("mux-multiple-selectors", _("второй селектор {name!r}", name=extra.name),
                 extra._path + ("multiplexer",))
    for sel in selectors:
        if sel.mux is not None:
            ctx.emit("mux-selector-muxed", _("селектор {name!r} не может иметь mux", name=sel.name),
                     sel._path + ("mux",))

    for s in sigs:
        sp = s._path
        be = s.byte_order == "big_endian"
        occ = B.occupied_bits(s.start_bit, s.bit_length, be)
        if min(occ) < 0 or max(occ) >= nbits:
            first, last = B.byte_span(s.start_bit, s.bit_length, be)
            ctx.emit("signal-out-of-frame",
                     _("сигнал {name!r} занимает байты {first}..{last}, а DLC = {dlc}",
                       name=s.name, first=first, last=last, dlc=frame.dlc), sp)

        lo, hi = B.raw_range(s.bit_length, s.signed)
        for v, ev in enum_entries(s.values):
            _ident(ctx, ev.name, _("имя значения"), sp + ("values", v), lint.value_name)
            if not lo <= v <= hi:
                msg = (_("значение {value} ({name}) не помещается в {bits} бит (знаковое: {lo}..{hi})") if s.signed
                       else _("значение {value} ({name}) не помещается в {bits} бит (беззнаковое: {lo}..{hi})"))
                ctx.emit("enum-overflow", msg.format(value=v, name=ev.name, bits=s.bit_length, lo=lo, hi=hi),
                         sp + ("values", v))
        _dup_enum_names(ctx, s.values, sp)

        if s.flags and s.kind != "bitfield":
            ctx.emit("flags-kind", _("flags у сигнала типа {kind}", kind=s.kind), sp + ("flags",))
        if s.kind == "flag" and s.bit_length != 1:
            ctx.emit("flag-length", _("сигнал-флаг {name!r} длиной {bits} бит", name=s.name, bits=s.bit_length),
                     sp + ("bit_length",))
        _check_flags(ctx, s)

        if s.factor == 0:
            ctx.emit("metric-factor", "factor = 0", sp + ("factor",))
        elif s.kind == "metric":
            phys = sorted((lo * s.factor + s.offset, hi * s.factor + s.offset))
            if s.min is not None and s.max is not None and s.min > s.max:
                ctx.emit("min-max", _("min {min} > max {max}", min=s.min, max=s.max), sp + ("min",))
            for k in ("min", "max"):
                val = getattr(s, k)
                if val is not None and not phys[0] - 1e-9 <= val <= phys[1] + 1e-9:
                    ctx.emit("metric-range",
                             _("{key} = {value:g} вне представимого диапазона {lo:g}..{hi:g} {unit}",
                               key=k, value=val, lo=phys[0], hi=phys[1], unit=s.unit or "").rstrip(), sp + (k,))

        if s.kind == "float" and s.bit_length not in (32, 64):
            ctx.emit("float-length", _("сигнал {name!r}: float — 32 или 64 бита, задано {bits}",
                                       name=s.name, bits=s.bit_length), sp + ("bit_length",))
        raw_lo, raw_hi = (lo, hi) if s.kind != "float" else (None, None)
        for v in s.invalid_values:
            if raw_lo is not None and not raw_lo <= v <= raw_hi:
                ctx.emit("invalid-overflow", _("invalid = {value} не помещается в {bits} бит ({lo}..{hi})",
                                               value=v, bits=s.bit_length, lo=raw_lo, hi=raw_hi), sp + ("invalid",))
        if s.initial is not None and s.factor != 0:
            raw = s.initial_raw
            if raw_lo is not None and not raw_lo <= raw <= raw_hi:
                ctx.emit("initial-range", _("initial = {value:g} → raw {raw} вне {lo}..{hi}",
                                            value=s.initial, raw=raw, lo=raw_lo, hi=raw_hi),
                         sp + ("initial",))
            elif (s.min is not None and s.initial < s.min) or (s.max is not None and s.initial > s.max):
                ctx.emit("initial-range", _("initial = {value:g} вне min/max", value=s.initial), sp + ("initial",))

        if s.description is None and not s._path[-1:] == ("sdo",):
            ctx.emit("missing-description", _("сигнал {name!r} без описания", name=s.name), sp + ("description",))

        if s.signed_code is not None and not s.signed:
            ctx.emit("signed-code", _("signed_code у беззнакового сигнала {name!r} не используется", name=s.name),
                     sp + ("signed_code",))
        elif s.signed and s.signed_code in ("ones_complement", "sign_magnitude"):
            ctx.emit("signed-code", _("{name!r}: сгенерированный код и DBC читают значение в дополнительном коде",
                                      name=s.name), sp + ("signed_code",))

        if s.mux is not None:
            if selector is None:
                ctx.emit("mux-no-selector", _("у сигнала {name!r} задан mux, но в кадре нет multiplexer", name=s.name),
                         sp + ("mux",))
            else:
                slo, shi = B.raw_range(selector.bit_length, selector.signed)
                known = {v for v, _ in enum_entries(selector.values)}
                for mv in s.mux_values:
                    if not slo <= mv <= shi:
                        ctx.emit("mux-value-overflow",
                                 _("mux {value} не помещается в селектор {name!r}", value=mv, name=selector.name),
                                 sp + ("mux",))
                    elif known and mv not in known:
                        ctx.emit("mux-value-unknown",
                                 _("mux {value} отсутствует в values селектора {name!r}", value=mv,
                                   name=selector.name), sp + ("mux",))

    _check_overlap(ctx, frame, sigs, selector)


def _dup_enum_names(ctx: _Ctx, values, path) -> None:
    seen = {}
    for v, ev in enum_entries(values):
        if ev.name in seen:
            ctx.emit("duplicate-enum-name", _("имя {name!r} у значений {a} и {b}", name=ev.name, a=seen[ev.name], b=v),
                     path + ("values", v))
        seen[ev.name] = v


def _check_flags(ctx: _Ctx, s: Signal) -> None:
    if not s.flags:
        return
    used: dict[int, str] = {}
    for fl in s.flags:
        if fl.bit + fl.bit_length > s.bit_length:
            ctx.emit("flag-out-of-field",
                     _("флаг {name!r} (биты {first}..{last}) вне поля длиной {bits} бит", name=fl.name,
                       first=fl.bit, last=fl.bit + fl.bit_length - 1, bits=s.bit_length), fl._path + ("bit",))
        for b in range(fl.bit, fl.bit + fl.bit_length):
            if b in used:
                ctx.emit("flag-overlap", _("флаг {name!r} пересекается с {other!r} по биту {bit}",
                                           name=fl.name, other=used[b], bit=b),
                         fl._path + ("bit",))
                break
            used[b] = fl.name
        lo, hi = B.raw_range(fl.bit_length, False)
        for v, ev in enum_entries(fl.values):
            _ident(ctx, ev.name, _("имя значения"), fl._path + ("values", v), ctx.cmap.lint.value_name)
            if not lo <= v <= hi:
                ctx.emit("enum-overflow", _("значение {value} не помещается во флаг {name!r}", value=v, name=fl.name),
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
                rng = _("бит {bit}", bit=lo) if lo == hi else _("биты {first}..{last}", first=lo, last=hi)
                byte = str(lo // 8) if lo // 8 == hi // 8 else f"{lo // 8}..{hi // 8}"
                ctx.emit("bit-overlap",
                         _("сигнал {name!r} пересекается с {other!r}: {bits} (байт {byte})",
                           name=a.name, other=b.name, bits=rng, byte=byte),
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
