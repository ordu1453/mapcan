"""Values a signal takes from the map (source): map version and layout CRC32; the version format."""

from __future__ import annotations

from mapcan.codegen.c import CGen
from mapcan.codegen.py import PyGen
from mapcan.layout import layout_crc32

from .conftest import ROOT, run

MINIMAL = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8")

VERSION_FRAME = """
          - name: map_info
            canopen: pdo_tx2
            length: 7
            description: Map version
            trigger: on_request
            signals:
              - {name: major, encoding: number, description: x, byte: 0, byte_length: 1, source: map_version.major}
              - {name: minor, encoding: number, description: x, byte: 1, byte_length: 1, source: map_version.minor}
              - {name: patch, encoding: number, description: x, byte: 2, byte_length: 1, source: map_version.patch}
              - {name: crc, encoding: number, description: x, byte: 3, byte_length: 4, source: layout_crc32}
"""


def with_version_frame(version: str = "1.4.2") -> str:
    return MINIMAL.replace("version: 0.1.0", f"version: {version}") + VERSION_FRAME


def signals(res) -> dict:
    frame = next(f for f in res.map.buses[0].all_frames() if f.name == "map_info")
    return {s.name: s for s in frame.signals}


def test_values_come_from_the_map():
    res, report = run(with_version_frame())
    assert not [d for d in report.diagnostics if d.level == "error"], report.diagnostics
    s = signals(res)
    assert [s[k].initial_raw for k in ("major", "minor", "patch")] == [1, 4, 2]
    assert s["crc"].initial_raw == layout_crc32(res.map)


def test_crc_covers_the_layout_only():
    base, _ = run(with_version_frame())
    crc = layout_crc32(base.map)
    # A new version, names and texts do not change it
    renamed, _ = run(with_version_frame("2.0.0").replace("Pump state", "State").replace("name: mode", "name: m"))
    assert layout_crc32(renamed.map) == crc
    # A signal moved or scaled differently does
    moved, _ = run(with_version_frame().replace("start_bit: 56", "start_bit: 60"))
    assert layout_crc32(moved.map) != crc
    scaled, _ = run(with_version_frame().replace("factor: 0.01", "factor: 0.1"))
    assert layout_crc32(scaled.map) != crc


def test_code_carries_the_map():
    res, _ = run(with_version_frame())
    bus = res.map.buses[0]
    crc = layout_crc32(res.map)
    h = CGen(res.map, bus, "").header()
    B = bus.name.upper()
    assert f"#define {B}_MAP_VERSION_MAJOR 1u" in h and f"#define {B}_MAP_LAYOUT_CRC32 0x{crc:08X}u" in h
    assert "#define MAP_VERSION_MAJOR 1u /* deprecated" in h     # the former name, until MAPCAN_NO_DEPRECATED
    assert "#define MAP_INFO_MINOR_INITIAL_RAW 4" in h
    py = PyGen(res.map, bus).module()
    assert "MAP_VERSION = (1, 4, 2)" in py and f"MAP_LAYOUT_CRC32 = 0x{crc:08X}" in py
    assert "    minor: int = 4" in py


def test_version_format():
    _, report = run(MINIMAL.replace("version: 0.1.0", "version: rev A"))
    assert "version-format" in report.codes()
    res, report = run(MINIMAL.replace("version: 0.1.0", 'version: "2.1"'))
    assert res.map.document.version_parts == (2, 1, 0) and "version-format" not in report.codes()


def test_source_errors():
    _, report = run(with_version_frame("rev A"))
    assert "source-value" in report.codes()
    _, report = run(with_version_frame("300.0.0"))      # major does not fit in 8 bits
    assert "source-value" in report.codes()
    text = with_version_frame().replace("source: map_version.major}", "source: map_version.major, initial: 1}")
    _, report = run(text)
    assert "source-value" in report.codes()
    # a floating-point number has no source
    text = with_version_frame().replace("encoding: number, description: x, byte: 0",
                                        "encoding: number, description: x, representation: float, byte: 0", 1)
    _, report = run(text)
    assert "encoding-field" in report.codes()
