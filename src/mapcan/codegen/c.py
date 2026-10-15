"""C code generation: frame IDs, value enums, flag masks, structs and pack/unpack.

The code uses no dynamic memory and no standard library beyond
<stdint.h>, <stdbool.h>, <stddef.h> and memcpy from <string.h>; it fits bare metal, FreeRTOS, Zephyr,
and compiles as C99 and as C++.
"""

from __future__ import annotations

import zlib
from collections import Counter
from pathlib import Path

from .. import bits as B
from ..i18n import _
from ..layout import layout_crc32
from ..model import Bus, Frame, MapCan, Signal, enum_entries, text
from ..units import translate_unit
from .common import code_text, frames_with_layout, is_byte_array, num, physical, raw_limits, selector_of, storage_bits

HELPERS = r"""
#ifndef MAPCAN_BITS_HELPERS
#define MAPCAN_BITS_HELPERS @REVISION@
@BITS_NOTE@
static inline uint64_t mapcan_get_bits(const uint8_t *data, uint16_t start, uint8_t length, bool big_endian)
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

static inline void mapcan_set_bits(uint8_t *data, uint64_t value, uint16_t start, uint8_t length, bool big_endian)
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

@CLAMP_NOTE@
static inline uint64_t mapcan_clamp_u(uint64_t value, uint64_t hi)
{
    return value > hi ? hi : value;
}
static inline int64_t mapcan_clamp_s(int64_t value, int64_t lo, int64_t hi)
{
    return value < lo ? lo : (value > hi ? hi : value);
}

static inline int64_t mapcan_sign_extend(uint64_t value, uint8_t length)
{
    uint64_t sign = (uint64_t)1u << (length - 1u);
    return (int64_t)((value ^ sign) - sign);
}
static inline int32_t mapcan_sign_extend32(uint32_t value, uint8_t length)
{
    uint32_t sign = (uint32_t)1u << (length - 1u);
    return (int32_t)((value ^ sign) - sign);
}

@ONES_NOTE@
static inline int64_t mapcan_ones_decode(uint64_t value, uint8_t length)
{
    uint64_t sign = (uint64_t)1u << (length - 1u);
    return (value & sign) ? -(int64_t)(~value & (sign - 1u)) : (int64_t)value;
}
static inline uint64_t mapcan_ones_encode(int64_t value)
{
    return value < 0 ? ~(uint64_t)(-value) : (uint64_t)value;
}

@SM_NOTE@
static inline int64_t mapcan_sm_decode(uint64_t value, uint8_t length)
{
    uint64_t sign = (uint64_t)1u << (length - 1u);
    return (value & sign) ? -(int64_t)(value & (sign - 1u)) : (int64_t)value;
}
static inline uint64_t mapcan_sm_encode(int64_t value, uint8_t length)
{
    return value < 0 ? (((uint64_t)1u << (length - 1u)) | (uint64_t)(-value)) : (uint64_t)value;
}

@IEEE_NOTE@
static inline uint32_t mapcan_f32_to_bits(float f)
{
    uint32_t u;
    memcpy(&u, &f, sizeof u);
    return u;
}
static inline float mapcan_bits_to_f32(uint32_t u)
{
    float f;
    memcpy(&f, &u, sizeof f);
    return f;
}
static inline uint64_t mapcan_f64_to_bits(double f)
{
    uint64_t u;
    memcpy(&u, &f, sizeof u);
    return u;
}
static inline double mapcan_bits_to_f64(uint64_t u)
{
    double f;
    memcpy(&f, &u, sizeof f);
    return f;
}

static inline float mapcan_round_f(float x)
{
    return (x >= 0.0f) ? (x + 0.5f) : (x - 0.5f);
}

static inline double mapcan_round_d(double x)
{
    return (x >= 0.0) ? (x + 0.5) : (x - 0.5);
}

@TABLES_NOTE@
typedef struct {
    uint32_t id;
    uint16_t length;
    bool extended;
    bool fd;
    uint32_t cycle_ms;
    bool on_event;
    uint32_t inhibit_us;
} mapcan_tx_entry_t;
typedef struct {
    uint32_t id;
    uint16_t length;
    bool extended;
    bool fd;
    uint32_t cycle_ms;
    uint32_t timeout_ms;
} mapcan_rx_entry_t;
typedef struct {
    uint32_t id;
    uint32_t mask;
    bool extended;
} mapcan_filter_t;
#elif MAPCAN_BITS_HELPERS != @REVISION@
@MISMATCH@
#endif /* MAPCAN_BITS_HELPERS */
"""
# The helpers' revision: headers of different mapcan versions with different helpers do not build together
HELPERS_REVISION = f"0x{zlib.crc32(HELPERS.encode()):08X}u"


def _c_int(v: int) -> str:
    return f"{v}u" if v >= 0 else f"({v})"


def _c_bound(v: int) -> str:
    """Integer literal of a bound; INT64_MIN cannot be written as a literal directly."""
    return f"({v + 1} - 1)" if v == -(1 << 63) else _c_int(v)


def _c_signed(v: int) -> str:
    """A signed int64_t literal; INT64_MIN is never needed (a clamp at the type's limit is left out)."""
    return f"({v}LL)" if v < 0 else f"{v}LL"


