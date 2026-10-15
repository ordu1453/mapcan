"""Round trip pack → unpack for every frame: Python module, C code, DBC."""

from __future__ import annotations

import importlib.util
import shutil
import struct
import subprocess
import sys

import cantools
import pytest

from mapcan.codegen.c import CGen, generate_c
from mapcan.codegen.common import frames_with_layout, is_byte_array, selector_of
from mapcan.codegen.py import _cls, generate_py
from mapcan.export.dbc import bus_database
from mapcan.loader import load

from .conftest import REFERENCE, ROOT, run

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
        if is_byte_array(s) and s.encoding == "string":
            # Text that fills the field: no terminator, so it reads back the same
            vals[s.name] = "".join(chr(ord("A") + (k + i) % 26) for k in range(s.bit_length // 8))
        elif is_byte_array(s):
            vals[s.name] = bytes((0x11 * (k + 1) + i) & 0xFF for k in range(s.bit_length // 8))
        else:
            vals[s.name] = 1.5 + 0.25 * i if s.encoding == "float" else _value(s, i)
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
mapcan: 1
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    devices:
      - name: a
        frames:
          - {name: std, id: 0x100, length: 1, signals: [{name: s, encoding: raw, byte: 0, byte_length: 1}]}
          - {name: ext, id: 0x100, extended: true, length: 1,
             signals: [{name: e, encoding: raw, byte: 0, byte_length: 1}]}
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
    if s.encoding == "float":
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
                elif s.encoding == "float":
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


ARM_GCC = shutil.which("arm-none-eabi-gcc")


@pytest.mark.skipif(ARM_GCC is None, reason="нет arm-none-eabi-gcc")
def test_c_compiles_for_cortex_m(cmap, tmp_path):
    for src in (p for p in generate_c(cmap, tmp_path) if p.suffix == ".c"):
        subprocess.run([ARM_GCC, "-std=c99", "-mcpu=cortex-m4", "-mthumb", "-Os", "-Wall", "-Wextra",
                        "-Werror", "-ffreestanding", "-c", str(src), "-o", str(src.with_suffix(".o"))],
                       check=True, capture_output=True, text=True)


BOUNDS_MAP = """\
mapcan: 1
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
              - {name: u28, encoding: scaled, start_bit: 0, bit_length: 28, unit: ms}
              - {name: s32, encoding: scaled, start_bit: 28, bit_length: 32, factor: 0.5,
                 representation: twos_complement}
          - name: f2
            id: 0x102
            length: 8
            signals:
              - {name: u64, encoding: scaled, start_bit: 0, bit_length: 64, factor: 2}
          - name: f3
            id: 0x103
            length: 8
            signals:
              - {name: s64, encoding: scaled, start_bit: 0, bit_length: 64, representation: twos_complement, factor: 2}
          - name: f4
            id: 0x104
            length: 8
            signals:
              - {name: s8, encoding: scaled, start_bit: 0, bit_length: 8, representation: twos_complement, factor: 0.5}
"""


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_c_from_phys_bounds(tmp_path):
    """Saturation at the limits of the width and precision of long fields (double, not float)."""
    from mapcan.loader import loads

    cmap = loads(BOUNDS_MAP, "bounds.yaml").map
    sources = [p for p in generate_c(cmap, tmp_path) if p.suffix == ".c"]
    checks = [
        ("f1_u28_from_phys(1e12)", 268435455),        # used to be 2^28: the top bit was lost when packing
        ("f1_u28_from_phys(16777217.0)", 16777217),   # in float it would round to 16777216
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
        "unit: ms}", "unit: ms, initial: 7, description: Time, comment: Raw ms}"))
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
mapcan: 1
document: {title: Test, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 8
        signals:
          - {name: o8, encoding: raw, byte: 0, byte_length: 1, representation: ones_complement}
          - {name: s8, encoding: raw, byte: 1, byte_length: 1, representation: sign_magnitude}
          - {name: o12, encoding: raw, start_bit: 16, bit_length: 12, representation: ones_complement}
          - {name: s16, encoding: raw, byte: 4, byte_length: 2, byte_order: big_endian,
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
mapcan: 1
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
              - {{name: s, encoding: raw, byte: 0, byte_length: 1}}
          - name: {bus}_only
            canopen: pdo_tx2
            length: 1
            signals:
              - {{name: s, encoding: raw, byte: 0, byte_length: 1}}
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
mapcan: 1
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 8
        signals:
          - {name: speed, encoding: scaled, byte: 0, byte_length: 2, factor: 0.125, unit: rpm,
             invalid_raw: {not_available: [0xFF00..0xFFFF], error: [0xFE00..0xFEFF, 7]}}
          - {name: temp, encoding: scaled, byte: 2, byte_length: 1, representation: twos_complement, unit: C,
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
mapcan: 1
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: ident
        id: 0x100
        length: 8
        signals:
          - {name: code, encoding: string, byte: 0, byte_length: 5, terminator: "*"}
          - {name: tag, encoding: string, byte: 5, byte_length: 3}
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
mapcan: 1
document: {title: T, language: en}
buses:
  - name: bus
    protocol: can
    frames:
      - name: f
        id: 0x100
        length: 4
        signals:
          - {name: u5, encoding: scaled, start_bit: 0, bit_length: 5, factor: 0.5}
          - {name: s6, encoding: scaled, start_bit: 8, bit_length: 6, representation: twos_complement}
          - {name: o8, encoding: raw, byte: 2, byte_length: 1, representation: ones_complement}
          - {name: u8, encoding: raw, byte: 3, byte_length: 1}
"""
# Physical value → raw, the same in C and Python: rounded half away from zero, saturated to the field
RANGE_PHYS = [("u5", 1000.0, 31), ("u5", -3.0, 0), ("u5", 0.25, 1), ("u5", 1.25, 3),
              ("s6", 100.0, 31), ("s6", -100.0, -32), ("s6", -2.5, -3)]
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
mapcan: 1
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
