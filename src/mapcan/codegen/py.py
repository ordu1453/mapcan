"""Generation of a self-contained Python module (with no dependency on mapcan).

The module has ID constants, value IntEnums, flag masks, a dataclass for
each frame with ``pack()``/``unpack()`` methods, and ``DECODERS``, a dictionary
(CAN ID, extended) → frame class. Suitable for tests and test benches.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Bus, Frame, MapCan, enum_entries, text
from ..units import translate_unit
from .common import code_text, frames_with_layout, is_byte_array, num, physical, selector_of

RUNTIME = '''

def _f2b(value, bits):
    """@F2B@"""
    if bits == 32:
        return struct.unpack("<I", struct.pack("<f", value))[0]
    return struct.unpack("<Q", struct.pack("<d", value))[0]


def _b2f(raw, bits):
    """@B2F@"""
    if bits == 32:
        return struct.unpack("<f", struct.pack("<I", raw))[0]
    return struct.unpack("<d", struct.pack("<Q", raw))[0]


def _get(data, start, length, big_endian, signed=False):
    value, done, pos = 0, 0, start
    while done < length:
        byte, shift = divmod(pos, 8)
        n = min(8 - shift, length - done)
        value |= ((data[byte] >> shift) & ((1 << n) - 1)) << done
        done += n
        pos = (byte - 1) * 8 if big_endian else (byte + 1) * 8
    if signed and value & (1 << (length - 1)):
        if signed == "ones_complement":
            value -= (1 << length) - 1
        elif signed == "sign_magnitude":
            value = -(value & ((1 << (length - 1)) - 1))
        else:
            value -= 1 << length
    return value


def _ones(value, length):
    """@ONES_NOTE@"""
    return value if value >= 0 else ((1 << length) - 1) + value


def _sm(value, length):
    """@SM_NOTE@"""
    return value if value >= 0 else (1 << (length - 1)) | -value


def _set(buf, value, start, length, big_endian):
    value &= (1 << length) - 1
    done, pos = 0, start
    while done < length:
        byte, shift = divmod(pos, 8)
        n = min(8 - shift, length - done)
        mask = ((1 << n) - 1) << shift
        buf[byte] = (buf[byte] & ~mask & 0xFF) | (((value >> done) << shift) & mask)
        done += n
        pos = (byte - 1) * 8 if big_endian else (byte + 1) * 8
'''


# Ones' complement and sign-magnitude: an encoding function in the generated module (_get decodes)
_SIGNED_ENCODERS = {"ones_complement": "_ones", "sign_magnitude": "_sm"}


def _cls(name: str) -> str:
    return "".join(p.capitalize() for p in name.split("_"))


def _py_str(s: str) -> str:
    return repr(s)


class PyGen:
    def __init__(self, cmap: MapCan, bus: Bus, lang: str | None = None):
        self.cmap, self.bus, self.lang = cmap, bus, lang or cmap.lang
        self.T = code_text(self.lang)

    def t(self, v) -> str:
        return text(v, self.lang, self.cmap.lang).replace("\n", " ")

    def module(self) -> str:
        d = self.cmap.document
        out = [
            '"""' + self.T["py_header"].format(bus=self.bus.name, title=self.t(d.title), version=d.version),
            "",
            self.T["do_not_edit"],
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "import struct",
            "from dataclasses import dataclass, field",
            "from enum import IntEnum",
            RUNTIME.replace("@F2B@", self.T["f2b"]).replace("@B2F@", self.T["b2f"])
            .replace("@ONES_NOTE@", self.T["ones_py"]).replace("@SM_NOTE@", self.T["sm_py"]),
        ]
        frames = frames_with_layout(self.bus)
        for f in frames:
            out += self.frame(f)
        out.append("DECODERS = {")
        for f in frames:
            out.append(f"    (0x{f.can_id:03X}, {bool(f.extended)}): {_cls(f.name)},")
        out.append("}")
        out.append("")
        out.append("")
        out.append("def decode(can_id: int, data: bytes, is_extended: bool | None = None):")
        out.append(f'    """{self.T["decode"]}"""')
        out.append("    if is_extended is None:")
        out.append("        cls = DECODERS.get((can_id, False)) or DECODERS.get((can_id, True))")
        out.append("    else:")
        out.append("        cls = DECODERS.get((can_id, is_extended))")
        out.append("    return cls.unpack(data) if cls else None")
        out.append("")
        return "\n".join(out)

    def frame(self, f: Frame) -> list[str]:
        C = _cls(f.name)
        U = f.name.upper()
        sel = selector_of(f)
        out = ["", f"{U}_ID = 0x{f.can_id:03X}", f"{U}_LENGTH = {f.length}",
               f"{U}_DLC = {U}_LENGTH  # {self.T['deprecated_dlc'].format(name=f'{U}_LENGTH')}"]
        if f.mode == "cyclic":
            out.append(f"{U}_CYCLE_MS = {f.cycle_ms}")
        for s in f.layout:
            if s.spn is not None:
                out.append(f"{U}_{s.name.upper()}_SPN = {s.spn}")
            entries = enum_entries(s.values)
            if entries:
                out += ["", "", f"class {C}{_cls(s.name)}(IntEnum):"]
                d = self.t(s.description) or self.t(s.title)
                if d:
                    out.append(f"    {_py_str(d)}")
                for v, ev in entries:
                    out.append(f"    {ev.name} = {v}")
            for fl in s.flags or []:
                mask = ((1 << fl.bit_length) - 1) << fl.bit
                out.append(f"{U}_{s.name.upper()}_{fl.name.upper()}_MASK = 0x{mask:X}")
        # Raw values without a value, by meaning: <frame>_<signal>_is_not_available(raw), …_is_error(raw)
        for s in f.layout:
            for meaning, ranges in s.invalid_ranges.items():
                def lit(v: int) -> str:
                    return f"0x{v:X}" if v >= 0 else str(v)
                cond = " or ".join(f"raw == {lit(lo)}" if lo == hi else f"{lit(lo)} <= raw <= {lit(hi)}"
                                   for lo, hi in ranges)
                out += ["", "", f"def {f.name.lower()}_{s.name.lower()}_is_{meaning}(raw: int) -> bool:",
                        f"    return {cond}"]
        out += ["", "", "@dataclass", f"class {C}:"]
        doc = self.t(f.description) or self.t(f.title)
        out.append(f'    """0x{f.can_id:03X} {f.name}: {doc}"""' if doc else f'    """0x{f.can_id:03X} {f.name}"""')
        out += ["", f"    ID = 0x{f.can_id:03X}", f"    LENGTH = {f.length}",
                f"    DLC = LENGTH  # {self.T['deprecated_dlc'].format(name='LENGTH')}",
                # How to send the frame, named as the arguments of python-can's can.Message
                f"    IS_EXTENDED = {f.extended}", f"    IS_FD = {f.bus.fd}",
                f"    BITRATE_SWITCH = {bool(f.bit_rate_switch)}", ""]
        for s in f.layout:
            init = s.initial_raw
            if is_byte_array(s):
                out.append(f"    {s.name}: bytes = field(default=bytes({s.bit_length // 8}))")
            elif s.encoding == "float":
                out.append(f"    {s.name}: float = {num(init if init is not None else 0.0)}")
            else:
                out.append(f"    {s.name}: int = {init if init is not None else 0}")
        if not f.layout:
            out.append("    pass")

        # pack
        out += ["", "    def pack(self) -> bytes:", f"        buf = bytearray({f.length})"]
        for s in f.layout:
            body = self._pack_stmt(s)
            out += self._guard(s, sel, body, "self")
        out.append("        return bytes(buf)")

        # unpack
        bad_length = self.T["bad_length"].format(frame=f.name, length=f.length, got="{len(data)}")
        out += ["", "    @classmethod", f"    def unpack(cls, data: bytes) -> \"{C}\":",
                f"        if len(data) < {f.length}:",
                f"            raise ValueError(f\"{bad_length}\")",
                "        msg = cls()"]
        for s in sorted(f.layout, key=lambda s: not s.multiplexer):
            out += self._guard(s, sel, self._unpack_stmt(s), "msg")
        out.append("        return msg")

        # physical values
        for s in f.layout:
            if physical(s) and not is_byte_array(s):
                unit = ", " + translate_unit(s.unit, self.lang) if s.unit else ""
                out += [
                    "",
                    "    @property",
                    f"    def {s.name}_phys(self) -> float:",
                    # The map's text as a string literal: quotes and \ in it do not break the docstring
                    f"        {_py_str((self.t(s.description) or self.t(s.title)) + unit)}",
                    f"        return self.{s.name} * {num(s.factor)} + {num(s.offset)}",
                    "",
                    f"    @{s.name}_phys.setter",
                    f"    def {s.name}_phys(self, value: float) -> None:",
                    (f"        self.{s.name} = (value - {num(s.offset)}) / {num(s.factor)}" if s.encoding == "float"
                     else f"        self.{s.name} = round((value - {num(s.offset)}) / {num(s.factor)})"),
                ]
        out.append("")
        return out

    @staticmethod
    def _guard(s, sel, body: list[str], obj: str) -> list[str]:
        if s.mux is None or sel is None:
            return body
        vals = ", ".join(str(v) for v in s.mux_values)
        return [f"        if {obj}.{sel.name} in ({vals},):"] + ["    " + b for b in body]

    @staticmethod
    def _pack_stmt(s) -> list[str]:
        if is_byte_array(s):
            n, b0 = s.bit_length // 8, s.start_bit // 8
            return [f"        buf[{b0}:{b0 + n}] = bytes(self.{s.name})[:{n}].ljust({n}, b'\\0')"]
        be = s.byte_order == "big_endian"
        value = f"_f2b(self.{s.name}, {s.bit_length})" if s.encoding == "float" else f"self.{s.name}"
        enc = _SIGNED_ENCODERS.get(s.signed_code) if s.signed else None
        if enc:
            value = f"{enc}({value}, {s.bit_length})"
        return [f"        _set(buf, {value}, {s.start_bit}, {s.bit_length}, {be})"]

    @staticmethod
    def _unpack_stmt(s) -> list[str]:
        if is_byte_array(s):
            n, b0 = s.bit_length // 8, s.start_bit // 8
            return [f"        msg.{s.name} = bytes(data[{b0}:{b0 + n}])"]
        be = s.byte_order == "big_endian"
        if s.encoding == "float":
            return [f"        msg.{s.name} = _b2f(_get(data, {s.start_bit}, {s.bit_length}, {be}), {s.bit_length})"]
        signed = repr(s.signed_code) if s.signed and s.signed_code in _SIGNED_ENCODERS else s.signed
        return [f"        msg.{s.name} = _get(data, {s.start_bit}, {s.bit_length}, {be}, {signed})"]


def generate_py(cmap: MapCan, out_dir: str | Path, buses: list[str] | None = None) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for bus in cmap.buses:
        if buses and bus.name not in buses:
            continue
        p = out / f"{bus.name.lower()}_mapcan.py"
        p.write_text(PyGen(cmap, bus).module(), encoding="utf-8")
        written.append(p)
    return written