def _c_bool(v) -> str:
    return "true" if v else "false"


def _c_comment(s: str) -> str:
    return s.replace("*/", "* /").replace("\n", " ")


PHYS_TYPES = ("float", "double")


class CGen:
    def __init__(self, cmap: MapCan, bus: Bus, prefix: str = "", lang: str | None = None,
                 phys_type: str = "float"):
        """``phys_type``: the type of physical values of scaled signals: float (double only where float cannot
        hold the raw values exactly), or double for all of them (MCUs with a double-precision FPU, test
        benches)."""
        if phys_type not in PHYS_TYPES:
            raise ValueError(phys_type)
        self.cmap, self.bus = cmap, bus
        self.phys_type = phys_type
        self.lang = lang or cmap.lang
        self.T = code_text(self.lang)
        self.prefix = prefix
        self.base = (prefix + bus.name).lower() if prefix else bus.name.lower()
        # Names are unique only within a bus: a frame or device whose name is also on another bus
        # is qualified by its bus, so the headers of all buses build in one firmware (a gateway).
        frames = Counter(f.name for b in cmap.buses for f in frames_with_layout(b))
        devices = Counter(d.name for b in cmap.buses for d in b.devices if d.node_id is not None)
        self._shared_frames = {n for n, k in frames.items() if k > 1}
        self._shared_devices = {n for n, k in devices.items() if k > 1}

    def frame_name(self, f: Frame) -> str:
        """The frame's name in identifiers: <frame>, or <bus>_<frame> if another bus has a frame of that name."""
        return f"{self.bus.name}_{f.name}" if f.name in self._shared_frames else f.name

    def device_name(self, name: str) -> str:
        return f"{self.bus.name}_{name}" if name in self._shared_devices else name

    def t(self, v) -> str:
        return _c_comment(text(v, self.lang, self.cmap.lang))

    def P(self, *parts: str) -> str:
        """Macro name: PREFIX_PART1_PART2."""
        return "_".join(x for x in (self.prefix.rstrip("_"), *parts) if x).upper()

    def p(self, *parts: str) -> str:
        return "_".join(x for x in (self.prefix.rstrip("_"), *parts) if x).lower()

    def frames(self) -> list[Frame]:
        """The frames of the generated code."""
        return frames_with_layout(self.bus)

    def packs(self, f: Frame) -> bool:
        """The frame gets pack() and from_phys() (it is sent)."""
        return True

    def unpacks(self, f: Frame) -> bool:
        """The frame gets unpack() and to_phys() (it is received)."""
        return True

    def extra_decls(self) -> list[str]:
        return []

    def extra_impl(self) -> list[str]:
        return []

    @staticmethod
    def ctype(s: Signal) -> str:
        if s.encoding == "float":
            return "double" if s.bit_length == 64 else "float"
        return ("int" if s.signed else "uint") + f"{storage_bits(s)}_t"

    # ------------------------------------------------------------------ #

    def header(self) -> str:
        guard = f"{self.base.upper()}_MAPCAN_H"
        d = self.cmap.document
        out = [
            self.T["c_header"].format(base=self.base, title=_c_comment(text(d.title, self.lang, self.cmap.lang)),
                                      version=d.version),
            f"#ifndef {guard}",
            f"#define {guard}",
            "",
            "#include <stdbool.h>",
            "#include <stddef.h>",
            "#include <stdint.h>",
            "#include <string.h>",
            "",
            "#ifdef __cplusplus",
            'extern "C" {',
            "#endif",
            HELPERS.replace("@BITS_NOTE@", self.T["bits_note"]).replace("@IEEE_NOTE@", self.T["ieee_note"])
            .replace("@CLAMP_NOTE@", self.T["clamp_c"]).replace("@MISMATCH@", self.T["helpers_mismatch"])
            .replace("@REVISION@", HELPERS_REVISION).replace("@TABLES_NOTE@", self.T["tables_note"])
            .replace("@ONES_NOTE@", self.T["ones_c"]).replace("@SM_NOTE@", self.T["sm_c"]),
        ]
        # The map this code was built from, named after the bus: headers of two maps build together
        crc = f"0x{layout_crc32(self.cmap):08X}u"
        consts = [(("MAP_VERSION", n), f"{v}u") for n, v in zip(("MAJOR", "MINOR", "PATCH"), d.version_parts or (),
                                                                strict=False)]
        consts.append((("MAP_LAYOUT_CRC32",), crc))
        for parts, v in consts:
            out.append(f"#define {self.P(self.bus.name, *parts)} {v}")
        # The former names without the bus (the same in every header of a map: identical redefinitions are allowed)
        out.append("#ifndef MAPCAN_NO_DEPRECATED")
        for parts, v in consts:
            out.append(f"#define {self.P(*parts)} {v} "
                       f"/* {self.T['deprecated_dlc'].format(name=self.P(self.bus.name, *parts))} */")
        out.append("#endif")
        if self.bus.bitrate:
            out.append(f"#define {self.P(self.bus.name, 'BITRATE')} {self.bus.bitrate}u")
        if self.bus.fd and self.bus.data_bitrate:
            out.append(f"#define {self.P(self.bus.name, 'DATA_BITRATE')} {self.bus.data_bitrate}u")
        for dev in self.bus.devices:
            if dev.node_id is not None:
                out.append(f"#define {self.P(self.device_name(dev.name), 'NODE_ID')} 0x{dev.node_id:02X}u")
        out.append("")
        for f in self.frames():
            out += self.frame_decls(f)
        out += self.extra_decls()
        out += ["#ifdef __cplusplus", "}", "#endif", "", f"#endif /* {guard} */", ""]
        return "\n".join(out)

    def frame_decls(self, f: Frame) -> list[str]:
        F = self.frame_name(f)
        out = [
            "/* " + "-" * 72 + " */",
            f"/* {F}: {self.t(f.description) or self.t(f.title)} */",
            f"#define {self.P(F, 'ID')} 0x{f.can_id:03X}u",
            f"#define {self.P(F, 'LENGTH')} {f.length}u",
            f"#define {self.P(F, 'DLC')} {self.P(F, 'LENGTH')} "
            f"/* {self.T['deprecated_dlc'].format(name=self.P(F, 'LENGTH'))} */",
        ]
        if f.extended:
            out.append(f"#define {self.P(F, 'IS_EXTENDED')} 1")
        if f.bit_rate_switch is not None:
            # How the CAN driver sends the frame: CAN FD, with or without the bit rate switch
            out.append(f"#define {self.P(F, 'IS_FD')} 1")
            out.append(f"#define {self.P(F, 'BRS')} {int(f.bit_rate_switch)}")
        if f.cycle_ms is not None:
            out.append(f"#define {self.P(F, 'CYCLE_MS')} {f.cycle_ms}u")
        if f.trigger == "event":
            # Sent on an event (with CYCLE_MS also every period)
            out.append(f"#define {self.P(F, 'ON_EVENT')} 1")
        if f.inhibit_ms is not None:
            # In microseconds: an integer also for CANopen's 0.1 ms steps
            out.append(f"#define {self.P(F, 'INHIBIT_US')} {round(f.inhibit_ms * 1000)}u")
        if f.timeout_ms is not None:
            out.append(f"#define {self.P(F, 'TIMEOUT_MS')} {f.timeout_ms}u")
        out.append("")

        for s in f.layout:
            S = s.name
            entries = enum_entries(s.values)
            if entries:
                out.append(f"/* {S}: {self.t(s.description) or self.t(s.title)} */")
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
            out += self.default_defines(F, s)
            if physical(s) and s.encoding == "float":
                T = self.ctype(s)
                sfx = "" if T == "double" else "f"
                fn = self.p(F, S)
                out += [
                    f"#define {self.P(F, S, 'FACTOR')} ({num(s.factor)}{sfx})",
                    f"#define {self.P(F, S, 'OFFSET')} ({num(s.offset)}{sfx})",
                ]
                if self.unpacks(f):
                    out += [f"static inline {T} {fn}_to_phys({T} raw)", "{",
                            f"    return raw * {self.P(F, S, 'FACTOR')} + {self.P(F, S, 'OFFSET')};", "}"]
                if self.packs(f):
                    out += [f"static inline {T} {fn}_from_phys({T} phys)", "{",
                            f"    return (phys - {self.P(F, S, 'OFFSET')}) / {self.P(F, S, 'FACTOR')};", "}"]
                out.append("")
            elif physical(s) and not is_byte_array(s):
                T = self.ctype(s)
                lo, hi = B.raw_range(s.bit_length, s.signed, s.signed_code)
                # float represents integers exactly only up to 2^24: long fields are computed in double.
                # The upper bound is compared with hi + 1 (a power of two, exact in any type),
                # otherwise hi would round up and fall outside the field's width.
                if s.bit_length > 24 or self.phys_type == "double":
                    FT, sfx, rnd = "double", "", "mapcan_round_d"
                else:
                    FT, sfx, rnd = "float", "f", "mapcan_round_f"
                fn = self.p(F, S)
                out += [
                    f"#define {self.P(F, S, 'FACTOR')} ({num(s.factor)}{sfx})",
                    f"#define {self.P(F, S, 'OFFSET')} ({num(s.offset)}{sfx})",
                ]
                if s.unit:
                    out.append(f"/* {S}: {self.T['unit']} — {_c_comment(translate_unit(s.unit, self.lang))} */")
                if self.unpacks(f):
                    out += [f"static inline {FT} {fn}_to_phys({T} raw)", "{",
                            f"    return ({FT})raw * {self.P(F, S, 'FACTOR')} + {self.P(F, S, 'OFFSET')};", "}"]
                if self.packs(f):
                    out += [
                        f"static inline {T} {fn}_from_phys({FT} phys)",
                        "{",
                        f"    {FT} r = {rnd}((phys - {self.P(F, S, 'OFFSET')}) / {self.P(F, S, 'FACTOR')});",
                        f"    if (r < {float(lo)!r}{sfx}) {{ return {_c_bound(lo)}; }}",
                        f"    if (r >= {float(hi + 1)!r}{sfx}) {{ return {_c_bound(hi)}; }}",
                        f"    return ({T})r;",
                        "}",
                    ]
                out.append("")

        out.append("typedef struct {")
        if not f.layout:
            out.append(f"    uint8_t reserved_; /* {self.T['no_signals']} */")
        for s in f.layout:
            d = self.t(s.description) or self.t(s.title)
            if is_byte_array(s):
                # A string is text of the charset, not NUL-terminated when it fills the field
                ctype = "char" if s.encoding == "string" else "uint8_t"
                out.append(f"    {ctype} {s.name}[{s.bit_length // 8}];{' /* ' + d + ' */' if d else ''}")
            else:
                unit = f" [{_c_comment(translate_unit(s.unit, self.lang))}]" if s.unit else ""
                out.append(f"    {self.ctype(s)} {s.name};{' /* ' + d + unit + ' */' if d or unit else ''}")
        out.append(f"}} {self.p(F)}_t;")
        out.append("")
        sel = selector_of(f)
        for s in f.layout:
            if s.mux is not None and sel is not None:
                cond = " || ".join(f"msg->{sel.name} == {v}" for v in s.mux_values)
                out.append(f"static inline int {self.p(F, s.name)}_is_active(const {self.p(F)}_t *msg) "
                           f"{{ return {cond}; }}")
        if sel is not None and any(s.mux is not None for s in f.layout):
            out.append("")
        out.append(f"/* {self.T['init']} */")
        out.append(f"extern const {self.p(F)}_t {self.P(F, 'INITIAL')};")
        out.append(f"void {self.p(F)}_init({self.p(F)}_t *msg);")
        if self.packs(f):
            out.append(f"/* {self.T['pack']} */")
            out.append(f"int {self.p(F)}_pack(uint8_t *data, size_t size, const {self.p(F)}_t *msg);")
        if self.unpacks(f):
            muxed = selector_of(f) is not None and any(s.mux is not None for s in f.layout)
            out.append(f"/* {self.T['unpack_mux' if muxed else 'unpack']} */")
            out.append(f"int {self.p(F)}_unpack({self.p(F)}_t *msg, const uint8_t *data, size_t size);")
        out.append("")
        return out

    def default_defines(self, F: str, s: Signal) -> list[str]:
        """#define for the initial value, "no data" and SPN (J1939)."""
        out = []
        if s.spn is not None:
            out.append(f"#define {self.P(F, s.name, 'SPN')} {s.spn}u")
        init = s.initial_raw
        if init is not None and not is_byte_array(s):
            if s.encoding == "float":
                sfx = "" if s.bit_length == 64 else "f"
                out.append(f"#define {self.P(F, s.name, 'INITIAL')} ({num(init)}{sfx})")
            else:
                out.append(f"#define {self.P(F, s.name, 'INITIAL_RAW')} {_c_int(init)}")
        inv = s.invalid_values
        for i, v in enumerate(inv):
            suffix = "INVALID_RAW" if len(inv) == 1 else f"INVALID_RAW_{i + 1}"
            out.append(f"#define {self.P(F, s.name, suffix)} {_c_int(v)}")
        # Raw values without a value, by meaning: <frame>_<signal>_is_not_available(raw), …_is_error(raw)
        bits = storage_bits(s)
        tmin, tmax = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if s.signed else (0, (1 << bits) - 1)
        # A literal of the signedness of the type: no -Wsign-compare warning

        def lit(v: int) -> str:
            return _c_signed(v) if s.signed and v > tmin else _c_bound(v)

        for meaning, ranges in s.invalid_ranges.items():
            conds = []
            for lo, hi in ranges:
                # A bound at the limit of the C type is always true: it is left out (no -Wtype-limits warning)
                bounds = ((f"raw >= {lit(lo)}", lo > tmin), (f"raw <= {lit(hi)}", hi < tmax))
                parts = [f"raw == {lit(lo)}"] if lo == hi else [x for x, need in bounds if need] or ["1"]
                conds.append(parts[0] if len(parts) == 1 else f"({' && '.join(parts)})")
            out.append(f"static inline int {self.p(F, s.name)}_is_{meaning}({self.ctype(s)} raw) "
                       f"{{ return {' || '.join(conds)}; }}")
        # The raw values of the map's min..max: <frame>_<signal>_in_range(raw)
        limits = raw_limits(s)
        if limits is not None:
            lo, hi = limits
            parts = [x for x, need in ((f"raw >= {lit(lo)}", lo > tmin), (f"raw <= {lit(hi)}", hi < tmax))
                     if need] or ["1"]
            out.append(f"static inline int {self.p(F, s.name)}_in_range({self.ctype(s)} raw) "
                       f"{{ return {' && '.join(parts)}; }}")
        if out:
            out.append("")
        return out

    # ------------------------------------------------------------------ #

    def source(self) -> str:
        out = [
            self.T["c_source"].format(base=self.base),
            f'#include "{self.base}.h"',
            "",
        ]
        for f in self.frames():
            out += self.frame_impl(f)
        out += self.extra_impl()
        return "\n".join(out)

    def _guard(self, s: Signal, sel: Signal | None, body: list[str]) -> list[str]:
        if s.mux is None or sel is None:
            return body
        cond = " || ".join(f"msg->{sel.name} == {v}" for v in s.mux_values)
        if body[0] == "    {" and body[-1] == "    }":
            body = [b.removeprefix("    ") for b in body[1:-1]]      # the if's own block takes the place of it
        return [f"    if ({cond}) {{"] + ["    " + b for b in body] + ["    }"]

    def initial_const(self, f: Frame) -> list[str]:
        """<FRAME>_INITIAL: the message with the initial values (in the order of the struct's fields)."""
        F = self.frame_name(f)
        items = []
        for s in f.layout:
            init = s.initial_raw
            if is_byte_array(s):
                n = s.bit_length // 8
                fill = (f"(char)0x{s.terminator_byte or 0:02X}" if s.encoding == "string" else "0u")
                items.append("{" + ", ".join([fill] * n) + "}")
            elif init is None:
                items.append("0.0" if self.ctype(s) == "double" else "0.0f" if s.encoding == "float" else "0")
            else:
                macro = self.P(F, s.name, "INITIAL" if s.encoding == "float" else "INITIAL_RAW")
                items.append(f"({self.ctype(s)}){macro}")
        return [f"const {self.p(F)}_t {self.P(F, 'INITIAL')} = {{{', '.join(items) or '0u'}}};", ""]

    def init_impl(self, f: Frame) -> list[str]:
        """<frame>_init(): every signal at the initial value of the map, 0 without one."""
        F = self.frame_name(f)
        name = self.p(F)
        out = self.initial_const(f)
        out += [f"void {name}_init({name}_t *msg)", "{", "    if (msg == NULL) {", "        return;", "    }"]
        if not f.layout:
            out.append("    msg->reserved_ = 0u;")
        for s in f.layout:
            init = s.initial_raw
            if is_byte_array(s):
                # A string is filled with its terminator (0x00 without one): the empty text
                fill = (f"(char)0x{s.terminator_byte or 0:02X}" if s.encoding == "string" else "0u")
                out += [f"    for (size_t i = 0u; i < {s.bit_length // 8}u; i++) {{",
                        f"        msg->{s.name}[i] = {fill};", "    }"]
            elif init is None:
                zero = "0.0" if self.ctype(s) == "double" else "0.0f" if s.encoding == "float" else "0"
                out.append(f"    msg->{s.name} = {zero};")
            else:
                macro = self.P(F, s.name, "INITIAL" if s.encoding == "float" else "INITIAL_RAW")
                out.append(f"    msg->{s.name} = ({self.ctype(s)}){macro};")
        return out + ["}", ""]

    # The bits of a signal are read and written with the shifts and masks of the bytes it touches, worked out
    # here from its layout (as mapcan_get_bits / mapcan_set_bits walk it at run time), in an unsigned type of
    # the field's width: no loop and no 64-bit arithmetic for a short field.

    @staticmethod
    def _chunks(s: Signal) -> list[tuple[int, int, int, int]]:
        """(byte, shift in it, bits, offset in the value) of each byte the signal touches, LSB first."""
        out, done, pos = [], 0, s.start_bit
        while done < s.bit_length:
            byte, shift = divmod(pos, 8)
            n = min(8 - shift, s.bit_length - done)
            out.append((byte, shift, n, done))
            done += n
            pos = (byte - 1) * 8 if s.byte_order == "big_endian" else (byte + 1) * 8
        return out

    @staticmethod
    def _raw_type(s: Signal) -> str:
        return f"uint{storage_bits(s)}_t"

    def _read_raw(self, s: Signal) -> str:
        """The raw bits of the signal from ``data`` as its unsigned type."""
        W = self._raw_type(s)
        terms = []
        for byte, shift, n, done in self._chunks(s):
            x = f"data[{byte}]"
            if shift:
                x = f"({x} >> {shift}u)"
            if n < 8 - shift:
                x = f"({x} & 0x{(1 << n) - 1:X}u)"
            terms.append(f"(({W}){x} << {done}u)" if done else f"({W}){x}")
        return terms[0] if len(terms) == 1 else f"({W})({' | '.join(terms)})"

    def _unpack_value(self, s: Signal) -> str:
        raw, n = self._read_raw(s), s.bit_length
        if s.encoding == "float":
            return f"mapcan_bits_to_f{64 if n == 64 else 32}({raw})"
        code = s.signed_code if s.signed else None
        T = self.ctype(s)
        if code == "ones_complement":
            return f"({T})mapcan_ones_decode((uint64_t){raw}, {n}u)"
        if code == "sign_magnitude":
            return f"({T})mapcan_sm_decode((uint64_t){raw}, {n}u)"
        if s.signed:
            ext = "mapcan_sign_extend32" if storage_bits(s) <= 32 else "mapcan_sign_extend"
            return f"({T}){ext}({raw}, {n}u)"
        return raw

    def _pack_bits(self, s: Signal) -> list[str]:
        """Statements writing the signal into ``data``: its raw value saturated to the field (a value outside
        it is not cut to its low bits), then each byte it touches."""
        W, v = self._raw_type(s), f"msg->{s.name}"
        bits = storage_bits(s)
        if s.encoding == "float":
            value = f"mapcan_f{64 if s.bit_length == 64 else 32}_to_bits({v})"
        else:
            code = s.signed_code if s.signed else None
            lo, hi = B.raw_range(s.bit_length, s.signed, code)
            if not s.signed:
                value = f"({W})(({v} > {_c_int(hi)}) ? {_c_int(hi)} : {v})" if hi < (1 << bits) - 1 else v
            else:
                # A bound at the limit of the C type is left out (always false: -Wtype-limits)
                if hi < (1 << (bits - 1)) - 1:
                    v = f"(({v} > {_c_signed(hi)}) ? {_c_signed(hi)} : {v})"
                if lo > -(1 << (bits - 1)):
                    v = f"((msg->{s.name} < {_c_signed(lo)}) ? {_c_signed(lo)} : {v})"
                value =(f"({W})mapcan_ones_encode((int64_t){v})" if code == "ones_complement"
                         else f"({W})mapcan_sm_encode((int64_t){v}, {s.bit_length}u)" if code == "sign_magnitude"
                         else f"({W}){v}")
        out = ["    {", f"        const {W} v = {value};"]
        for byte, shift, n, done in self._chunks(s):
            part = f"(v >> {done}u)" if done else "v"
            if shift:
                part = f"({part} << {shift}u)"
            if shift + n < 8:
                part = f"({part} & 0x{((1 << n) - 1) << shift:02X}u)"
            if n == 8:
                out.append(f"        data[{byte}] = (uint8_t){part};")
            else:
                keep = ~(((1 << n) - 1) << shift) & 0xFF
                out.append(f"        data[{byte}] = (uint8_t)((data[{byte}] & 0x{keep:02X}u) | (uint8_t){part});")
        return out + ["    }"]

    def frame_impl(self, f: Frame) -> list[str]:
        name = self.p(self.frame_name(f))
        sel = selector_of(f)
        init = self.init_impl(f)
        if f.length == 0:
            return init + ([
                f"int {name}_pack(uint8_t *data, size_t size, const {name}_t *msg)",
                "{", "    (void)data;", "    (void)size;", "    return (msg == NULL) ? -1 : 0;", "}", "",
            ] if self.packs(f) else []) + ([
                f"int {name}_unpack({name}_t *msg, const uint8_t *data, size_t size)",
                "{", "    (void)data;", "    (void)size;", "    if (msg == NULL) {", "        return -1;", "    }",
                "    msg->reserved_ = 0u;", "    return 0;", "}", "",
            ] if self.unpacks(f) else [])
        pack = [
            f"int {name}_pack(uint8_t *data, size_t size, const {name}_t *msg)",
            "{",
            f"    if (data == NULL || msg == NULL || size < {f.length}u) {{",
            "        return -1;",
            "    }",
            f"    for (size_t i = 0u; i < {f.length}u; i++) {{",
            "        data[i] = 0u;",
            "    }",
        ]
        unpack = [
            f"int {name}_unpack({name}_t *msg, const uint8_t *data, size_t size)",
            "{",
            f"    if (data == NULL || msg == NULL || size < {f.length}u) {{",
            "        return -1;",
            "    }",
        ]
        if sel is not None and any(s.mux is not None for s in f.layout):
            # Signals of another selector value do not keep what the previous frame had
            unpack.append(f"    {name}_init(msg);")
        # The selector is unpacked first: the other signals depend on it.
        order = sorted(f.layout, key=lambda s: not s.multiplexer)
        if not f.layout:
            unpack.append("    msg->reserved_ = 0u;")
        for s in order:
            if is_byte_array(s):
                n, b0 = s.bit_length // 8, s.start_bit // 8
                pack += self._guard(s, sel, [
                    f"    for (size_t i = 0u; i < {n}u; i++) {{",
                    f"        data[{b0}u + i] = (uint8_t)msg->{s.name}[i];",
                    "    }"])
                unpack += self._guard(s, sel, [
                    f"    for (size_t i = 0u; i < {n}u; i++) {{",
                    f"        msg->{s.name}[i] = ({'char' if s.encoding == 'string' else 'uint8_t'})data[{b0}u + i];",
                    "    }"])
                continue
            pack += self._guard(s, sel, self._pack_bits(s))
            unpack += self._guard(s, sel, [f"    msg->{s.name} = {self._unpack_value(s)};"])
        pack += [f"    return {f.length};", "}", ""]
        unpack += ["    return 0;", "}", ""]
        return init + (pack if self.packs(f) else []) + (unpack if self.unpacks(f) else [])


