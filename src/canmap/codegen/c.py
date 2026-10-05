"""Генерация C-кода: ID кадров, enum значений, маски флагов, структуры и pack/unpack.

Код не использует динамическую память и стандартную библиотеку, кроме
<stdint.h>, <stdbool.h>, <stddef.h>; пригоден для bare-metal, FreeRTOS, Zephyr.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Bus, CanMap, Frame, Signal, enum_entries, text
from .common import frames_with_layout, is_byte_array, num, physical, selector_of, storage_bits

HELPERS = r"""
#ifndef CANMAP_BITS_HELPERS
#define CANMAP_BITS_HELPERS
/* Нумерация бит lsb0: бит p — бит (p % 8) байта (p / 8); start — позиция LSB.
 * big-endian (Motorola): после старшего бита байта цепочка продолжается
 * с бита 0 предыдущего байта. */
static inline uint64_t canmap_get_bits(const uint8_t *data, uint16_t start, uint8_t length, bool big_endian)
{
    uint64_t value = 0u;
    uint8_t done = 0u;
    int16_t pos = (int16_t)start;
    while (done < length) {
        uint8_t byte = (uint8_t)(pos / 8);
        uint8_t shift = (uint8_t)(pos % 8);
        uint8_t n = (uint8_t)(8u - shift);
        if (n > (uint8_t)(length - done)) {
            n = (uint8_t)(length - done);
        }
        uint8_t chunk = (uint8_t)((data[byte] >> shift) & (uint8_t)((1u << n) - 1u));
        value |= (uint64_t)chunk << done;
        done = (uint8_t)(done + n);
        pos = big_endian ? (int16_t)((byte - 1) * 8) : (int16_t)((byte + 1) * 8);
    }
    return value;
}

static inline void canmap_set_bits(uint8_t *data, uint64_t value, uint16_t start, uint8_t length, bool big_endian)
{
    uint8_t done = 0u;
    int16_t pos = (int16_t)start;
    while (done < length) {
        uint8_t byte = (uint8_t)(pos / 8);
        uint8_t shift = (uint8_t)(pos % 8);
        uint8_t n = (uint8_t)(8u - shift);
        if (n > (uint8_t)(length - done)) {
            n = (uint8_t)(length - done);
        }
        uint8_t mask = (uint8_t)(((1u << n) - 1u) << shift);
        uint8_t chunk = (uint8_t)(((value >> done) << shift) & mask);
        data[byte] = (uint8_t)((data[byte] & (uint8_t)~mask) | chunk);
        done = (uint8_t)(done + n);
        pos = big_endian ? (int16_t)((byte - 1) * 8) : (int16_t)((byte + 1) * 8);
    }
}

static inline int64_t canmap_sign_extend(uint64_t value, uint8_t length)
{
    uint64_t sign = (uint64_t)1u << (length - 1u);
    return (int64_t)((value ^ sign) - sign);
}

