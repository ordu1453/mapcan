"""Семантические проверки карты.

Каждое правило имеет код (``Diagnostic.code``); правила стиля можно
отключить через ``lint.disable`` в YAML или опцией ``--disable`` CLI.
"""

from __future__ import annotations

import keyword
import re
from collections import defaultdict
from collections.abc import Iterable

from . import bits as B
from .canopen import CANOPEN_DLC, FUNCTION_CODES
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

# Ключевые слова C (C99…C23) и Python: имена сигналов становятся полями структур и классов.
C_KEYWORDS = frozenset("""
    auto break case char const continue default do double else enum extern float for goto if inline
    int long register restrict return short signed sizeof static struct switch typedef union unsigned
    void volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn
    _Static_assert _Thread_local alignas alignof bool constexpr false nullptr static_assert
    thread_local true typeof typeof_unqual
""".split())
PY_KEYWORDS = frozenset(keyword.kwlist)
# Члены сгенерированного класса кадра в Python-модуле.
PY_FRAME_MEMBERS = frozenset({"ID", "DLC", "pack", "unpack"})
# Стандартные скорости классического CAN, бит/с (33,3 и 83,3 кбит/с — GMLAN и низкоскоростные шины).
STANDARD_BITRATES = frozenset({10_000, 20_000, 33_333, 50_000, 83_333, 100_000, 125_000, 250_000,
                               500_000, 800_000, 1_000_000})