class DeviceGen(CGen):
    """The code of one device: the frames it sends (pack) and receives (unpack), its TX schedule, the list of
    the frames it receives with acceptance filters, and a dispatch of a received frame to its unpack."""

    def __init__(self, cmap: MapCan, bus: Bus, device: str, prefix: str = "", lang: str | None = None,
                 phys_type: str = "float"):
        super().__init__(cmap, bus, prefix, lang, phys_type)
        self.device = device
        self.D = self.device_name(device)
        self.base = (prefix + self.D).lower()
        frames = frames_with_layout(bus)
        self.tx = [f for f in frames if f.sender_name == device]
        self.rx = [f for f in frames if device in f.receiver_names and f.sender_name != device]

    def frames(self) -> list[Frame]:
        return [f for f in frames_with_layout(self.bus) if f in self.tx or f in self.rx]

    def packs(self, f: Frame) -> bool:
        return f in self.tx

    def unpacks(self, f: Frame) -> bool:
        return f in self.rx

    @staticmethod
    def _filter(frames: list[Frame], full: int) -> tuple[int, int]:
        """One ID/mask pair that lets all these IDs through: the bits they have in common."""
        first = frames[0].can_id
        differ = 0
        for f in frames[1:]:
            differ |= f.can_id ^ first
        mask = full & ~differ
        return first & mask, mask

    def extra_decls(self) -> list[str]:
        D = self.D
        out = ["/* " + "=" * 72 + " */", f"/* {self.T['device_note'].format(device=D)} */"]
        out.append(f"#define {self.P(D, 'TX_COUNT')} {len(self.tx)}u")
        if self.tx:
            out.append("typedef enum {")
            out += [f"    {self.P(D, 'TX', self.frame_name(f))} = {i}," for i, f in enumerate(self.tx)]
            out.append(f"}} {self.p(D, 'tx_frame')}_t;")
            out.append(f"/* {self.T['tx_schedule']} */")
            out.append(f"extern const mapcan_tx_entry_t {self.p(D, 'tx_schedule')}[{self.P(D, 'TX_COUNT')}];")
        out.append(f"#define {self.P(D, 'RX_COUNT')} {len(self.rx)}u")
        if self.rx:
            out.append("typedef enum {")
            out += [f"    {self.P(D, 'RX', self.frame_name(f))} = {i}," for i, f in enumerate(self.rx)]
            out.append(f"}} {self.p(D, 'rx_frame')}_t;")
            out.append(f"/* {self.T['rx_frames']} */")
            out.append(f"extern const mapcan_rx_entry_t {self.p(D, 'rx_frames')}[{self.P(D, 'RX_COUNT')}];")
            out.append(f"/* {self.T['rx_filters']} */")
            out.append(f"extern const mapcan_filter_t {self.p(D, 'rx_filters')}[{self.P(D, 'RX_COUNT')}];")
            for ext, full, kind in ((False, 0x7FF, "STD"), (True, 0x1FFFFFFF, "EXT")):
                group = [f for f in self.rx if bool(f.extended) == ext]
                if group:
                    fid, mask = self._filter(group, full)
                    out.append(f"#define {self.P(D, 'RX_FILTER', kind, 'ID')} 0x{fid:X}u")
                    out.append(f"#define {self.P(D, 'RX_FILTER', kind, 'MASK')} 0x{mask:X}u")
            out.append(f"/* {self.T['rx_state']} */")
            out.append("typedef struct {")
            out += [f"    {self.p(self.frame_name(f))}_t {self.frame_name(f)};" for f in self.rx]
            out.append(f"    bool received[{self.P(D, 'RX_COUNT')}];")
            out.append(f"    uint32_t received_ms[{self.P(D, 'RX_COUNT')}];")
            out.append(f"}} {self.p(D, 'rx')}_t;")
            out.append(f"void {self.p(D, 'rx_init')}({self.p(D, 'rx')}_t *rx);")
            out.append(f"/* {self.T['rx_dispatch'].format(prefix=self.P(D, 'RX'))} */")
            out.append(f"int {self.p(D, 'rx_dispatch')}({self.p(D, 'rx')}_t *rx, uint32_t now_ms, uint32_t id, "
                       "bool extended, const uint8_t *data, size_t size);")
            out.append(f"/* {self.T['rx_timed_out']} */")
            out.append(f"bool {self.p(D, 'rx_timed_out')}(const {self.p(D, 'rx')}_t *rx, {self.p(D, 'rx_frame')}_t "
                       "frame, uint32_t now_ms);")
        out.append("")
        return out

    def extra_impl(self) -> list[str]:
        D, out = self.D, []
        if self.tx:
            out.append(f"const mapcan_tx_entry_t {self.p(D, 'tx_schedule')}[{self.P(D, 'TX_COUNT')}] = {{")
            for f in self.tx:
                F = self.frame_name(f)
                inhibit = round(f.inhibit_ms * 1000) if f.inhibit_ms is not None else 0
                out.append(f"    {{{self.P(F, 'ID')}, {self.P(F, 'LENGTH')}, {_c_bool(f.extended)}, "
                           f"{_c_bool(f.bus.fd)}, {f.cycle_ms or 0}u, {_c_bool(f.trigger == 'event')}, "
                           f"{inhibit}u}},")
            out += ["};", ""]
        if not self.rx:
            return out
        out.append(f"const mapcan_rx_entry_t {self.p(D, 'rx_frames')}[{self.P(D, 'RX_COUNT')}] = {{")
        for f in self.rx:
            F = self.frame_name(f)
            # The receive timeout of the map, or three periods of a cyclic frame without one
            timeout = f.timeout_ms or (3 * f.cycle_ms if f.cycle_ms else 0)
            out.append(f"    {{{self.P(F, 'ID')}, {self.P(F, 'LENGTH')}, {_c_bool(f.extended)}, {_c_bool(f.bus.fd)}, "
                       f"{f.cycle_ms or 0}u, {timeout}u}},")
        out += ["};", ""]
        out.append(f"const mapcan_filter_t {self.p(D, 'rx_filters')}[{self.P(D, 'RX_COUNT')}] = {{")
        for f in self.rx:
            out.append(f"    {{{self.P(self.frame_name(f), 'ID')}, 0x{0x1FFFFFFF if f.extended else 0x7FF:X}u, "
                       f"{_c_bool(f.extended)}}},")
        out += ["};", ""]
        rx_t = f"{self.p(D, 'rx')}_t"
        out += [f"void {self.p(D, 'rx_init')}({rx_t} *rx)", "{", "    if (rx == NULL) {", "        return;", "    }"]
        out += [f"    {self.p(self.frame_name(f))}_init(&rx->{self.frame_name(f)});" for f in self.rx]
        out += [f"    for (size_t i = 0u; i < {self.P(D, 'RX_COUNT')}; i++) {{", "        rx->received[i] = false;",
                "        rx->received_ms[i] = 0u;", "    }", "}", ""]
        out += [f"int {self.p(D, 'rx_dispatch')}({rx_t} *rx, uint32_t now_ms, uint32_t id, bool extended, "
                "const uint8_t *data, size_t size)", "{", "    if (rx == NULL) {", "        return -1;", "    }"]
        for ext in (False, True):
            group, seen = [], set()
            for f in self.rx:
                if bool(f.extended) == ext and f.can_id not in seen:       # a duplicate ID: the first frame
                    seen.add(f.can_id)
                    group.append(f)
            if not group:
                continue
            out += [f"    if ({'' if ext else '!'}extended) {{", "        switch (id) {"]
            for f in group:
                F, idx = self.frame_name(f), self.P(D, "RX", self.frame_name(f))
                out += [f"        case {self.P(F, 'ID')}:",
                        f"            if ({self.p(F)}_unpack(&rx->{F}, data, size) != 0) {{",
                        "                return -1;",
                        "            }",
                        f"            rx->received[{idx}] = true;",
                        f"            rx->received_ms[{idx}] = now_ms;",
                        f"            return (int){idx};"]
            out += ["        default:", "            break;", "        }", "    }"]
        out += ["    return -1;", "}", ""]
        # Timeout supervision: the time since the last reception (unsigned: the millisecond counter may wrap)
        out += [f"bool {self.p(D, 'rx_timed_out')}(const {rx_t} *rx, {self.p(D, 'rx_frame')}_t frame, "
                "uint32_t now_ms)", "{",
                f"    if (rx == NULL || (size_t)frame >= {self.P(D, 'RX_COUNT')} || "
                f"{self.p(D, 'rx_frames')}[frame].timeout_ms == 0u) {{",
                "        return false;", "    }",
                "    return !rx->received[frame]",
                f"        || (uint32_t)(now_ms - rx->received_ms[frame]) > {self.p(D, 'rx_frames')}[frame].timeout_ms;",
                "}", ""]
        return out