static inline float canmap_round_f(float x)
{
    return (x >= 0.0f) ? (x + 0.5f) : (x - 0.5f);
}
#endif /* CANMAP_BITS_HELPERS */
"""


def _c_comment(s: str) -> str:
    return s.replace("*/", "* /").replace("\n", " ")


class CGen:
    def __init__(self, cmap: CanMap, bus: Bus, prefix: str = "", lang: str | None = None):
        self.cmap, self.bus = cmap, bus
        self.lang = lang or cmap.lang
        self.prefix = prefix
        self.base = (prefix + bus.name).lower() if prefix else bus.name.lower()

    def t(self, v) -> str:
        return _c_comment(text(v, self.lang))

    def P(self, *parts: str) -> str:
        """Имя макроса: PREFIX_PART1_PART2."""
        return "_".join(x for x in (self.prefix.rstrip("_"), *parts) if x).upper()

    def p(self, *parts: str) -> str:
        return "_".join(x for x in (self.prefix.rstrip("_"), *parts) if x).lower()

    @staticmethod
    def ctype(s: Signal) -> str:
        return ("int" if s.signed else "uint") + f"{storage_bits(s)}_t"

    # ------------------------------------------------------------------ #

    def header(self) -> str:
        guard = f"{self.base.upper()}_CANMAP_H"
        d = self.cmap.document
        out = [
            f"/* {self.base}.h — сгенерировано canmap из карты «{_c_comment(text(d.title, self.lang))}»",
            f" * версии {d.version}. Не редактируйте вручную: источник — YAML-карта. */",
            f"#ifndef {guard}",
            f"#define {guard}",
            "",
            "#include <stdbool.h>",
            "#include <stddef.h>",
            "#include <stdint.h>",
            "",
            "#ifdef __cplusplus",
            'extern "C" {',
            "#endif",
            HELPERS,
        ]
        if self.bus.bitrate:
            out.append(f"#define {self.P(self.bus.name, 'BITRATE')} {self.bus.bitrate}u")
        for dev in self.bus.devices:
            if dev.node_id is not None:
                out.append(f"#define {self.P(dev.name, 'NODE_ID')} 0x{dev.node_id:02X}u")
        out.append("")
        for f in frames_with_layout(self.bus):
            out += self.frame_decls(f)
        out += ["#ifdef __cplusplus", "}", "#endif", "", f"#endif /* {guard} */", ""]
        return "\n".join(out)

    def frame_decls(self, f: Frame) -> list[str]:
        F = f.name
        out = [
            "/* " + "-" * 72 + " */",
            f"/* {F}: {self.t(f.description) or self.t(f.title)} */",
            f"#define {self.P(F, 'ID')} 0x{f.can_id:03X}u",
            f"#define {self.P(F, 'DLC')} {f.dlc}u",
        ]
        if f.extended:
            out.append(f"#define {self.P(F, 'IS_EXTENDED')} 1")
        if f.transmission and f.transmission.cycle_ms:
            out.append(f"#define {self.P(F, 'CYCLE_MS')} {f.transmission.cycle_ms}u")
        out.append("")

        for s in f.layout:
            S = s.name
            entries = enum_entries(s.values)
            if entries:
                out.append(f"/* {S}: {self.t(s.description)} */")
                out.append("typedef enum {")
                for v, ev in entries:
                    d = self.t(ev.description)
                    out.append(f"    {self.P(F, S, ev.name)} = {v},{' /* ' + d + ' */' if d else ''}")
                out.append(f"}} {self.p(F, S)}_t;")
                out.append("")
            for fl in s.flags or []:
                mask = ((1 << fl.bit_length) - 1) << fl.bit
                d = self.t(fl.description)
                out.append(f"#define {self.P(F, S, fl.name, 'SHIFT')} {fl.bit}u")
                out.append(f"#define {self.P(F, S, fl.name, 'MASK')} 0x{mask:X}u{' /* ' + d + ' */' if d else ''}")
                for v, ev in enum_entries(fl.values):
                    out.append(f"#define {self.P(F, S, fl.name, ev.name)} {v}u")
            if s.flags:
                out.append("")
            if physical(s) and not is_byte_array(s):
                T = self.ctype(s)
                lo = -(1 << (s.bit_length - 1)) if s.signed else 0
                hi = (1 << (s.bit_length - 1)) - 1 if s.signed else (1 << s.bit_length) - 1
                fn = self.p(F, S)
                out += [
                    f"#define {self.P(F, S, 'FACTOR')} ({num(s.factor)}f)",
                    f"#define {self.P(F, S, 'OFFSET')} ({num(s.offset)}f)",
                ]
                if s.unit:
                    out.append(f"/* {S}: единица измерения — {_c_comment(s.unit)} */")
                out += [
                    f"static inline float {fn}_to_phys({T} raw)",
                    "{",
                    f"    return (float)raw * {self.P(F, S, 'FACTOR')} + {self.P(F, S, 'OFFSET')};",
                    "}",
                    f"static inline {T} {fn}_from_phys(float phys)",
                    "{",
                    f"    float r = canmap_round_f((phys - {self.P(F, S, 'OFFSET')}) / {self.P(F, S, 'FACTOR')});",
                    f"    if (r < {float(lo)!r}f) {{ r = {float(lo)!r}f; }}",
                    f"    if (r > {float(hi)!r}f) {{ r = {float(hi)!r}f; }}",
                    f"    return ({T})r;",
                    "}",
                    "",
                ]

        out.append("typedef struct {")
        if not f.layout:
            out.append("    uint8_t reserved_; /* сигналы не описаны */")
        for s in f.layout:
            d = self.t(s.description)
            if is_byte_array(s):
                out.append(f"    uint8_t {s.name}[{s.bit_length // 8}];{' /* ' + d + ' */' if d else ''}")
            else:
                unit = f" [{_c_comment(s.unit)}]" if s.unit else ""
                out.append(f"    {self.ctype(s)} {s.name};{' /* ' + d + unit + ' */' if d or unit else ''}")
        out.append(f"}} {self.p(F)}_t;")
        out.append("")
        out.append("/* Упаковать: возвращает DLC или -1, если буфер меньше DLC. */")
        out.append(f"int {self.p(F)}_pack(uint8_t *data, size_t size, const {self.p(F)}_t *msg);")
        out.append("/* Распаковать: возвращает 0 или -1, если данных меньше DLC. */")
        out.append(f"int {self.p(F)}_unpack({self.p(F)}_t *msg, const uint8_t *data, size_t size);")
        out.append("")
        return out

    # ------------------------------------------------------------------ #

    def source(self) -> str:
        out = [
            f"/* {self.base}.c — сгенерировано canmap. Не редактируйте вручную. */",
            f'#include "{self.base}.h"',
            "",
        ]
        for f in frames_with_layout(self.bus):
            out += self.frame_impl(f)
        return "\n".join(out)

    def _guard(self, s: Signal, sel: Signal | None, body: list[str]) -> list[str]:
        if s.mux is None or sel is None:
            return body
        cond = " || ".join(f"msg->{sel.name} == {v}" for v in s.mux_values)
        return [f"    if ({cond}) {{"] + ["    " + b for b in body] + ["    }"]

    def frame_impl(self, f: Frame) -> list[str]:
        name = self.p(f.name)
        sel = selector_of(f)
        be = lambda s: "true" if s.byte_order == "big_endian" else "false"  # noqa: E731
        if f.dlc == 0:
            return [
                f"int {name}_pack(uint8_t *data, size_t size, const {name}_t *msg)",
                "{", "    (void)data;", "    (void)size;", "    return (msg == NULL) ? -1 : 0;", "}", "",
                f"int {name}_unpack({name}_t *msg, const uint8_t *data, size_t size)",
                "{", "    (void)data;", "    (void)size;", "    if (msg == NULL) {", "        return -1;", "    }",
                "    msg->reserved_ = 0u;", "    return 0;", "}", "",
            ]
        pack = [
            f"int {name}_pack(uint8_t *data, size_t size, const {name}_t *msg)",
            "{",
            f"    if (data == NULL || msg == NULL || size < {f.dlc}u) {{",
            "        return -1;",
            "    }",
            f"    for (size_t i = 0u; i < {f.dlc}u; i++) {{",
            "        data[i] = 0u;",
            "    }",
        ]
        unpack = [
            f"int {name}_unpack({name}_t *msg, const uint8_t *data, size_t size)",
            "{",
            f"    if (data == NULL || msg == NULL || size < {f.dlc}u) {{",
            "        return -1;",
            "    }",
        ]
        # Селектор распаковывается первым — от него зависят остальные сигналы.
        order = sorted(f.layout, key=lambda s: not s.multiplexer)
        if not f.layout:
            unpack.append("    msg->reserved_ = 0u;")
        for s in order:
            if is_byte_array(s):
                n, b0 = s.bit_length // 8, s.start_bit // 8
                pack += self._guard(s, sel, [
                    f"    for (size_t i = 0u; i < {n}u; i++) {{",
                    f"        data[{b0}u + i] = msg->{s.name}[i];",
                    "    }"])
                unpack += self._guard(s, sel, [
                    f"    for (size_t i = 0u; i < {n}u; i++) {{",
                    f"        msg->{s.name}[i] = data[{b0}u + i];",
                    "    }"])
                continue
            T = self.ctype(s)
            pack += self._guard(s, sel, [
                f"    canmap_set_bits(data, (uint64_t)msg->{s.name}, {s.start_bit}u, {s.bit_length}u, {be(s)});"])
            get = f"canmap_get_bits(data, {s.start_bit}u, {s.bit_length}u, {be(s)})"
            if s.signed:
                get = f"canmap_sign_extend({get}, {s.bit_length}u)"
            unpack += self._guard(s, sel, [f"    msg->{s.name} = ({T}){get};"])
        pack += [f"    return {f.dlc};", "}", ""]
        unpack += ["    return 0;", "}", ""]
        return pack + unpack


def generate_c(cmap: CanMap, out_dir: str | Path, prefix: str = "", buses: list[str] | None = None) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for bus in cmap.buses:
        if buses and bus.name not in buses:
            continue
        g = CGen(cmap, bus, prefix)
        h, c = out / f"{g.base}.h", out / f"{g.base}.c"
        h.write_text(g.header(), encoding="utf-8")
        c.write_text(g.source(), encoding="utf-8")
        written += [h, c]
    return written
