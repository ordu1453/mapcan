"""Round-trip pack → unpack для каждого кадра: Python-модуль, C-код, DBC."""

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

from .conftest import REFERENCE, ROOT

PATTERN = 0xA5C396E15A3C691E


def _value(s, i: int) -> int:
    mask = (1 << s.bit_length) - 1
    v = ((PATTERN >> (i * 5 % 40)) | (PATTERN << 7)) & mask
    if s.signed and v & (1 << (s.bit_length - 1)):
        v -= 1 << s.bit_length
    return v


def sample(frame) -> dict:
    """Значения сигналов для теста; селектор выбирает первый мультиплексный набор."""
    vals = {}
    sel = selector_of(frame)
    for i, s in enumerate(frame.layout):
        if is_byte_array(s):
            vals[s.name] = bytes((0x11 * (k + 1) + i) & 0xFF for k in range(s.bit_length // 8))
        else:
            vals[s.name] = 1.5 + 0.25 * i if s.kind == "float" else _value(s, i)
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
            assert len(data) == f.dlc
            back = cls.unpack(data)
            for s in present(f, vals):
                assert getattr(back, s.name) == vals[s.name], (f.name, s.name)
            assert mod.decode(f.can_id, data) == back
            n += 1
    assert n >= 1


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
    """cantools кодирует те же байты, что и сгенерированный модуль."""
    for bus in cmap.buses:
        db = bus_database(cmap, bus)
        dbc = cantools.database.load_string(db.as_dbc_string(), "dbc")
        mod = py_modules[bus.name]
        for f in frames_with_layout(bus):
            if not f.layout:
                continue
            vals = sample(f)
            if any(is_byte_array(s) for s in present(f, vals)):
                continue  # байтовые массивы в DBC — целые 56 бит, проверяются отдельно
            ours = getattr(mod, _cls(f.name))(**vals).pack()
            msg = dbc.get_message_by_frame_id(f.can_id)
            decoded = msg.decode(ours, decode_choices=False, scaling=False)
            for s in present(f, vals):
                if s.kind == "bitfield" and s.flags:
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
    if s.kind == "float":
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
            t = g.p(f.name)
            vals = sample(f)
            main.append("    {")
            main.append(f"        {t}_t m = {{0}}, u = {{0}};")
            for s in f.layout:
                if s.name not in vals:
                    continue
                v = vals[s.name]
                if isinstance(v, bytes):
                    for k, b in enumerate(v):
                        main.append(f"        m.{s.name}[{k}] = 0x{b:02X};")
                else:
                    main.append(f"        m.{s.name} = ({g.ctype(s)}){_c_lit(s, v)};")
            main.append(f"        rc = {t}_pack(buf, sizeof buf, &m);")
            main.append(f'        hex("{f.name}", buf, rc);')
            main.append(f"        if ({t}_unpack(&u, buf, (size_t)rc) != 0) return 1;")
            for s in present(f, vals):
                if is_byte_array(s):
                    main.append(f'        hex("{f.name}.{s.name}", u.{s.name}, {s.bit_length // 8});')
                    expected.append(f"{f.name}.{s.name}" + "".join(f" {b:02X}" for b in vals[s.name]))
                elif s.kind == "float":
                    # Сравнение по точным битам IEEE 754.
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
                main.append(f"        if ({t}_pack(buf, {max(f.dlc - 1, 0)}u, &m) != -1) return 2;")
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