def device_names(cmap: MapCan, buses: list[str] | None = None) -> list[str]:
    """Devices of the map (of the given buses) that send or receive a frame, in the map's order."""
    out: list[str] = []
    for bus in cmap.buses:
        if buses and bus.name not in buses:
            continue
        frames = frames_with_layout(bus)
        for d in bus.devices:
            if d.name not in out and any(f.sender_name == d.name or d.name in f.receiver_names for f in frames):
                out.append(d.name)
    return out


def generate_c_devices(cmap: MapCan, out_dir: str | Path, devices: list[str] | None = None, prefix: str = "",
                       buses: list[str] | None = None, phys_type: str = "float") -> list[Path]:
    """<device>.h / <device>.c for each device (all of them without ``devices``); a device on several buses
    gets a pair per bus, named with the bus (<bus>_<device>)."""
    names = device_names(cmap, buses)
    unknown = [d for d in devices or [] if d not in names]
    if unknown:
        raise ValueError(_("no frames are sent or received by: {names}", names=", ".join(unknown)))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for bus in cmap.buses:
        if buses and bus.name not in buses:
            continue
        for d in bus.devices:
            if d.name not in (devices or names):
                continue
            g = DeviceGen(cmap, bus, d.name, prefix, phys_type=phys_type)
            if not g.tx and not g.rx:
                continue
            h, c = out / f"{g.base}.h", out / f"{g.base}.c"
            h.write_text(g.header(), encoding="utf-8")
            c.write_text(g.source(), encoding="utf-8")
            written += [h, c]
    return written


def generate_c(cmap: MapCan, out_dir: str | Path, prefix: str = "", buses: list[str] | None = None,
               phys_type: str = "float") -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for bus in cmap.buses:
        if buses and bus.name not in buses:
            continue
        g = CGen(cmap, bus, prefix, phys_type=phys_type)
        h, c = out / f"{g.base}.h", out / f"{g.base}.c"
        h.write_text(g.header(), encoding="utf-8")
        c.write_text(g.source(), encoding="utf-8")
        written += [h, c]
    return written