BUS_LOAD_LIMIT = 70  # %, порог предупреждения о загрузке шины
# Длина данных служебных кадров CANopen по CiA 301. EMCY не проверяется: CiA 301 требует 8 байт,
# но многие устройства передают укороченный кадр, и это не мешает его приёму.
# Широковещательные службы CANopen: получателей у них не перечисляют.
BROADCAST_TYPES = frozenset({"nmt", "sync", "time", "emcy", "heartbeat"})

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
    "canopen-dlc": ("warning", N_("DLC служебного кадра CANopen не соответствует CiA 301")),
    "bitrate-nonstandard": ("warning", N_("Нестандартная скорость шины")),
    "bus-load": ("warning", N_("Расчётная загрузка шины циклическими кадрами выше 70 %")),
    "duplicate-signal-name": ("error", N_("Повтор имени сигнала/флага в кадре")),
    "reserved-identifier": ("error", N_("Имя совпадает с ключевым словом C/Python или членом "
                                        "сгенерированного класса")),
    "name-collision": ("error", N_("Имена совпадают в сгенерированном коде (различаются только регистром "
                                   "или совпадают со свойством _phys)")),
    "signal-out-of-frame": ("error", N_("Сигнал выходит за пределы DLC")),
    "bit-overlap": ("error", N_("Пересечение сигналов по битам (с учётом мультиплексирования)")),
    "enum-overflow": ("error", N_("Значение enum не помещается в разрядность поля")),
    "duplicate-enum-name": ("warning", N_("Одинаковое имя у разных значений enum")),
    "encoding-field": ("error", N_("Поле не применимо к кодированию сигнала")),
    "flag-out-of-field": ("error", N_("Флаг выходит за пределы битового поля")),
    "flag-overlap": ("error", N_("Пересечение флагов внутри битового поля")),
    "flag-length": ("warning", N_("Сигнал типа flag длиной больше 1 бита")),
    "zero-factor": ("error", N_("Нулевой масштаб")),
    "range-overflow": ("warning", N_("min/max вне диапазона, представимого полем")),
    "min-max": ("error", N_("min больше max")),
    "invalid-in-range": ("warning", N_("Значение invalid попадает в рабочий диапазон min..max")),
    "missing-unit": ("info", N_("Физическая величина без единицы измерения")),
    "mux-no-selector": ("error", N_("Мультиплексированный сигнал в кадре без селектора")),
    "mux-multiple-selectors": ("error", N_("Больше одного селектора в кадре")),
    "mux-value-overflow": ("error", N_("Значение mux не помещается в селектор")),
    "mux-value-unknown": ("warning", N_("Значения mux нет в таблице значений селектора")),
    "mux-selector-muxed": ("error", N_("Селектор сам мультиплексирован")),
    "cycle-unexpected": ("error", N_("cycle_ms задан вместе с trigger")),
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
    "unknown-sender": ("error", N_("Отправитель кадра не описан на шине")),
    "sender-mismatch": ("warning", N_("sender противоречит направлению кадра или совпадает с получателем")),
    "rx-duplicate": ("error", N_("RX-кадр повторяет кадр другого устройства (описывайте кадр у отправителя)")),
    "rx-no-sender": ("info", N_("RX-кадр без отправителя")),
    "no-receivers": ("info", N_("У кадра нет получателей на шине")),
    "duplicate-short": ("warning", N_("Повтор короткого обозначения устройства на шине")),
    "history-version": ("warning", N_("Версия документа не совпадает с последней записью истории")),
    "float-length": ("error", N_("Сигнал float должен быть 32 или 64 бита")),
    "initial-range": ("warning", N_("Значение по умолчанию вне диапазона сигнала")),
    "invalid-overflow": ("error", N_("Значение invalid не помещается в разрядность сигнала")),
    "logo-missing": ("warning", N_("Файл логотипа не найден")),
    "logo-format": ("error", N_("Неподдерживаемый формат логотипа")),
    "signed-code": ("info", N_("Код знакового числа не выражается в DBC "
                               "или задан у беззнакового сигнала")),
    "missing-description": ("info", N_("Нет описания сигнала")),
    "missing-title": ("info", N_("Нет полного названия шины или устройства")),
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

    hist = cmap.document.history
    if hist and hist[0].version != cmap.document.version:
        ctx.emit("history-version", _("версия документа {version!r}, а последняя запись истории — {latest!r}",
                                      version=cmap.document.version, latest=hist[0].version),
                 ("document", "version"))

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
    if bus.bitrate is not None and bus.bitrate not in STANDARD_BITRATES:
        ctx.emit("bitrate-nonstandard", _("скорость {bitrate} бит/с не входит в стандартный ряд "
                                          "(125000, 250000, 500000, 1000000…)", bitrate=bus.bitrate),
                 bus._path + ("bitrate",))
    if bus.title is None:
        ctx.emit("missing-title", _("у шины {name!r} нет названия (title)", name=bus.name), bus._path + ("title",))
    names, nodes, addrs, shorts = {}, {}, {}, {}
    for dev in bus.devices:
        if dev.title is None:
            ctx.emit("missing-title", _("у устройства {name!r} нет полного названия (title)", name=dev.name),
                     dev._path + ("title",))
        if dev.short:
            if dev.short in shorts:
                ctx.emit("duplicate-short", _("обозначение {short!r} уже у устройства {other!r}",
                                              short=dev.short, other=shorts[dev.short]), dev._path + ("short",))
            shorts.setdefault(dev.short, dev.name)
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

    frame_names, ids, upper = {}, {}, {}
    for frame in bus.all_frames():
        p = frame._path
        if frame.name in frame_names:
            ctx.emit("duplicate-frame-name", _("кадр {name!r} уже описан на шине", name=frame.name), p + ("name",))
        elif frame.name.upper() in upper:
            ctx.emit("name-collision", _("кадр {name!r} отличается от {other!r} только регистром: "
                                         "в C-коде их макросы совпадут", name=frame.name,
                                         other=upper[frame.name.upper()]), p + ("name",))
        frame_names[frame.name] = frame
        upper.setdefault(frame.name.upper(), frame.name)
        if frame.can_id is None:
            if bus.protocol == "j1939":
                # Сообщение — на поле, которое нужно заполнить (редактор подсвечивает его)
                if frame.pgn is None:
                    ctx.emit("frame-id-missing", _("кадр {name!r}: {why}", name=frame.name,
                                                   why=_("нужен pgn (или id)")), p + ("pgn",))
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
            twin = _rx_twin(frame, other)
            if twin is not None:
                rx, tx = twin
                ctx.emit("rx-duplicate",
                         _("RX-кадр {name!r} устройства {device!r} повторяет кадр {other!r} отправителя {sender!r} "
                           "(CAN ID {can_id:#05x}): опишите кадр один раз у отправителя и добавьте {device!r} "
                           "в receivers", name=rx.name, device=rx.device.name, other=tx.name,
                           sender=tx.sender_name, can_id=frame.can_id), rx._path)
            else:
                ctx.emit("duplicate-can-id",
                         _("CAN ID {can_id:#05x} кадра {name!r} совпадает с кадром {other!r}",
                           can_id=frame.can_id, name=frame.name, other=other.name),
                         p + (("id",) if frame.id is not None else ("type",)))
        else:
            ids[frame.can_id] = frame
        if frame.can_id > 0x7FF and not frame.extended:
            ctx.emit("can-id-range", _("CAN ID {can_id:#x} > 0x7FF", can_id=frame.can_id), p + ("id",))
    _check_bus_load(ctx, bus)


