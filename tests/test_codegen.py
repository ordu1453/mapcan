"""Round trip pack → unpack for every frame: Python module, C code, DBC."""

from __future__ import annotations

import importlib.util
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import cantools
import pytest

from mapcan import bits as B
from mapcan.codegen.c import CGen, generate_c
from mapcan.codegen.common import frames_with_layout, is_byte_array, selector_of
from mapcan.codegen.py import _cls, generate_py
from mapcan.export.dbc import bus_database
from mapcan.loader import load
from mapcan.model import Signal

from .conftest import DATA, REFERENCE, ROOT, run

PATTERN = 0xA5C396E15A3C691E


def _value(s, i: int) -> int:
    mask = (1 << s.bit_length) - 1
    v = ((PATTERN >> (i * 5 % 40)) | (PATTERN << 7)) & mask
    if s.signed and v & (1 << (s.bit_length - 1)):
        v -= 1 << s.bit_length
    return v


def sample(frame) -> dict:
    """Signal values for the test; the selector picks the first multiplexed set."""
    vals = {}
    sel = selector_of(frame)
    for i, s in enumerate(frame.layout):
        if is_byte_array(s) and s.is_text:
            # Text that fills the field: no terminator, so it reads back the same
            vals[s.name] = "".join(chr(ord("A") + (k + i) % 26) for k in range(s.bit_length // 8))
        elif is_byte_array(s):
            vals[s.name] = bytes((0x11 * (k + 1) + i) & 0xFF for k in range(s.bit_length // 8))
        else:
            vals[s.name] = 1.5 + 0.25 * i if s.is_float else _value(s, i)
    if sel is not None:
        muxed = [s for s in frame.layout if s.mux is not None]
        if muxed:
            vals[sel.name] = muxed[0].mux_values[0]
    return vals


def present(frame, vals) -> list:
    sel = selector_of(frame)
    out = []
    for s in frame.layout:
        if s.mux is None or sel is None or vals[sel.name] in s.mux_values:
            out.append(s)
    return out


def _import(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


MAPS = [REFERENCE, ROOT / "examples" / "minimal.yaml", ROOT / "examples" / "j1939.yaml",
        ROOT / "examples" / "vehicle-can.yaml"]


@pytest.fixture(scope="module", params=MAPS, ids=lambda p: p.stem)
def cmap(request):
    res = load(request.param)
    assert res.map is not None
    return res.map


@pytest.fixture(scope="module")
def py_modules(cmap, tmp_path_factory):
    out = tmp_path_factory.mktemp("py")
    return {p.stem.replace("_mapcan", ""): _import(p) for p in generate_py(cmap, out)}


def test_python_roundtrip(cmap, py_modules):
    n = 0
    for bus in cmap.buses:
        mod = py_modules[bus.name]
        for f in frames_with_layout(bus):
            cls = getattr(mod, _cls(f.name))
            vals = sample(f)
            msg = cls(**vals)
            data = msg.pack()
            assert len(data) == f.length
            back = cls.unpack(data)
            for s in present(f, vals):
                assert getattr(back, s.name) == vals[s.name], (f.name, s.name)
            assert mod.decode(f.can_id, data) == back
            n += 1
    assert n >= 1


def test_python_decode_standard_and_extended(tmp_path):
    """An 11-bit and a 29-bit frame with the same number both have a decoder."""
    from mapcan.loader import loads

    m = loads("""
mapcan: 2
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    devices:
      - name: a
        frames:
          - {name: std, id: 0x100, length: 1, signals: [{name: s, encoding: number, byte: 0, byte_length: 1}]}
          - {name: ext, id: 0x100, extended: true, length: 1,
             signals: [{name: e, encoding: number, byte: 0, byte_length: 1}]}
""", "t.yaml").map
    [path] = generate_py(m, tmp_path)
    mod = _import(path)
    assert set(mod.DECODERS) == {(0x100, False), (0x100, True)}
    assert mod.decode(0x100, b"") == mod.Std(s=7)
    assert mod.decode(0x100, b"", is_extended=False) == mod.Std(s=7)
    assert mod.decode(0x100, b"", is_extended=True) == mod.Ext(e=7)
    assert mod.decode(0x101, b"") is None


def test_python_physical(py_modules):
    if "bus1" not in py_modules:
        pytest.skip("только для эталонной карты")
    m = py_modules["bus1"].ImdData()
    m.bus_voltage_phys = 400.3
    assert m.bus_voltage == 4003
    assert abs(m.bus_voltage_phys - 400.3) < 1e-9


def test_python_enums(py_modules):
    if "bus1" not in py_modules:
        pytest.skip("только для эталонной карты")
    mod = py_modules["bus1"]
    assert mod.ImdStateInsulationStatus.ALARM == 3
    assert mod.IMD_STATE_ID == 0x1A1
    assert mod.IMD_STATE_INTERNAL_ERROR_TIMEOUT_ERROR_MASK == 0x2


def test_dbc_matches_python(cmap, py_modules):
    """cantools encodes the same bytes as the generated module."""
    for bus in cmap.buses:
        db = bus_database(cmap, bus)
        dbc = cantools.database.load_string(db.as_dbc_string(), "dbc")
        mod = py_modules[bus.name]
        for f in frames_with_layout(bus):
            if not f.layout:
                continue
            vals = sample(f)
            if any(is_byte_array(s) for s in present(f, vals)):
                continue  # byte arrays in DBC are whole 56-bit integers, checked separately
            ours = getattr(mod, _cls(f.name))(**vals).pack()
            msg = dbc.get_message_by_frame_id(f.can_id)
            decoded = msg.decode(ours, decode_choices=False, scaling=False)
            for s in present(f, vals):
                if s.encoding == "bitfield" and s.flags:
                    for fl in s.flags:
                        expect = (vals[s.name] >> fl.bit) & ((1 << fl.bit_length) - 1)
                        assert decoded[fl.name] == expect, (f.name, fl.name)
                else:
                    assert decoded[s.name] == vals[s.name], (f.name, s.name)


def test_dbc_file_loads(ref_map, tmp_path):
    from mapcan.export.dbc import export_dbc

    paths = export_dbc(ref_map, tmp_path)
    db = cantools.database.load_file(paths[0], encoding="cp1251")
    m = db.get_message_by_frame_id(0x2A2)
    assert m.is_multiplexed()
    assert m.get_signal_by_name("parse_type").is_multiplexer
    assert db.get_message_by_frame_id(0x1A1).cycle_time == 100


# --------------------------------------------------------------------------- C

GCC = shutil.which("gcc") or shutil.which("cc")


def _c_lit(s, v) -> str:
    if isinstance(v, bytes):
        return "{" + ", ".join(f"0x{b:02X}" for b in v) + "}"
    if s.is_float:
        return repr(float(v)) + ("" if s.bit_length == 64 else "f")
    if s.signed:
        return f"({v}LL)"
    return f"{v}ULL"


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_c_matches_python(cmap, py_modules, tmp_path):
    sources = [p for p in generate_c(cmap, tmp_path) if p.suffix == ".c"]
    main = ["#include <stdio.h>", "#include <inttypes.h>"] + [f'#include "{p.stem}.h"' for p in sources] + [
            "static void hex(const char *n, const uint8_t *d, int len) {",
            '    printf("%s", n); for (int i = 0; i < len; i++) printf(" %02X", d[i]); printf("\\n"); }',
            "int main(void) {", "    uint8_t buf[64];", "    int rc;"]
    expected = []
    for bus in cmap.buses:
        g = CGen(cmap, bus)
        mod = py_modules[bus.name]
        for f in frames_with_layout(bus):
            t = g.p(g.frame_name(f))
            vals = sample(f)
            main.append("    {")
            main.append(f"        {t}_t m = {{0}}, u = {{0}};")
            for s in f.layout:
                if s.name not in vals:
                    continue
                v = vals[s.name]
                if isinstance(v, str):
                    for k, b in enumerate(v.encode("ascii")):
                        main.append(f"        m.{s.name}[{k}] = (char)0x{b:02X};")
                elif isinstance(v, bytes):
                    for k, b in enumerate(v):
                        main.append(f"        m.{s.name}[{k}] = 0x{b:02X};")
                else:
                    main.append(f"        m.{s.name} = ({g.ctype(s)}){_c_lit(s, v)};")
            main.append(f"        rc = {t}_pack(buf, sizeof buf, &m);")
            main.append(f'        hex("{f.name}", buf, rc);')
            main.append(f"        if ({t}_unpack(&u, buf, (size_t)rc) != 0) return 1;")
            for s in present(f, vals):
                if is_byte_array(s):
                    main.append(f'        hex("{f.name}.{s.name}", (const uint8_t *)u.{s.name}, {s.bit_length // 8});')
                    data = vals[s.name].encode("ascii") if isinstance(vals[s.name], str) else vals[s.name]
                    expected.append(f"{f.name}.{s.name}" + "".join(f" {b:02X}" for b in data))
                elif s.is_float:
                    # Compared by the exact IEEE 754 bits.
                    w = 64 if s.bit_length == 64 else 32
                    main.append(f'        printf("{f.name}.{s.name} %" PRIu64 "\\n", '
                                f'(uint64_t)mapcan_f{w}_to_bits(u.{s.name}));')
                    fmt, ufmt = ("<d", "<Q") if w == 64 else ("<f", "<I")
                    bits = struct.unpack(ufmt, struct.pack(fmt, vals[s.name]))[0]
                    expected.append(f"{f.name}.{s.name} {bits}")
                else:
                    main.append(f'        printf("{f.name}.{s.name} %" PRId64 "\\n", (int64_t)u.{s.name});')
                    expected.append(f"{f.name}.{s.name} {vals[s.name]}")
            if f.layout:
                main.append(f"        if ({t}_pack(buf, {max(f.length - 1, 0)}u, &m) != -1) return 2;")
            main.append("    }")
            data = getattr(mod, _cls(f.name))(**vals).pack()
            expected.insert(len(expected) - len(present(f, vals)),
                            f.name + "".join(f" {b:02X}" for b in data))
    main += ["    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    cmd = [GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
           str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split("\n")
    assert [line.strip() for line in out if line.strip()] == expected
    if GXX is None:
        return
    # The same code built as C++17 gives the same bytes and values ({0} of the test's structs is valid C++ too)
    exe = tmp_path / "t_cpp.exe"
    subprocess.run([GXX, "-x", "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    "-Wno-missing-field-initializers",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split("\n")
    assert [line.strip() for line in out if line.strip()] == expected


GXX = shutil.which("g++") or shutil.which("c++")


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_headers_with_different_helpers_do_not_build_together(tmp_path):
    """Headers whose bit helpers differ (other mapcan versions) stop the build instead of sharing the first ones."""
    from mapcan.codegen.c import HELPERS_REVISION

    generate_c(_gateway_map("gw", "1.0", "body", "chassis"), tmp_path)
    generate_c(_gateway_map("service", "2.3", "diag"), tmp_path)
    diag = tmp_path / "diag.h"
    diag.write_text(diag.read_text(encoding="utf-8").replace(HELPERS_REVISION, "0x00000001u"), encoding="utf-8")
    (tmp_path / "main.c").write_text('#include "body.h"\n#include "diag.h"\nint main(void) { return 0; }\n',
                                     encoding="utf-8")
    r = subprocess.run([GCC, "-std=c99", "-fsyntax-only", str(tmp_path / "main.c"), "-I", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "different mapcan versions" in r.stderr
    # The same revision: one copy of the helpers, no error
    diag.write_text(diag.read_text(encoding="utf-8").replace("0x00000001u", HELPERS_REVISION), encoding="utf-8")
    subprocess.run([GCC, "-std=c99", "-Wall", "-Werror", "-DMAPCAN_NO_DEPRECATED", "-fsyntax-only",
                    str(tmp_path / "main.c"), "-I", str(tmp_path)], check=True, capture_output=True, text=True)


ARM_GCC = shutil.which("arm-none-eabi-gcc")


@pytest.mark.skipif(ARM_GCC is None, reason="нет arm-none-eabi-gcc")
def test_c_compiles_for_cortex_m(cmap, tmp_path):
    for src in (p for p in generate_c(cmap, tmp_path) if p.suffix == ".c"):
        subprocess.run([ARM_GCC, "-std=c99", "-mcpu=cortex-m4", "-mthumb", "-Os", "-Wall", "-Wextra",
                        "-Werror", "-ffreestanding", "-c", str(src), "-o", str(src.with_suffix(".o"))],
                       check=True, capture_output=True, text=True)


BOUNDS_MAP = """\
mapcan: 2
document:
  title: Test
  language: ru
buses:
  - name: bus
    protocol: can
    devices:
      - name: dev
        frames:
          - name: f1
            id: 0x101
            length: 8
            signals:
              - {name: u28, encoding: number, start_bit: 0, bit_length: 28, factor: 0.5, unit: ms}
              - {name: s32, encoding: number, start_bit: 28, bit_length: 32, factor: 0.5,
                 representation: twos_complement}
          - name: f2
            id: 0x102
            length: 8
            signals:
              - {name: u64, encoding: number, start_bit: 0, bit_length: 64, factor: 2}
          - name: f3
            id: 0x103
            length: 8
            signals:
              - {name: s64, encoding: number, start_bit: 0, bit_length: 64, representation: twos_complement, factor: 2}
          - name: f4
            id: 0x104
            length: 8
            signals:
              - {name: s8, encoding: number, start_bit: 0, bit_length: 8, representation: twos_complement, factor: 0.5}
"""


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_c_from_phys_bounds(tmp_path):
    """Saturation at the limits of the width and precision of long fields (double, not float)."""
    from mapcan.loader import loads

    cmap = loads(BOUNDS_MAP, "bounds.yaml").map
    sources = [p for p in generate_c(cmap, tmp_path) if p.suffix == ".c"]
    checks = [
        ("f1_u28_from_phys(1e12)", 268435455),        # used to be 2^28: the top bit was lost when packing
        ("f1_u28_from_phys(8388608.5)", 16777217),    # in float 8388608.5 is not exact (25 significant bits)
        ("f1_u28_from_phys(-5.0)", 0),
        ("f1_s32_from_phys(1e12)", 2**31 - 1),
        ("f1_s32_from_phys(-1e12)", -(2**31)),
        ("f2_u64_from_phys(1e30)", 2**64 - 1),
        ("f2_u64_from_phys(-1.0)", 0),
        ("f3_s64_from_phys(1e30)", 2**63 - 1),
        ("f3_s64_from_phys(-1e30)", -(2**63)),
        ("f4_s8_from_phys(1000.0f)", 127),
        ("f4_s8_from_phys(-1000.0f)", -128),
    ]
    main = ["#include <stdio.h>", "#include <inttypes.h>", '#include "bus.h"', "int main(void) {"]
    for expr, v in checks:
        fmt, cast = ("PRIu64", "uint64_t") if v >= 2**63 else ("PRId64", "int64_t")
        main.append(f'    printf("%" {fmt} "\\n", ({cast}){expr});')
    main += ["    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split()
    assert [int(x) for x in out] == [v for _, v in checks]


def _dbc(yaml_text: str):
    from mapcan.loader import loads

    m = loads(yaml_text, "t.yaml").map
    return cantools.database.load_string(bus_database(m, m.buses[0]).as_dbc_string(), "dbc")


def test_dbc_attributes_for_plain_can():
    """Period, transmission mode, initial value and bus bitrate are not lost on a bus without J1939."""
    db = _dbc(BOUNDS_MAP.replace("protocol: can", "protocol: can\n    bitrate: 250000").replace(
        "id: 0x101", "id: 0x101\n            cycle_ms: 50\n            comment: Note").replace(
        "id: 0x102", "id: 0x102\n            trigger: event").replace(
        "unit: ms}", "unit: ms, initial: 3.5, description: Time, comment: Raw ms}"))
    f1, f2 = db.get_message_by_name("f1"), db.get_message_by_name("f2")
    assert db.buses[0].baudrate == 250000
    assert (f1.cycle_time, f1.send_type, f2.send_type) == (50, "Cyclic", "Spontaneous")
    assert db.get_message_by_name("f3").send_type == "NoMsgSendType"
    assert f1.comment == "Note"
    sig = f1.get_signal_by_name("u28")
    assert sig.raw_initial == 7 and sig.comment == "Time\nRaw ms"


def test_dbc_fd_frames():
    db = _dbc(BOUNDS_MAP.replace("protocol: can", "protocol: can\n    fd: true"))
    assert all(m.is_fd for m in db.messages)


def test_dbc_flag_comment_in_document_language():
    flags = """\
          - name: f5
            id: 0x105
            length: 8
            signals:
              - name: st
                encoding: bitfield
                start_bit: 0
                bit_length: 8
                flags: [{name: ready, bit: 3}]
"""
    yaml_en = BOUNDS_MAP.replace("  language: ru", "  language: en") + flags
    assert _dbc(yaml_en).get_message_by_name("f5").get_signal_by_name("ready").comment == "st, bit 3"
    assert _dbc(BOUNDS_MAP + flags).get_message_by_name("f5").get_signal_by_name("ready").comment == "st, бит 3"


def test_dbc_warns_about_unencodable_chars(tmp_path):
    from mapcan.export.dbc import export_dbc
    from mapcan.loader import loads

    m = loads(BOUNDS_MAP.replace("unit: ms}", "unit: ms, description: 'Δt ≥ 0'}"), "t.yaml").map
    warnings = []
    export_dbc(m, tmp_path, warn=warnings.append)
    assert len(warnings) == 1 and "'Δ'" in warnings[0] and "'≥'" in warnings[0]
    export_dbc(loads(BOUNDS_MAP, "t.yaml").map, tmp_path, warn=warnings.append)
    assert len(warnings) == 1


SIGNED_CODES_MAP = """\
mapcan: 2
document: {title: Test, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 8
        signals:
          - {name: o8, encoding: number, byte: 0, byte_length: 1, representation: ones_complement}
          - {name: s8, encoding: number, byte: 1, byte_length: 1, representation: sign_magnitude}
          - {name: o12, encoding: number, start_bit: 16, bit_length: 12, representation: ones_complement}
          - {name: s16, encoding: number, byte: 4, byte_length: 2, byte_order: big_endian,
             representation: sign_magnitude}
"""
# Bytes computed by hand: ones' complement −5 = 0xFA, sign-magnitude −5 = 0x85, 12 bits −100 = 0xF9B, −300 = 0x812C
SIGNED_CASES = [
    ({"o8": -5, "s8": -5, "o12": -100, "s16": -300}, "FA 85 9B 0F 81 2C 00 00"),
    ({"o8": 5, "s8": 5, "o12": 100, "s16": 300}, "05 05 64 00 01 2C 00 00"),
    ({"o8": -127, "s8": -127, "o12": -2047, "s16": -32767}, "80 FF 00 08 FF FF 00 00"),
]


def test_signed_codes_python(tmp_path):
    from mapcan.loader import loads

    mod = _import(generate_py(loads(SIGNED_CODES_MAP, "t.yaml").map, tmp_path)[0])
    for vals, data in SIGNED_CASES:
        packed = mod.F(**vals).pack()
        assert packed.hex(" ").upper() == data
        assert {k: getattr(mod.F.unpack(packed), k) for k in vals} == vals


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_signed_codes_c(tmp_path):
    from mapcan.loader import loads

    sources = [p for p in generate_c(loads(SIGNED_CODES_MAP, "t.yaml").map, tmp_path) if p.suffix == ".c"]
    main = ["#include <stdio.h>", "#include <inttypes.h>", '#include "bus.h"', "int main(void) {",
            "    uint8_t buf[8];", "    f_t m, u;"]
    expected = []
    for vals, data in SIGNED_CASES:
        main += [f"    m.{k} = {v};" for k, v in vals.items()]
        main += ["    f_pack(buf, sizeof buf, &m);",
                 '    for (int i = 0; i < 8; i++) printf("%02X ", buf[i]);', '    printf("\\n");',
                 "    f_unpack(&u, buf, sizeof buf);"]
        main += [f'    printf("%" PRId64 "\\n", (int64_t)u.{k});' for k in vals]
        expected += [data] + [str(v) for v in vals.values()]
    main += ["    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()
    assert [line.strip() for line in out] == expected


def test_dbc_warns_about_signed_codes(tmp_path):
    from mapcan.export.dbc import export_dbc
    from mapcan.loader import loads

    warnings = []
    export_dbc(loads(SIGNED_CODES_MAP, "t.yaml").map, tmp_path, warn=warnings.append)
    assert len(warnings) == 1 and "f.o8, f.s8, f.o12, f.s16" in warnings[0]


def test_fd_and_brs_flags(tmp_path):
    from mapcan.loader import loads

    from .test_import import _fd_map

    cmap = loads(_fd_map(), "fd.yaml").map
    header = next(p for p in generate_c(cmap, tmp_path / "c") if p.suffix == ".h").read_text(encoding="utf-8")
    assert "#define FAST_IS_FD 1\n#define FAST_BRS 1\n" in header
    assert "#define SLOW_IS_FD 1\n#define SLOW_BRS 0\n" in header
    mod = _import(generate_py(cmap, tmp_path / "py")[0])
    assert (mod.Fast.IS_EXTENDED, mod.Fast.IS_FD, mod.Fast.BITRATE_SWITCH) == (False, True, True)
    assert (mod.Slow.IS_FD, mod.Slow.BITRATE_SWITCH) == (True, False)


def test_classic_can_has_no_fd_flags(ref_map, tmp_path):
    header = next(p for p in generate_c(ref_map, tmp_path / "c") if p.suffix == ".h").read_text(encoding="utf-8")
    assert "_IS_FD" not in header and "_BRS" not in header
    mod = _import(generate_py(ref_map, tmp_path / "py")[0])
    frame = next(v for v in vars(mod).values() if isinstance(v, type) and hasattr(v, "BITRATE_SWITCH"))
    assert (frame.IS_FD, frame.BITRATE_SWITCH) == (False, False)


GATEWAY_MAP = """
mapcan: 2
document: {{title: {title}, version: "{version}", language: en}}
buses:
{buses}
"""
GATEWAY_BUS = """
  - name: {bus}
    protocol: canopen
    devices:
      - name: gw
        node_id: {node}
        frames:
          - name: status
            canopen: pdo_tx1
            length: 1
            signals:
              - {{name: s, encoding: number, byte: 0, byte_length: 1}}
          - name: {bus}_only
            canopen: pdo_tx2
            length: 1
            signals:
              - {{name: s, encoding: number, byte: 0, byte_length: 1}}
"""


def _gateway_map(title, version, *buses):
    text = GATEWAY_MAP.format(title=title, version=version, buses="".join(
        GATEWAY_BUS.format(bus=b, node=0x10 + i) for i, b in enumerate(buses)))
    res, report = run(text)
    assert not [d for d in report.diagnostics if d.level == "error"], report.diagnostics
    return res.map


def test_names_shared_by_buses_are_qualified(tmp_path):
    """A frame or device name on several buses gets the bus; a unique one keeps its name."""
    h = {p.stem: p.read_text(encoding="utf-8")
         for p in generate_c(_gateway_map("gw", "1.0", "body", "chassis"), tmp_path) if p.suffix == ".h"}
    assert "#define BODY_STATUS_ID " in h["body"] and "int body_status_pack(" in h["body"]
    assert "#define CHASSIS_STATUS_ID " in h["chassis"] and "#define CHASSIS_GW_NODE_ID 0x11u" in h["chassis"]
    assert "#define BODY_ONLY_ID " in h["body"] and "int body_only_pack(" in h["body"]
    assert "#define BODY_MAP_VERSION_MAJOR 1u" in h["body"]


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_headers_of_buses_and_maps_build_together(tmp_path):
    """A gateway includes the headers of every bus, and of two maps (with MAPCAN_NO_DEPRECATED)."""
    sources = generate_c(_gateway_map("gw", "1.0", "body", "chassis"), tmp_path)
    sources += generate_c(_gateway_map("service", "2.3", "diag"), tmp_path)
    headers = [p for p in sources if p.suffix == ".h"]
    main = [f'#include "{p.name}"' for p in headers] + [
        "int main(void) {",
        "    uint8_t buf[8];",
        "    body_status_t a = {1u};",
        "    chassis_status_t b = {2u};",
        "    if (body_status_pack(buf, sizeof buf, &a) != 1 || chassis_status_pack(buf, sizeof buf, &b) != 1) {",
        "        return 1;",
        "    }",
        "    return (BODY_MAP_VERSION_MAJOR == 1u && DIAG_MAP_VERSION_MINOR == 3u && buf[0] == 2u) ? 0 : 2;",
        "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    "-DMAPCAN_NO_DEPRECATED", str(tmp_path / "main.c"),
                    *(str(p) for p in sources if p.suffix == ".c"), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    subprocess.run([str(exe)], check=True)


INVALID_MAP = """
mapcan: 2
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 8
        signals:
          - {name: speed, encoding: number, byte: 0, byte_length: 2, factor: 0.125, unit: rpm,
             invalid_raw: {not_available: [0xFF00..0xFFFF], error: [0xFE00..0xFEFF, 7]}}
          - {name: temp, encoding: number, byte: 2, byte_length: 1, representation: twos_complement, unit: C,
             invalid_raw: [-128, -127..-120]}
"""
# raw value → (not available, error) for speed
INVALID_CASES = [(0xFF00, 1, 0), (0xFFFF, 1, 0), (0xFE10, 0, 1), (7, 0, 1), (100, 0, 0)]


def test_invalid_helpers_python(tmp_path):
    from mapcan.loader import loads

    mod = _import(generate_py(loads(INVALID_MAP, "t.yaml").map, tmp_path)[0])
    for raw, na, err in INVALID_CASES:
        assert (mod.f_speed_is_not_available(raw), mod.f_speed_is_error(raw)) == (bool(na), bool(err))
    assert [mod.f_temp_is_not_available(v) for v in (-128, -124, -119, 5)] == [True, True, False, False]


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_invalid_helpers_c(tmp_path):
    from mapcan.loader import loads

    sources = [p for p in generate_c(loads(INVALID_MAP, "t.yaml").map, tmp_path) if p.suffix == ".c"]
    main = ["#include <stdio.h>", '#include "bus.h"', "int main(void) {"]
    main += [f'    printf("%d %d\\n", f_speed_is_not_available({raw}u), f_speed_is_error({raw}u));'
             for raw, _, _ in INVALID_CASES]
    main += ["    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split()
    assert out == [str(x) for _, na, err in INVALID_CASES for x in (na, err)]


STRING_MAP = """
mapcan: 2
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: ident
        id: 0x100
        length: 8
        signals:
          - {name: code, encoding: bytes, charset: ascii, byte: 0, byte_length: 5, terminator: "*"}
          - {name: tag, encoding: bytes, charset: ascii, byte: 5, byte_length: 3}
"""


def test_strings_python(tmp_path):
    from mapcan.loader import loads

    mod = _import(generate_py(loads(STRING_MAP, "t.yaml").map, tmp_path)[0])
    packed = mod.Ident(code="AB", tag="xyz").pack()
    assert packed == b"AB***xyz"
    back = mod.Ident.unpack(packed)
    assert (back.code, back.tag) == ("AB", "xyz")
    assert mod.Ident.unpack(b"ABCDEq" + bytes(2)).tag == "q"      # trailing 0x00 bytes are not text


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_strings_c(tmp_path):
    from mapcan.loader import loads

    sources = [p for p in generate_c(loads(STRING_MAP, "t.yaml").map, tmp_path) if p.suffix == ".c"]
    main = ["#include <stdio.h>", "#include <string.h>", '#include "bus.h"', "int main(void) {",
            "    ident_t m, u;", "    uint8_t buf[8];",
            '    memcpy(m.code, "AB***", 5);', '    memcpy(m.tag, "xyz", 3);',
            "    ident_pack(buf, sizeof buf, &m);", "    ident_unpack(&u, buf, sizeof buf);",
            '    printf("%.8s", (const char *)buf);', '    printf(" %.5s %.3s", u.code, u.tag);', '    puts("");',
            "    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split()
    assert out == ["AB***xyz", "AB***", "xyz"]


RANGE_MAP = """
mapcan: 2
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 4
        signals:
          - {name: u5, encoding: number, start_bit: 0, bit_length: 5, factor: 0.5}
          - {name: s6, encoding: number, start_bit: 8, bit_length: 6, representation: twos_complement,
             factor: 0.5}
          - {name: o8, encoding: number, byte: 2, byte_length: 1, representation: ones_complement}
          - {name: u8, encoding: number, byte: 3, byte_length: 1}
"""
# Physical value → raw, the same in C and Python: rounded half away from zero, saturated to the field
RANGE_PHYS = [("u5", 1000.0, 31), ("u5", -3.0, 0), ("u5", 0.25, 1), ("u5", 1.25, 3),
              ("s6", 100.0, 31), ("s6", -100.0, -32), ("s6", -1.25, -3)]
# Raw values outside the field: C saturates them in pack()
RANGE_RAW = {"u5": 40, "s6": -40, "o8": -128, "u8": 200}
RANGE_SATURATED = {"u5": 31, "s6": -32, "o8": -127, "u8": 200}


def test_out_of_range_python(tmp_path):
    from mapcan.loader import loads

    mod = _import(generate_py(loads(RANGE_MAP, "t.yaml").map, tmp_path)[0])
    m = mod.F()
    for name, phys, raw in RANGE_PHYS:
        setattr(m, f"{name}_phys", phys)
        assert getattr(m, name) == raw, (name, phys)
    for name, raw in RANGE_RAW.items():
        if raw != RANGE_SATURATED[name]:
            with pytest.raises(ValueError, match=rf"f\.{name}: value {raw} "):
                mod.F(**{name: raw}).pack()
    assert mod.F(**RANGE_SATURATED).pack() == bytes([31, 0x20, 0x80, 200])


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_out_of_range_c_matches_python(tmp_path):
    from mapcan.loader import loads

    cmap = loads(RANGE_MAP, "t.yaml").map
    mod = _import(generate_py(cmap, tmp_path)[0])
    sources = [p for p in generate_c(cmap, tmp_path) if p.suffix == ".c"]
    main = ["#include <stdio.h>", "#include <inttypes.h>", '#include "bus.h"', "int main(void) {",
            "    uint8_t buf[4];", "    f_t m;"]
    main += [f'    printf("%" PRId64 "\\n", (int64_t)f_{name}_from_phys({phys}f));' for name, phys, _ in RANGE_PHYS]
    main += [f"    m.{k} = ({'uint8_t' if k.startswith('u') else 'int8_t'})({v});" for k, v in RANGE_RAW.items()]
    main += ["    f_pack(buf, sizeof buf, &m);", '    for (int i = 0; i < 4; i++) printf("%02X ", buf[i]);',
             "    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split()
    assert [int(x) for x in out[:len(RANGE_PHYS)]] == [raw for _, _, raw in RANGE_PHYS]
    assert bytes.fromhex("".join(out[len(RANGE_PHYS):])) == mod.F(**RANGE_SATURATED).pack()


ENUM_MAP = """
mapcan: 2
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 2
        signals:
          - {name: mode, encoding: enum, byte: 0, byte_length: 1, initial: 2,
             values: {0: OFF, 1: ON, 2: STANDBY}}
          - {name: gear, encoding: enum, byte: 1, byte_length: 1, values: {1: FIRST, 2: SECOND}}
"""


def test_python_enum_fields(tmp_path):
    """Enum fields hold IntEnum members; a raw value without a name stays an int."""
    import typing

    from mapcan.loader import loads

    mod = _import(generate_py(loads(ENUM_MAP, "t.yaml").map, tmp_path)[0])
    m = mod.F()
    assert m.mode is mod.FMode.STANDBY and m.gear == 0 and type(m.gear) is int
    assert typing.get_type_hints(mod.F)["mode"] is mod.FMode
    back = mod.F.unpack(bytes([1, 7]))
    assert back.mode is mod.FMode.ON
    assert back.gear == 7 and type(back.gear) is int
    assert back.pack() == bytes([1, 7])
    assert mod.F(mode=mod.FMode.OFF, gear=mod.FGear.SECOND).pack() == bytes([0, 2])


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_c_init_matches_python(cmap, py_modules, tmp_path):
    """<frame>_init() + pack() in C gives the bytes of Frame().pack() in Python."""
    sources = [p for p in generate_c(cmap, tmp_path) if p.suffix == ".c"]
    main = ["#include <stdio.h>"] + [f'#include "{p.stem}.h"' for p in sources] + [
            "int main(void) {", "    uint8_t buf[64];", "    int rc;"]
    expected = []
    for bus in cmap.buses:
        g = CGen(cmap, bus)
        for f in frames_with_layout(bus):
            t = g.p(g.frame_name(f))
            main += ["    {", f"        {t}_t m;", f"        {t}_init(&m);",
                     f"        rc = {t}_pack(buf, sizeof buf, &m);", f'        printf("{f.name}");',
                     '        for (int i = 0; i < rc; i++) printf(" %02X", buf[i]);', '        printf("\\n");', "    }"]
            data = getattr(py_modules[bus.name], _cls(f.name))().pack()
            expected.append(f.name + "".join(f" {b:02X}" for b in data))
    main += ["    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()
    assert [line.strip() for line in out] == expected


MUX_MAP = """
mapcan: 2
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 3
        signals:
          - {name: sel, encoding: number, byte: 0, byte_length: 1, multiplexer: true}
          - {name: a, encoding: number, byte: 1, byte_length: 1, mux: 0, initial: 9}
          - {name: b, encoding: number, byte: 1, byte_length: 1, mux: 1}
          - {name: tag, encoding: bytes, charset: ascii, byte: 2, byte_length: 1, mux: 1, terminator: "*"}
"""


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_c_unpack_leaves_no_stale_multiplexed_signals(tmp_path):
    from mapcan.loader import loads

    sources = [p for p in generate_c(loads(MUX_MAP, "t.yaml").map, tmp_path) if p.suffix == ".c"]
    show = '    printf("%d %d %d %c\\n", u.sel, u.a, u.b, u.tag[0]);'
    main = ["#include <stdio.h>", '#include "bus.h"', "int main(void) {", "    f_t u;",
            "    const uint8_t sel0[3] = {0u, 5u, 0u};", "    const uint8_t sel1[3] = {1u, 6u, 0x41u};",
            "    f_init(&u);", show,
            "    f_unpack(&u, sel1, sizeof sel1);", "    f_unpack(&u, sel0, sizeof sel0);", show,
            "    f_unpack(&u, sel1, sizeof sel1);", show, "    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()
    assert out == ["0 9 0 *", "0 5 0 *", "1 9 6 A"]


def test_inhibit_time_in_code(tmp_path):
    from mapcan.loader import loads

    timing = "length: 2\n        trigger: event\n        inhibit_ms: 0.5"
    cmap = loads(ENUM_MAP.replace("length: 2", timing), "t.yaml").map
    header = next(p for p in generate_c(cmap, tmp_path / "c") if p.suffix == ".h").read_text(encoding="utf-8")
    assert "#define F_INHIBIT_US 500u\n" in header
    assert _import(generate_py(cmap, tmp_path / "py")[0]).F_INHIBIT_MS == 0.5


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_random_layouts_c_matches_python(tmp_path):
    """The unrolled bit access of the C code against the Python module: random positions, lengths, byte orders and
    representations, packed and unpacked (one signal per frame, so any layout fits)."""
    import random

    from mapcan.loader import loads

    rnd = random.Random(87)
    kinds = ["raw", "raw", "twos_complement", "ones_complement", "sign_magnitude", "float"]
    frames, values = [], {}
    while len(frames) < 150:
        kind = rnd.choice(kinds)
        length = rnd.choice([32, 64]) if kind == "float" else rnd.randint(1 if kind == "raw" else 2, 64)
        order = rnd.choice(["little_endian", "big_endian"])
        start = rnd.randint(0, 16 * 8 - 1)
        sig = Signal(name="s", encoding="number", start_bit=start, bit_length=length,
                     byte_order=order, representation="unsigned" if kind == "raw" else kind)
        if any(not 0 <= b < 16 for b, *_ in CGen._chunks(sig)):
            continue
        name = f"f{len(frames)}"
        rep = f", representation: {kind}" if kind != "raw" else ""
        frames.append(f"      - {{name: {name}, id: {0x100 + len(frames)}, length: 16, signals: [{{name: s, "
                      f"encoding: number, start_bit: {start}, bit_length: {length}, "
                      f"byte_order: {order}{rep}}}]}}")
        if kind == "float":
            values[name] = rnd.uniform(-1e6, 1e6) if length == 64 else struct.unpack("<f", struct.pack(
                "<f", rnd.uniform(-1e3, 1e3)))[0]
        else:
            lo, hi = B.raw_range(length, kind != "raw", None if kind == "raw" else kind)
            values[name] = rnd.choice([lo, hi, 0, rnd.randint(lo, hi)])
    text = ("mapcan: 2\ndocument: {title: T, language: en}\nbuses:\n  - name: bus\n    protocol: can\n"
            "    fd: true\n    frames:\n" + "\n".join(frames) + "\n")
    res = loads(text, "t.yaml")
    assert res.map is not None, res.report.sorted()[:3]
    cmap = res.map
    mod = _import(generate_py(cmap, tmp_path)[0])
    sources = [p for p in generate_c(cmap, tmp_path) if p.suffix == ".c"]
    g = CGen(cmap, cmap.buses[0])
    main = ["#include <stdio.h>", "#include <inttypes.h>", '#include "bus.h"', "int main(void) {",
            "    uint8_t buf[16];"]
    expected = []
    for f in frames_with_layout(cmap.buses[0]):
        s = f.layout[0]
        v = values[f.name]
        main += ["    {", f"        {f.name}_t m, u;", f"        m.s = ({g.ctype(s)}){_c_lit(s, v)};",
                 f"        {f.name}_pack(buf, sizeof buf, &m);",
                 '        for (int i = 0; i < 16; i++) printf("%02X", buf[i]);',
                 f"        {f.name}_unpack(&u, buf, sizeof buf);"]
        if s.is_float:
            w = 64 if s.bit_length == 64 else 32
            main.append(f'        printf(" %" PRIu64 "\\n", (uint64_t)mapcan_f{w}_to_bits(u.s));')
            fmt, ufmt = ("<d", "<Q") if w == 64 else ("<f", "<I")
            shown = struct.unpack(ufmt, struct.pack(fmt, v))[0]
        else:
            main.append('        printf(" %" PRId64 "\\n", (int64_t)u.s);')
            shown = v
        main.append("    }")
        data = getattr(mod, _cls(f.name))(s=v).pack()
        assert getattr(mod, _cls(f.name)).unpack(data).s == v, f.name
        expected.append(f"{data.hex().upper()} {shown}")
    main += ["    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic", "-O2",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()
    assert [line.strip() for line in out] == expected


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_phys_type_double(tmp_path):
    from typer.testing import CliRunner

    from mapcan.cli import app

    (tmp_path / "m.yaml").write_text(BOUNDS_MAP, encoding="utf-8")
    r = CliRunner().invoke(app, ["gen", "c", str(tmp_path / "m.yaml"), "-o", str(tmp_path), "--phys-type", "double"])
    assert r.exit_code == 0, r.output
    header = (tmp_path / "bus.h").read_text(encoding="utf-8")
    assert "static inline double f4_s8_to_phys(int8_t raw)" in header
    assert "static inline int8_t f4_s8_from_phys(double phys)" in header
    (tmp_path / "main.c").write_text('#include <stdio.h>\n#include "bus.h"\nint main(void) {\n'
                                     '    printf("%d %.17g\\n", f4_s8_from_phys(-3.75), f4_s8_to_phys(-7));\n'
                                     "    return 0;\n}\n", encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), str(tmp_path / "bus.c"), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    assert subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split() == ["-8", "-3.5"]
    r = CliRunner().invoke(app, ["gen", "c", str(tmp_path / "m.yaml"), "-o", str(tmp_path), "--phys-type", "half"])
    assert r.exit_code != 0


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_device_code(cmap, py_modules, tmp_path):
    """mapcan gen c --devices: each device packs the frames it sends as the Python module does, and its dispatch
    unpacks the frames it receives (bytes from the Python module) into its RX state; one program per device."""
    from mapcan.codegen.c import DeviceGen, generate_c_devices

    files = generate_c_devices(cmap, tmp_path)
    assert files
    checked = 0
    for bus in cmap.buses:
        mod = py_modules[bus.name]
        for dev in bus.devices:
            g = DeviceGen(cmap, bus, dev.name)
            if not g.tx and not g.rx:
                continue
            header = (tmp_path / f"{g.base}.h").read_text(encoding="utf-8")
            main = ["#include <stdio.h>", "#include <inttypes.h>", f'#include "{g.base}.h"', "int main(void) {",
                    "    uint8_t buf[64];", "    int rc;"]
            expected = []
            for f in g.tx:
                t = g.p(g.frame_name(f))
                assert f"int {t}_pack(" in header
                vals = sample(f)
                main += ["    {", f"        {t}_t m;", f"        {t}_init(&m);"]
                main += [f"        m.{s.name} = ({g.ctype(s)}){_c_lit(s, vals[s.name])};" for s in present(f, vals)
                         if not is_byte_array(s)]
                main += [f"        rc = {t}_pack(buf, sizeof buf, &m);", f'        printf("{f.name}");',
                         '        for (int i = 0; i < rc; i++) printf(" %02X", buf[i]);', '        printf("\\n");',
                         "    }"]
                data = getattr(mod, _cls(f.name))(**{s.name: vals[s.name] for s in present(f, vals)
                                                     if not is_byte_array(s)}).pack()
                expected.append(f.name + "".join(f" {b:02X}" for b in data))
            if g.rx:
                rx = g.p(g.D, "rx")
                main += [f"    static {rx}_t rx;", f"    {g.p(g.D, 'rx_init')}(&rx);"]
                for i, f in enumerate(g.rx):
                    t = g.p(g.frame_name(f))
                    assert f"int {t}_pack(" not in header or f in g.tx
                    vals = sample(f)
                    data = getattr(mod, _cls(f.name))(**{s.name: vals[s.name] for s in present(f, vals)
                                                         if not is_byte_array(s)}).pack()
                    lit = ", ".join(f"0x{b:02X}u" for b in data) or "0u"
                    # Received at 1000 ms: timed out after its timeout (of the map, or three periods), not before
                    timeout = f.timeout_ms or (3 * f.cycle_ms if f.cycle_ms else 0)
                    out_fn, idx = g.p(g.D, "rx_timed_out"), g.P(g.D, "RX", g.frame_name(f))
                    main += ["    {", f"        static const uint8_t d[] = {{{lit}}};",
                             f'        printf("{f.name} %d", {out_fn}(&rx, {idx}, 0u));',
                             f"        rc = {g.p(g.D, 'rx_dispatch')}(&rx, 1000u, 0x{f.can_id:X}u, "
                             f"{'true' if f.extended else 'false'}, d, {len(data)}u);",
                             f'        printf(" %d %d %d\\n", rc, {out_fn}(&rx, {idx}, {1000 + timeout}u), '
                             f"{out_fn}(&rx, {idx}, {1001 + timeout}u));"]
                    expected.append(f"{f.name} {int(bool(timeout))} {i} 0 {int(bool(timeout))}")
                    for s in present(f, vals):
                        if is_byte_array(s) or s.is_float:
                            continue
                        main.append(f'        printf("{f.name}.{s.name} %" PRId64 "\\n", '
                                    f"(int64_t)rx.{g.frame_name(f)}.{s.name});")
                        expected.append(f"{f.name}.{s.name} {vals[s.name]}")
                    main.append("    }")
                main.append(f'    printf("unknown %d\\n", {g.p(g.D, "rx_dispatch")}(&rx, 0u, 0x7FFu, true, buf, 8u));')
                expected.append("unknown -1")
            main += ["    return 0;", "}"]
            src = tmp_path / f"main_{g.base}.c"
            src.write_text("\n".join(main), encoding="utf-8")
            exe = tmp_path / f"{g.base}.exe"
            subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic", str(src),
                            str(tmp_path / f"{g.base}.c"), "-I", str(tmp_path), "-o", str(exe)],
                           check=True, capture_output=True, text=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()
            assert [line.strip() for line in out] == expected, g.base
            checked += 1
    assert checked >= 1


def test_device_tables():
    """The TX schedule, the received frames and the acceptance filters of a device."""
    from mapcan.codegen.c import DeviceGen

    cmap = load(ROOT / "examples" / "vehicle-can.yaml").map
    g = DeviceGen(cmap, cmap.buses[0], "bms")
    h, c = g.header(), g.source()
    assert [f.name for f in g.tx] == ["bms_status", "bms_cells"] and [f.name for f in g.rx] == ["vcu_command"]
    assert "#define BMS_RX_FILTER_STD_ID 0x200u\n#define BMS_RX_FILTER_STD_MASK 0x7FFu" in h
    assert "{BMS_STATUS_ID, BMS_STATUS_LENGTH, false, false, 100u, false, 0u}," in c
    # A frame the device does not send or receive is left out; a received one has no pack()
    assert "vcu_status" not in h and "int vcu_command_pack(" not in h and "int vcu_command_unpack(" in h
    # Common bits of several IDs: one filter that lets them all through
    pairs = DeviceGen._filter([type("F", (), {"can_id": i})() for i in (0x100, 0x101, 0x110)], 0x7FF)
    assert pairs == (0x100, 0x7EE)


def test_gen_c_device_cli(tmp_path):
    from typer.testing import CliRunner

    from mapcan.cli import app

    m = str(ROOT / "examples" / "vehicle-can.yaml")
    r = CliRunner().invoke(app, ["gen", "c", m, "-o", str(tmp_path), "--device", "bms"])
    assert r.exit_code == 0, r.output
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bms.c", "bms.h"]
    r = CliRunner().invoke(app, ["gen", "c", m, "-o", str(tmp_path), "--device", "nobody"])
    assert r.exit_code != 0 and "nobody" in r.output


LIMITS_MAP = """
mapcan: 2
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 4
        trigger: event
        signals:
          - {name: sel, encoding: number, byte: 0, byte_length: 1, multiplexer: true}
          - {name: temp, encoding: number, byte: 1, byte_length: 1, factor: 0.5, offset: -10, unit: C,
             min: -5, max: 20, initial: 0, mux: 1}
          - {name: neg, encoding: number, byte: 2, byte_length: 1, factor: -2, unit: V, min: -100, max: 10,
             representation: twos_complement, mux: [1, 2]}
          - {name: full, encoding: number, byte: 3, byte_length: 1, factor: 1, unit: A, min: 0, max: 255}
"""
# temp: raw (min + 10) / 0.5 = 10 .. 60; neg (factor < 0): raw -5 .. 50; full: min..max is the whole field
LIMITS = {"temp": (10, 60), "neg": (-5, 50)}


def test_in_range_python(tmp_path):
    from mapcan.loader import loads

    mod = _import(generate_py(loads(LIMITS_MAP, "t.yaml").map, tmp_path)[0])
    for name, (lo, hi) in LIMITS.items():
        fn = getattr(mod, f"f_{name}_in_range")
        assert [fn(v) for v in (lo - 1, lo, hi, hi + 1)] == [False, True, True, False], name
    assert not hasattr(mod, "f_full_in_range") and mod.F_ON_EVENT is True


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_in_range_initial_and_active_c(tmp_path):
    from mapcan.loader import loads

    sources = [p for p in generate_c(loads(LIMITS_MAP, "t.yaml").map, tmp_path) if p.suffix == ".c"]
    header = (tmp_path / "bus.h").read_text(encoding="utf-8")
    assert "#define F_ON_EVENT 1\n" in header and "f_full_in_range" not in header
    main = ["#include <stdio.h>", '#include "bus.h"', "int main(void) {", "    f_t m;"]
    for name, (lo, hi) in LIMITS.items():
        ctype = "int8_t" if name == "neg" else "uint8_t"
        main += [f'    printf("%d", f_{name}_in_range(({ctype})({v})));' for v in (lo - 1, lo, hi, hi + 1)]
    main += ['    printf("\\n");',
             # The constant holds the initial values, as f_init() sets them
             "    f_init(&m);",
             '    printf("%d %d %d %d\\n", m.temp, F_INITIAL.temp, m.sel, F_INITIAL.neg);',
             # Which multiplexed signals the selector value makes active
             "    m.sel = 2;",
             '    printf("%d %d\\n", f_temp_is_active(&m), f_neg_is_active(&m));',
             "    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split()
    assert out == ["01100110", "20", "20", "0", "0", "0", "1"]


def test_python_device_module(tmp_path):
    """A module of one device for a test bench: its frames, TX_FRAMES, RX_FRAMES, DECODERS of the received ones."""
    from typer.testing import CliRunner

    from mapcan.cli import app

    m = str(ROOT / "examples" / "vehicle-can.yaml")
    r = CliRunner().invoke(app, ["gen", "py", m, "-o", str(tmp_path), "--device", "bms"])
    assert r.exit_code == 0, r.output
    mod = _import(tmp_path / "bms_mapcan.py")
    assert mod.TX_FRAMES == [mod.BmsStatus, mod.BmsCells] and mod.RX_FRAMES == [mod.VcuCommand]
    assert set(mod.DECODERS.values()) == {mod.VcuCommand} and not hasattr(mod, "VcuStatus")
    assert mod.decode(mod.VcuCommand.ID, mod.VcuCommand().pack()) == mod.VcuCommand()
    assert mod.decode(mod.BmsStatus.ID, mod.BmsStatus().pack()) is None       # sent by the device, not received
    r = CliRunner().invoke(app, ["gen", "py", m, "-o", str(tmp_path), "--devices"])
    assert r.exit_code == 0 and (tmp_path / "vcu_mapcan.py").exists()
    assert CliRunner().invoke(app, ["gen", "py", m, "-o", str(tmp_path), "--device", "nobody"]).exit_code != 0


def _working_cppcheck() -> str | None:
    """cppcheck if it finds a known error (an installation without its configuration finds nothing)."""
    exe = shutil.which("cppcheck")
    if exe is None:
        return None
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        probe = Path(d) / "probe.c"
        probe.write_text("int main(void) { int a[2] = {0, 0}; return a[3]; }\n", encoding="utf-8")
        try:
            r = subprocess.run([exe, "--quiet", "--template={id}", str(probe)], capture_output=True, text=True,
                               timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
    return exe if "arrayIndexOutOfBounds" in r.stderr else None


CPPCHECK = _working_cppcheck()
# MISRA C:2012 rules the generated code deviates from, with the reason (docs/cli.md, "MISRA C"):
# 2.3, 2.4, 2.5 - a header of a whole bus declares types, tags and macros a firmware may not use;
# 8.7 - pack/unpack/init are the interface of the generated code, called from other files;
# 15.5 - an early return on bad arguments and in the saturation of from_phys (advisory);
# 21.15 - memcpy between a float and an integer of its width is the reading of its IEEE 754 bits.
MISRA_DEVIATIONS = {"2.3", "2.4", "2.5", "8.7", "15.5", "21.15"}


@pytest.mark.skipif(CPPCHECK is None and not os.environ.get("MAPCAN_REQUIRE_CPPCHECK"), reason="нет cppcheck")
@pytest.mark.parametrize("kind", ["bus", "device", "int"])
def test_cppcheck_and_misra(cmap, kind, tmp_path):
    """cppcheck finds nothing in the generated code, and MISRA C:2012 (its addon) nothing beyond the deviations."""
    from mapcan.codegen.c import generate_c_devices

    assert CPPCHECK is not None, "cppcheck not found (MAPCAN_REQUIRE_CPPCHECK is set)"

    files = (generate_c_devices(cmap, tmp_path) if kind == "device"
             else generate_c(cmap, tmp_path, phys_type="float" if kind == "bus" else "int"))
    found = {}
    for src in (p for p in files if p.suffix == ".c"):
        r = subprocess.run([CPPCHECK, "--std=c99", "--enable=warning,style,performance,portability",
                            "--addon=misra", f"--addon-python={sys.executable}", "--quiet", "--template={id}",
                            "-I", str(tmp_path), str(src)], capture_output=True, text=True)
        assert r.returncode == 0, (src.name, r.returncode, r.stderr[-500:])     # a crash is not a clean result
        for rule in r.stderr.split():
            if not (rule.startswith("misra-c2012-") and rule.removeprefix("misra-c2012-") in MISRA_DEVIATIONS):
                found.setdefault(rule, src.name)
    assert not found, found


INT_MAP = """
mapcan: 2
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 8
        signals:
          - {name: temp, encoding: number, byte: 0, byte_length: 1, factor: 0.125, offset: -40, unit: C}
          - {name: neg, encoding: number, byte: 1, byte_length: 1, factor: -2, representation: twos_complement,
             unit: V}
          - {name: third, encoding: number, byte: 2, byte_length: 1, factor: 0.3333333, offset: 0.1234567891234,
             unit: A}
          - {name: big, encoding: number, start_bit: 24, bit_length: 32, factor: 0.001, unit: V}
"""


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_phys_type_int(tmp_path):
    """--phys-type int: physical values as integers in units of the factor's decimals, rounded half away from
    zero and saturated as the float conversion is; a factor that is not decimal keeps the float conversion."""
    from fractions import Fraction

    from mapcan.loader import loads

    sources = [p for p in generate_c(loads(INT_MAP, "t.yaml").map, tmp_path, phys_type="int") if p.suffix == ".c"]
    header = (tmp_path / "bus.h").read_text(encoding="utf-8")
    assert "#define F_TEMP_PHYS_SCALE 1000" in header and "static inline int32_t f_temp_to_phys(uint8_t raw)" in header
    assert "static inline int64_t f_big_to_phys(uint32_t raw)" in header            # beyond int32_t
    assert "static inline float f_third_to_phys(uint8_t raw)" in header              # not a decimal: float

    def to_phys(raw, factor, offset, scale):
        return int(raw * Fraction(factor) * scale + Fraction(offset) * scale)

    def from_phys(phys, factor, offset, scale, lo, hi):
        q = (Fraction(phys) - Fraction(offset) * scale) / (Fraction(factor) * scale)
        r = int(abs(q) + Fraction(1, 2)) * (1 if q >= 0 else -1)
        return min(max(r, lo), hi)

    cases = [("temp", "0.125", "-40", 1000, 0, 255, [0, 1, 200, 255], [-40000, -39937, 0, 1, 100000, -100000]),
             ("neg", "-2", "0", 1, -128, 127, [-128, -1, 0, 127], [-3, -2, -1, 1, 3, 300, -300]),
             ("big", "0.001", "0", 1000, 0, 2**32 - 1, [0, 2**32 - 1], [1, 2**40])]
    main = ["#include <stdio.h>", "#include <inttypes.h>", '#include "bus.h"', "int main(void) {"]
    expected = []
    for name, factor, offset, scale, lo, hi, raws, physs in cases:
        ctype = "int8_t" if name == "neg" else "uint32_t" if name == "big" else "uint8_t"
        ptype = "int64_t" if name == "big" else "int32_t"
        for raw in raws:
            main.append(f'    printf("%" PRId64 "\\n", (int64_t)f_{name}_to_phys(({ctype})({raw}LL)));')
            expected.append(str(to_phys(raw, factor, offset, scale)))
        for phys in physs:
            main.append(f'    printf("%" PRId64 "\\n", (int64_t)f_{name}_from_phys(({ptype})({phys}LL)));')
            expected.append(str(from_phys(phys, factor, offset, scale, lo, hi)))
    main += ["    return 0;", "}"]
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    assert subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split() == expected


ARM_SIZE = shutil.which("arm-none-eabi-size")
# Code (with its constants) of the generated C for Cortex-M0 at -Os, bytes: about a fifth above what it is,
# so a regression (a loop over bits again, 64-bit arithmetic) shows up and small changes do not
CODE_SIZE_BUDGET = {("vehicle-can", "powertrain"): 1000, ("reference", "bus1"): 2300}


@pytest.mark.skipif(ARM_GCC is None or ARM_SIZE is None, reason="нет arm-none-eabi-gcc")
@pytest.mark.parametrize(("map_name", "bus"), list(CODE_SIZE_BUDGET), ids=lambda v: v)
def test_code_size_cortex_m0(map_name, bus, tmp_path):
    path = REFERENCE if map_name == "reference" else ROOT / "examples" / f"{map_name}.yaml"
    generate_c(load(path).map, tmp_path, buses=[bus])
    obj = tmp_path / f"{bus}.o"
    subprocess.run([ARM_GCC, "-std=c99", "-mcpu=cortex-m0", "-mthumb", "-Os", "-ffreestanding", "-c",
                    str(tmp_path / f"{bus}.c"), "-o", str(obj)], check=True, capture_output=True, text=True)
    text = int(subprocess.run([ARM_SIZE, str(obj)], check=True, capture_output=True, text=True)
               .stdout.splitlines()[-1].split()[0])
    assert text <= CODE_SIZE_BUDGET[(map_name, bus)], text


ZEPHYR_STUB = DATA / "zephyr_stub"
STUB_GLOBALS = ["uint32_t stub_uptime_ms;", "struct can_frame stub_sent[16];", "int stub_sent_count;",
                "struct can_filter stub_filters[16];", "int stub_filter_count;",
                "struct k_work_delayable *stub_works[16];", "int stub_work_count;"]


def _zephyr_build(tmp_path, sources, main: list[str], fd: bool = False) -> list[str]:
    (tmp_path / "main.c").write_text("\n".join(main), encoding="utf-8")
    exe = tmp_path / "t.exe"
    subprocess.run([GCC, "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-pedantic",
                    *(["-DCONFIG_CAN_FD_MODE"] if fd else []), "-isystem", str(ZEPHYR_STUB),
                    str(tmp_path / "main.c"), *map(str, sources), "-I", str(tmp_path), "-o", str(exe)],
                   check=True, capture_output=True, text=True)
    return subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
@pytest.mark.parametrize("kind", ["bus", "device"])
def test_zephyr_adapter_builds(cmap, kind, tmp_path):
    """--target zephyr: the adapter of the buses and of the devices builds against the Zephyr CAN API."""
    from mapcan.codegen.c import generate_c_devices

    files = (generate_c(cmap, tmp_path, target="zephyr") if kind == "bus"
             else generate_c_devices(cmap, tmp_path, target="zephyr"))
    zephyr = [p for p in files if p.name.endswith("_zephyr.c")]
    assert zephyr
    for src in zephyr:
        base = src.name.removesuffix("_zephyr.c")
        main = ["#include <zephyr/drivers/can.h>", f'#include "{base}_zephyr.h"', *STUB_GLOBALS,
                "int main(void) { return 0; }"]
        _zephyr_build(tmp_path, [src, tmp_path / f"{base}.c"], main, fd=any(b.fd for b in cmap.buses))


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_zephyr_device(tmp_path):
    """The Zephyr adapter of a device: its TX schedule sends the frames of the Python module at the periods of the
    map (a hook updates the values), filters are installed, received frames are dispatched."""
    from mapcan.codegen.c import generate_c_devices

    cmap = load(ROOT / "examples" / "vehicle-can.yaml").map
    files = generate_c_devices(cmap, tmp_path, ["bms"], target="zephyr")
    mod = _import(generate_py(cmap, tmp_path / "py")[0])
    command = mod.VcuCommand(contactor_request=1, torque_request=-300)
    data = command.pack()
    main = ["#include <stdio.h>", "#include <inttypes.h>", '#include "bms_zephyr.h"', *STUB_GLOBALS,
            "static void hook(bms_tx_frame_t frame, bms_tx_t *tx, void *user_data)", "{", "    (void)user_data;",
            "    if (frame == BMS_TX_BMS_CELLS) {", "        tx->bms_cells.cell_group = 1u;",
            "        tx->bms_cells.cell_4 = 3300u;", "    }", "}",
            "static void show(const struct can_frame *f)", "{",
            '    printf("%" PRIX32 " %u %u", f->id, f->dlc, f->flags);',
            '    for (int i = 0; i < can_dlc_to_bytes(f->dlc); i++) printf(" %02X", f->data[i]);', '    printf("\\n");',
            "}",
            "int main(void)", "{", "    struct device can = {\"can0\"};", "    static bms_tx_t tx;",
            "    static bms_rx_t rx;", "    struct k_msgq q;", "    bms_tx_init(&tx);", "    bms_rx_init(&rx);",
            '    printf("%d\\n", bms_zephyr_tx_start(&can, &tx, hook, NULL));',
            "    for (int i = 0; i < stub_work_count; i++) {",
            "        stub_works[i]->work.handler(&stub_works[i]->work);",
            '        printf("%" PRId64 "\\n", stub_works[i]->delay_ms);', "    }",
            "    for (int i = 0; i < stub_sent_count; i++) show(&stub_sent[i]);",
            '    printf("%d", bms_zephyr_add_rx_filters(&can, &q));',     # the order of printf arguments is not set
            '    printf(" %d %" PRIX32 " %" PRIX32 " %u\\n", stub_filter_count, stub_filters[0].id,',
            "           stub_filters[0].mask, stub_filters[0].flags);",
            "    struct can_frame f = {0};", "    f.id = 0x" + f"{command.ID:X}" + "u;",
            f"    f.dlc = can_bytes_to_dlc({len(data)}u);",
            *[f"    f.data[{i}] = 0x{b:02X}u;" for i, b in enumerate(data)],
            "    stub_uptime_ms = 1234u;",
            '    printf("%d", bms_zephyr_dispatch(&rx, &f));',
            '    printf(" %d %" PRIu32 " %d %d\\n", rx.received[0], rx.received_ms[0],',
            "           (int)rx.vcu_command.contactor_request, (int)rx.vcu_command.torque_request);",
            "    vcu_command_t c;", "    f.flags = CAN_FRAME_IDE;",
            '    printf("%d", vcu_command_from_can_frame(&c, &f));',
            "    f.flags = CAN_FRAME_RTR;", '    printf(" %d\\n", bms_zephyr_dispatch(&rx, &f));',
            "    bms_zephyr_tx_stop();",
            '    printf("%d %d\\n", stub_works[0]->scheduled, stub_works[1]->scheduled);', "    return 0;", "}"]
    out = _zephyr_build(tmp_path, [p for p in files if p.suffix == ".c"], main)
    status, cells = mod.BmsStatus().pack(), mod.BmsCells(cell_group=1, cell_4=3300).pack()
    assert out == ["0", str(mod.BMS_STATUS_CYCLE_MS), str(mod.BMS_CELLS_CYCLE_MS),
                   f"{mod.BmsStatus.ID:X} 8 0" + "".join(f" {b:02X}" for b in status),
                   f"{mod.BmsCells.ID:X} 8 1" + "".join(f" {b:02X}" for b in cells),
                   f"0 1 {mod.VcuCommand.ID:X} 7FF 0",
                   "0 1 1234 1 -300",
                   "-1 -1",
                   "0 0"]


def test_gen_c_target_cli(tmp_path):
    from typer.testing import CliRunner

    from mapcan.cli import app

    m = str(ROOT / "examples" / "vehicle-can.yaml")
    r = CliRunner().invoke(app, ["gen", "c", m, "-o", str(tmp_path), "--device", "bms", "--target", "zephyr"])
    assert r.exit_code == 0, r.output
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bms.c", "bms.h", "bms_zephyr.c", "bms_zephyr.h"]
    assert CliRunner().invoke(app, ["gen", "c", m, "-o", str(tmp_path), "--target", "rtos"]).exit_code != 0