def _frame_bits(dlc: int, extended: bool) -> int:
    """Длина кадра классического CAN в битах с худшим случаем бит-стаффинга (Davis et al., 2007)."""
    n = 8 * dlc
    return n + 67 + (54 + n - 1) // 4 if extended else n + 47 + (34 + n - 1) // 4


def _check_bus_load(ctx: _Ctx, bus) -> None:
    # У CAN FD фаза данных идёт на другой скорости, которой нет в карте, — оценка была бы неверной.
    if bus.fd or not bus.bitrate:
        return
    cyclic = [f for f in bus.all_frames()
              if f.can_id is not None and f.cycle_ms and f.trigger is None]
    bits_per_s = sum(_frame_bits(f.dlc, f.extended) * 1000 / f.cycle_ms for f in cyclic)
    load = 100 * bits_per_s / bus.bitrate
    if load > BUS_LOAD_LIMIT:
        ctx.emit("bus-load", _("расчётная загрузка шины {bus!r} — {load:.0f} % (циклических кадров: {count}, "
                               "{bitrate} бит/с), рекомендуется не больше {limit} %",
                               bus=bus.name, load=load, count=len(cyclic), bitrate=bus.bitrate,
                               limit=BUS_LOAD_LIMIT), bus._path + ("bitrate",))


def _rx_twin(a: Frame, b: Frame) -> tuple[Frame, Frame] | None:
    """Пара (RX-кадр устройства, тот же кадр у его отправителя) — один кадр, описанный дважды."""
    for rx, tx in ((a, b), (b, a)):
        if (rx.device is not None and rx.direction == "rx"
                and tx.sender_name is not None and tx.sender_name != rx.device.name):
            return rx, tx
    return None


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
    allowed = CANOPEN_DLC.get(frame.type)
    if bus.protocol == "canopen" and allowed and frame.dlc not in allowed:
        ctx.emit("canopen-dlc", _("кадр {type} по CiA 301 имеет DLC {expected}, указано {dlc}",
                                  type=frame.type, expected=" / ".join(map(str, sorted(allowed))), dlc=frame.dlc),
                 p + ("dlc",))
    devices = {d.name for d in bus.devices}
    for i, r in enumerate(frame.receivers):
        if r not in devices:
            ctx.emit("unknown-receiver", _("получатель {name!r} не описан на шине {bus!r}", name=r, bus=bus.name),
                     p + ("receivers", i))
    dev = frame.device
    if frame.sender is not None:
        if frame.sender not in devices:
            ctx.emit("unknown-sender", _("отправитель {name!r} не описан на шине {bus!r}",
                                         name=frame.sender, bus=bus.name), p + ("sender",))
        elif dev is not None and frame.direction == "tx" and frame.sender != dev.name:
            ctx.emit("sender-mismatch", _("кадр {name!r} передаёт само устройство {device!r} (TX), "
                                          "sender {sender!r} противоречит направлению",
                                          name=frame.name, device=dev.name, sender=frame.sender), p + ("sender",))
        elif dev is not None and frame.direction == "rx" and frame.sender == dev.name:
            ctx.emit("sender-mismatch", _("устройство {device!r} принимает кадр {name!r} (RX) "
                                          "и не может быть его отправителем",
                                          name=frame.name, device=dev.name), p + ("sender",))
    snd = frame.sender_name
    for i, r in enumerate(frame.receivers):
        if r == snd:
            ctx.emit("sender-mismatch", _("отправитель {name!r} указан среди получателей кадра", name=r),
                     p + ("receivers", i))
    if (dev is not None and snd is not None and not frame.receiver_names and len(devices) > 1
            and frame.type not in BROADCAST_TYPES):
        ctx.emit("no-receivers", _("кадр {name!r} никто не принимает: укажите получателей в receivers",
                                   name=frame.name), p + ("receivers",))
    if dev is not None and frame.direction == "rx" and frame.sender is None and fc is None and len(devices) > 1:
        ctx.emit("rx-no-sender", _("RX-кадр {name!r} без отправителя: если он описан на шине, укажите sender "
                                   "или перенесите кадр к отправителю и добавьте {device!r} в receivers",
                                   name=frame.name, device=dev.name), p + ("sender",))
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

    if frame.cycle_ms is not None and frame.trigger is not None:
        ctx.emit("cycle-unexpected", _("cycle_ms задан у кадра с trigger: {trigger}", trigger=frame.trigger),
                 p + ("cycle_ms",))

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
    upper: dict[str, str] = {}
    phys = {s.name + "_phys": s.name for s in sigs if s.factor != 1 or s.offset != 0 or s.encoding == "scaled"}
    for s in sigs:
        if s.name in C_KEYWORDS or s.name in PY_KEYWORDS:
            ctx.emit("reserved-identifier", _("имя сигнала {name!r} — ключевое слово C/Python: "
                                              "сгенерированный код не скомпилируется", name=s.name),
                     s._path + ("name",))
        elif s.name in PY_FRAME_MEMBERS:
            ctx.emit("reserved-identifier", _("имя сигнала {name!r} совпадает с членом класса кадра "
                                              "в Python-модуле ({members})", name=s.name,
                                              members=", ".join(sorted(PY_FRAME_MEMBERS))),
                     s._path + ("name",))
        if s.name in phys:
            ctx.emit("name-collision", _("сигнал {name!r} совпадает со свойством физического значения "
                                         "сигнала {other!r} в Python-модуле", name=s.name, other=phys[s.name]),
                     s._path + ("name",))
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
                if name.upper() in upper:
                    ctx.emit("name-collision", _("{name!r} отличается от {other!r} только регистром: "
                                                 "в C-коде их макросы совпадут", name=name,
                                                 other=upper[name.upper()]), path)
                upper.setdefault(name.upper(), name)

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

        lo, hi = B.raw_range(s.bit_length, s.signed, s.signed_code)
        for v, ev in enum_entries(s.values):
            _ident(ctx, ev.name, _("имя значения"), sp + ("values", v), lint.value_name)
            if not lo <= v <= hi:
                msg = (_("значение {value} ({name}) не помещается в {bits} бит (знаковое: {lo}..{hi})") if s.signed
                       else _("значение {value} ({name}) не помещается в {bits} бит (беззнаковое: {lo}..{hi})"))
                ctx.emit("enum-overflow", msg.format(value=v, name=ev.name, bits=s.bit_length, lo=lo, hi=hi),
                         sp + ("values", v))
        _dup_enum_names(ctx, s.values, sp)

        for key in _misplaced_fields(s):
            ctx.emit("encoding-field", _("{key} не применяется при encoding: {encoding}", key=key, encoding=s.encoding),
                     sp + (key,))
        if s.encoding == "flag" and s.bit_length != 1:
            ctx.emit("flag-length", _("сигнал-флаг {name!r} длиной {bits} бит", name=s.name, bits=s.bit_length),
                     sp + ("bit_length",))
        _check_flags(ctx, s)

        if s.factor == 0:
            ctx.emit("zero-factor", "factor = 0", sp + ("factor",))
        elif s.encoding == "scaled":
            phys = sorted((lo * s.factor + s.offset, hi * s.factor + s.offset))
            if s.min is not None and s.max is not None and s.min > s.max:
                ctx.emit("min-max", _("min {min} > max {max}", min=s.min, max=s.max), sp + ("min",))
            for k in ("min", "max"):
                val = getattr(s, k)
                if val is not None and not phys[0] - 1e-9 <= val <= phys[1] + 1e-9:
                    ctx.emit("range-overflow",
                             _("{key} = {value:g} вне представимого диапазона {lo:g}..{hi:g} {unit}",
                               key=k, value=val, lo=phys[0], hi=phys[1], unit=s.unit or "").rstrip(), sp + (k,))

        if s.encoding == "float" and s.bit_length not in (32, 64):
            ctx.emit("float-length", _("сигнал {name!r}: float — 32 или 64 бита, задано {bits}",
                                       name=s.name, bits=s.bit_length), sp + ("bit_length",))
        if s.encoding == "scaled" and not s.unit and (s.factor != 1 or s.offset != 0):
            ctx.emit("missing-unit", _("у физической величины {name!r} не указана единица (unit)", name=s.name),
                     sp + ("unit",))
        raw_lo, raw_hi = (lo, hi) if s.encoding != "float" else (None, None)
        for v in s.invalid_values:
            if raw_lo is not None and not raw_lo <= v <= raw_hi:
                ctx.emit("invalid-overflow", _("invalid = {value} не помещается в {bits} бит ({lo}..{hi})",
                                               value=v, bits=s.bit_length, lo=raw_lo, hi=raw_hi), sp + ("invalid",))
            elif raw_lo is not None and s.min is not None and s.max is not None and s.factor != 0:
                pv = v * s.factor + s.offset
                if s.min - 1e-9 <= pv <= s.max + 1e-9:
                    ctx.emit("invalid-in-range",
                             _("invalid = {value} соответствует {phys:g} в пределах min..max: "
                               "приёмник не отличит «нет данных» от реального значения",
                               value=v, phys=pv), sp + ("invalid",))
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
            ctx.emit("signed-code", _("{name!r}: DBC хранит знаковые значения только в дополнительном коде, "
                                      "в DBC-файле сигнал будет прочитан иначе", name=s.name), sp + ("signed_code",))

        if s.mux is not None:
            if selector is None:
                ctx.emit("mux-no-selector", _("у сигнала {name!r} задан mux, но в кадре нет multiplexer", name=s.name),
                         sp + ("mux",))
            else:
                slo, shi = B.raw_range(selector.bit_length, selector.signed, selector.signed_code)
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
    seen, upper = {}, {}
    for v, ev in enum_entries(values):
        if ev.name in PY_KEYWORDS:
            ctx.emit("reserved-identifier", _("имя значения {name!r} — ключевое слово Python: "
                                              "сгенерированный модуль не загрузится", name=ev.name),
                     path + ("values", v))
        if ev.name in seen:
            ctx.emit("duplicate-enum-name", _("имя {name!r} у значений {a} и {b}", name=ev.name, a=seen[ev.name], b=v),
                     path + ("values", v))
        elif ev.name.upper() in upper:
            ctx.emit("name-collision", _("значение {name!r} отличается от {other!r} только регистром: "
                                         "в C-коде их макросы совпадут", name=ev.name, other=upper[ev.name.upper()]),
                     path + ("values", v))
        seen[ev.name] = v
        upper.setdefault(ev.name.upper(), ev.name)


# Кодирования, к которым применимо поле сигнала (поле задано, если отличается от значения по умолчанию)
ENCODING_FIELDS = {
    "factor": ("scaled", "float"),
    "offset": ("scaled", "float"),
    "unit": ("raw", "scaled", "float"),
    "min": ("raw", "scaled", "float"),
    "max": ("raw", "scaled", "float"),
    "values": ("enum", "flag"),
    "flags": ("bitfield",),
    "signed": ("raw", "scaled", "enum"),
    "signed_code": ("raw", "scaled", "enum"),
    "invalid": ("raw", "scaled", "enum"),
    "initial": ("raw", "scaled", "enum", "flag", "float"),
}


def _misplaced_fields(s: Signal) -> list[str]:
    """Поля сигнала, которые заданы, но не применяются при его кодировании."""
    defaults = {k: Signal.model_fields[k].default for k in ENCODING_FIELDS}
    return [k for k, allowed in ENCODING_FIELDS.items()
            if s.encoding not in allowed and getattr(s, k) not in (defaults[k], None, [], {})]


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
