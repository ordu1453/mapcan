"""A test for every rule of the validator."""

import re

import pytest

from mapcan.docmodel import build_view
from mapcan.validate import RULES, validate_file

from .conftest import DATA, REFERENCE, codes, one_bus, run

OK_SIGNAL = """
        - name: f
          canopen: pdo_tx1
          length: 8
          cycle_ms: 100
          signals:
            - {name: a, encoding: raw, description: x, byte: 0, byte_length: 1}
"""


def test_reference_map_is_clean():
    res, report = validate_file(REFERENCE)
    assert res.map is not None
    assert report.errors == 0, [d.format() for d in report.diagnostics]
    assert report.warnings == 0, [d.format() for d in report.diagnostics]


def test_minimal_ok():
    assert codes(one_bus(OK_SIGNAL)) <= {"missing-description"}


# --------------------------------------------------------------- syntax


def test_yaml_syntax_error_has_line():
    _, rep = run("mapcan: 1\ndocument: [\n")
    d = rep.diagnostics[0]
    assert d.code == "yaml" and d.line is not None


def test_duplicate_key():
    _, rep = run(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - name: a
              encoding: enum
              byte: 0
              byte_length: 1
              values:
                0: A
                0: B
    """))
    assert "yaml" in rep.codes()


def _yaml_diag(text: str):
    _, rep = run(text)
    return next(d for d in rep.diagnostics if d.code in ("yaml", "schema"))


def test_yaml_dash_without_space_points_to_culprit():
    """"-name:" without a space: the message and line are at the culprit, not at the next item."""
    d = _yaml_diag(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            -ndsj:
              fdjopskd
            - {name: a, encoding: raw, byte: 0, byte_length: 1}
    """))
    assert d.code == "yaml" and "space after '-'" in d.message and "- ndsj:" in d.message
    assert d.line == 18


@pytest.mark.parametrize("text, words", [
    ("a: b: c\n", "quote a value"),
    ("a:\n\tb: 1\n", "tab character"),
    ("a:\n  b: 1\n c: 2\n", "bad indentation"),
    ("a: [1, 2\nb: 3\n", "'[' opened on line 1"),
    ("a: {x: 1\nb: 3\n", "'{' opened on line 1"),
    ('a: "x\nb: 1\n', "quote opened on line 1"),
])
def test_yaml_error_hints(text, words):
    assert words in _yaml_diag(text).message


def test_schema_dash_hints():
    d = _yaml_diag(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            -ndsj: x
    """))
    assert d.code == "schema" and "space after '-'" in d.message
    d = _yaml_diag(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - name: a
              encoding: raw
              byte: 0
              byte_length: 1
              -ndsj: x
    """))
    assert "unknown field '-ndsj'" in d.message and "space after '-'" in d.message


def test_schema_missing_field_and_unknown_field():
    _, rep = run(one_bus("""
        - canopen: pdo_tx1
          colour: red
    """))
    msgs = " ".join(d.message for d in rep.diagnostics if d.code == "schema")
    assert "name" in msgs and "colour" in msgs


def test_schema_bad_enum_value_points_to_line():
    text = one_bus("""
        - name: f
          type: pdo_tx9
          length: 8
    """)
    _, rep = run(text)
    d = next(d for d in rep.diagnostics if d.code == "schema")
    assert text.splitlines()[d.line - 1].strip() == "type: pdo_tx9"


def test_number_comma():
    text = one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: v, encoding: scaled, description: x, byte: 0, byte_length: 1, factor: "0,1"}
    """)
    _, rep = run(text)
    d = next(d for d in rep.diagnostics if d.code == "number-comma")
    assert d.level == "error" and "0.1" in d.message
    assert "factor" in text.splitlines()[d.line - 1]


def test_number_cyrillic_x():
    assert "number-cyrillic-x" in codes(one_bus("""
        - name: f
          id: 0х196
          length: 8
    """))


def test_number_quoted_hex():
    assert "number-quoted" in codes(one_bus("""
        - name: f
          id: "0x1A1"
          length: 8
    """))


# --------------------------------------------------------------- names


def test_invalid_identifier():
    assert "invalid-identifier" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: enum, description: x, byte: 0, byte_length: 1, values: {0: NO DATA}}
    """))


def test_name_style():
    c = codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: BadName, encoding: enum, description: x, byte: 0, byte_length: 1, values: {0: lower_case}}
    """))
    assert "name-style" in c


def test_name_style_configurable():
    text = one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: BadName, encoding: raw, description: x, byte: 0, byte_length: 1}
    """, lint="lint:\n  signal_name: PascalCase\n")
    assert "name-style" not in codes(text)


def test_rule_can_be_disabled():
    text = one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: BadName, encoding: raw, description: x, byte: 0, byte_length: 1}
    """, lint="lint:\n  disable: [name-style]\n")
    assert "name-style" not in codes(text)


def test_name_inconsistent():
    _, rep = run(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: enum, description: x, byte: 0, byte_length: 1, values: {0: NO_DATA, 1: OK}}
            - {name: b, encoding: enum, description: x, byte: 1, byte_length: 1, values: {0: NO DATA}}
    """))
    d = next(d for d in rep.diagnostics if d.code == "name-inconsistent")
    assert "'NO DATA'" in d.message and "'NO_DATA'" in d.message


def test_duplicate_signal_name():
    assert "duplicate-signal-name" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: raw, description: x, byte: 0, byte_length: 1}
            - {name: a, encoding: raw, description: x, byte: 1, byte_length: 1}
    """))


def test_duplicate_flag_vs_signal_name():
    """Case 0x1A3: a flag of a bit field is named like a signal of the frame."""
    assert "duplicate-signal-name" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: dc_status, encoding: raw, description: x, byte: 0, byte_length: 1}
            - name: errors
              encoding: bitfield
              description: x
              byte: 1
              byte_length: 1
              flags:
                - {bit: 0, name: dc_status}
    """))


def test_duplicate_enum_name():
    assert "duplicate-enum-name" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: enum, description: x, byte: 0, byte_length: 1, values: {0: OK, 1: OK}}
    """))


# --------------------------------------------------------------- bus


def test_duplicate_can_id():
    assert "duplicate-can-id" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
        - name: g
          id: 0x190
          length: 8
    """))


def test_duplicate_frame_name():
    assert "duplicate-frame-name" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
        - name: f
          canopen: pdo_tx2
          length: 8
    """))


def test_duplicate_device_and_node():
    extra = "      - name: dev\n        node_id: 0x10\n"
    c = codes(one_bus(OK_SIGNAL, devices_extra=extra))
    assert {"duplicate-device-name", "duplicate-node-id"} <= c


def test_node_id_range():
    text = one_bus(OK_SIGNAL).replace("node_id: 0x10", "node_id: 0")
    assert "node-id-range" in codes(text)


def test_frame_id_missing():
    assert "frame-id-missing" in codes(one_bus("""
        - name: f
          length: 8
    """))
    text = one_bus(OK_SIGNAL).replace("        node_id: 0x10\n", "")
    assert "frame-id-missing" in codes(text)


def test_frame_id_missing_points_to_field():
    """The editor highlights the field by the message's path: for a raw frame, the id field."""
    _, rep = run(one_bus("""
        - name: f
          length: 8
    """))
    d = next(d for d in rep.diagnostics if d.code == "frame-id-missing")
    assert d.node[-1] == "id"


def test_can_id_range():
    assert "can-id-range" in codes(one_bus("""
        - name: f
          id: 0x800
          length: 8
    """))


def test_dlc_range():
    assert "dlc-range" in codes(one_bus("""
        - name: f
          id: 0x100
          length: 12
    """))


def test_frame_type_protocol():
    assert "frame-type-protocol" in codes(one_bus("""
        - name: f
          id: 0x100
          canopen: pdo_tx1
          length: 8
    """, protocol="can"))


def test_direction_mismatch():
    assert "direction-mismatch" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          direction: rx
    """))


def test_cycle_rules():
    assert "cycle-unexpected" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          trigger: on_request
          cycle_ms: 10
    """))
    # Every period and on an event
    assert "cycle-unexpected" not in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          trigger: event
          cycle_ms: 10
    """))
    assert "cycle-unexpected" not in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          trigger: on_request
    """))


# --------------------------------------------------------------- layout


def test_signal_out_of_frame():
    assert "signal-out-of-frame" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 2
          signals:
            - {name: a, encoding: raw, description: x, byte: 1, byte_length: 2}
    """))


def test_big_endian_out_of_frame_start():
    assert "signal-out-of-frame" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: raw, description: x, start_bit: 0, bit_length: 16, byte_order: big_endian}
    """))


def test_bit_overlap():
    _, rep = run(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: raw, description: x, byte: 0, byte_length: 1}
            - {name: b, encoding: raw, description: x, start_bit: 4, bit_length: 8}
    """))
    d = next(d for d in rep.diagnostics if d.code == "bit-overlap")
    assert "bits 4..7" in d.message


def test_mux_signals_do_not_overlap():
    c = codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: sel, encoding: enum, description: x, byte: 0, byte_length: 1, multiplexer: true,
               values: {0: A, 1: B}}
            - {name: a, encoding: raw, description: x, byte: 1, byte_length: 1, mux: 0}
            - {name: b, encoding: raw, description: x, byte: 1, byte_length: 1, mux: 1}
    """))
    assert "bit-overlap" not in c


def test_mux_overlap_same_value():
    assert "bit-overlap" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: sel, encoding: raw, description: x, byte: 0, byte_length: 1, multiplexer: true}
            - {name: a, encoding: raw, description: x, byte: 1, byte_length: 1, mux: [0, 1]}
            - {name: b, encoding: raw, description: x, byte: 1, byte_length: 1, mux: 1}
    """))


def test_mux_overlap_with_plain_signal():
    assert "bit-overlap" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: sel, encoding: raw, description: x, byte: 0, byte_length: 1, multiplexer: true}
            - {name: a, encoding: raw, description: x, byte: 1, byte_length: 1, mux: 0}
            - {name: b, encoding: raw, description: x, byte: 1, byte_length: 1}
    """))


def test_mux_rules():
    assert "mux-no-selector" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: raw, description: x, byte: 1, byte_length: 1, mux: 0}
    """))
    c = codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: sel, encoding: enum, description: x, start_bit: 0, bit_length: 1, multiplexer: true,
               values: {0: A, 1: B}}
            - {name: sel2, encoding: raw, description: x, byte: 2, byte_length: 1, multiplexer: true, mux: 1}
            - {name: a, encoding: raw, description: x, byte: 1, byte_length: 1, mux: 2}
            - {name: b, encoding: raw, description: x, byte: 3, byte_length: 1, mux: 1}
    """))
    assert {"mux-multiple-selectors", "mux-value-overflow", "mux-selector-muxed"} <= c
    assert "mux-value-unknown" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: sel, encoding: enum, description: x, byte: 0, byte_length: 1, multiplexer: true, values: {0: A}}
            - {name: a, encoding: raw, description: x, byte: 1, byte_length: 1, mux: 5}
    """))


def test_enum_overflow():
    assert "enum-overflow" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: enum, description: x, start_bit: 0, bit_length: 2, values: {4: TOO_BIG}}
    """))
    assert "enum-overflow" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: enum, description: x, byte: 0, byte_length: 1, values: {-1: NEG}}
    """))
    assert "enum-overflow" not in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: enum, description: x, byte: 0, byte_length: 1, representation: twos_complement,
               values: {-1: NEG}}
    """))


def test_flags_rules():
    c = codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - name: a
              encoding: bitfield
              description: x
              byte: 0
              byte_length: 1
              flags:
                - {bit: 0, name: f0}
                - {bit: 0, name: f1}
                - {bit: 8, name: f2}
    """))
    assert {"flag-overlap", "flag-out-of-field"} <= c
    assert "encoding-field" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, description: x, byte: 0, byte_length: 1, encoding: enum, flags: [{bit: 0, name: f0}]}
    """))
    assert "flag-length" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, description: x, start_bit: 0, bit_length: 2, encoding: flag}
    """))


def test_scaled_rules():
    c = codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: scaled, description: x, byte: 0, byte_length: 1, factor: 0.1, unit: В,
               min: 0, max: 100}
            - {name: b, encoding: scaled, description: x, byte: 1, byte_length: 1, factor: 0}
            - {name: c, encoding: scaled, description: x, byte: 2, byte_length: 1, unit: В, min: 10, max: 5}
    """))
    assert {"range-overflow", "zero-factor", "min-max"} <= c


def test_sdo_rules():
    c = codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          sdo:
            - {name: a, command: 0x2B, index: 0x4010, subindex: 1}
            - {name: b, command: 0x2B, index: 0x4010, subindex: 1}
    """))
    assert {"sdo-frame-type", "sdo-duplicate"} <= c


def _sig(extra: str, encoding: str = "raw") -> str:
    text = OK_SIGNAL.replace("byte_length: 1}", "byte_length: 1, " + extra + "}")
    return one_bus(text.replace("encoding: raw", f"encoding: {encoding}"))


@pytest.mark.parametrize("name", ["default", "class", "unsigned", "pack", "DLC"])
def test_reserved_identifier_signal(name):
    assert "reserved-identifier" in codes(one_bus(OK_SIGNAL.replace("name: a,", f"name: {name},")))


def test_reserved_identifier_value():
    assert "reserved-identifier" in codes(_sig("values: {0: None, 1: OK}", "enum"))
    assert "reserved-identifier" not in codes(_sig("values: {0: NONE, 1: OK}", "enum"))


def test_name_collision():
    assert "name-collision" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: speed, encoding: raw, description: x, byte: 0, byte_length: 1}
            - {name: Speed, encoding: raw, description: x, byte: 1, byte_length: 1}
    """, lint="lint:\n  signal_name: any\n"))
    assert "name-collision" in codes(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: speed, encoding: scaled, description: x, byte: 0, byte_length: 1, factor: 0.1, unit: km/h}
            - {name: speed_phys, encoding: raw, description: x, byte: 1, byte_length: 1}
    """))
    assert "name-collision" in codes(_sig("values: {0: OK, 1: Ok}", "enum"))
    assert "name-collision" in codes(one_bus(OK_SIGNAL + OK_SIGNAL.replace("name: f", "name: F")
                                             .replace("pdo_tx1", "pdo_tx2"), lint="lint:\n  frame_name: any\n"))


def test_canopen_dlc():
    heartbeat = OK_SIGNAL.replace("pdo_tx1", "heartbeat")
    assert "canopen-dlc" in codes(one_bus(heartbeat))
    assert "canopen-dlc" not in codes(one_bus(heartbeat.replace("length: 8", "length: 1")))
    assert "canopen-dlc" not in codes(one_bus(OK_SIGNAL.replace("          canopen: pdo_tx1\n", "")
                                              + "          id: 0x701\n"))


def test_dlc_missing():
    no_dlc = OK_SIGNAL.replace("          length: 8\n", "")
    assert "dlc-missing" in codes(one_bus(no_dlc))
    # A CANopen service frame: its length is from CiA 301
    res, rep = run(one_bus(no_dlc.replace("pdo_tx1", "heartbeat")))
    assert "dlc-missing" not in rep.codes() and res.map.buses[0].devices[0].frames[0].length == 1


def test_bitrate_nonstandard():
    text = one_bus(OK_SIGNAL).replace("    protocol: canopen\n", "    protocol: canopen\n    bitrate: RATE\n")
    assert "bitrate-nonstandard" in codes(text.replace("RATE", "300000"))
    assert "bitrate-nonstandard" not in codes(text.replace("RATE", "250000"))


def test_bus_load():
    text = one_bus(OK_SIGNAL.replace("cycle_ms: 100", "cycle_ms: CYCLE")).replace(
        "    protocol: canopen\n", "    protocol: canopen\n    bitrate: 125000\n")
    # 8 bytes, 11-bit ID: up to 135 bits → 1 ms at 125 kbit/s ≈ 108 %
    assert "bus-load" in codes(text.replace("CYCLE", "1"))
    assert "bus-load" not in codes(text.replace("CYCLE", "10"))
    fd = text.replace("    bitrate: 125000\n", "    bitrate: 125000\n    fd: true\n")
    assert "bus-load" not in codes(fd.replace("CYCLE", "1"))


def test_invalid_in_range():
    assert "invalid-in-range" in codes(_sig("factor: 0.5, unit: V, min: 0, max: 200, invalid_raw: 0xFF", "scaled"))
    assert "invalid-in-range" not in codes(_sig("factor: 0.5, unit: V, min: 0, max: 100, invalid_raw: 0xFF", "scaled"))


def test_missing_unit():
    assert "missing-unit" in codes(_sig("factor: 0.1", "scaled"))
    assert "missing-unit" not in codes(_sig("factor: 0.1, unit: V", "scaled"))


@pytest.mark.parametrize(("extra", "encoding"), [
    ("factor: 0.1", "raw"), ("offset: -40", "enum"), ("unit: V", "enum"), ("min: 0", "bitfield"),
    ("values: {0: OFF}", "raw"), ("representation: twos_complement", "float"), ("invalid_raw: 0xFF", "bytes"),
    ("initial: 1", "bitfield"),
])
def test_encoding_field_rejected(extra, encoding):
    assert "encoding-field" in codes(_sig(extra, encoding))


@pytest.mark.parametrize(("extra", "encoding"), [
    ("unit: ms, min: 0, max: 100", "raw"), ("values: {0: OFF, 1: ON}", "flag"), ("factor: 0.5", "float"),
    ("representation: twos_complement, values: {-1: NEG}", "enum"), ("invalid_raw: 0xFF", "scaled"),
])
def test_encoding_field_allowed(extra, encoding):
    assert "encoding-field" not in codes(_sig(extra, encoding))


def test_no_receivers_and_duplicate_short():
    extra = "      - name: vcu\n        node_id: 0x20\n        short: DEV\n"
    text = one_bus(OK_SIGNAL, devices_extra=extra).replace("        node_id: 0x10\n",
                                                           "        node_id: 0x10\n        short: DEV\n")
    c = codes(text)
    assert {"no-receivers", "duplicate-short"} <= c
    assert "no-receivers" not in codes(text.replace("cycle_ms: 100", "cycle_ms: 100\n          receivers: [vcu]"))


def test_history_version():
    text = one_bus(OK_SIGNAL).replace("  title: Тест\n", "  title: Тест\n  version: '1.1'\n  history:\n"
                                                      "    - {version: '{}', changes: [x]}\n")
    assert "history-version" in codes(text.replace("'{}'", "'1.0'"))
    assert "history-version" not in codes(text.replace("'{}'", "'1.1'"))


def test_info_rules():
    _, rep = run(one_bus("""
        - name: f
          canopen: pdo_tx1
          length: 8
          signals:
            - {name: a, encoding: raw, byte: 0, byte_length: 1}
        - name: g
          canopen: pdo_tx2
          length: 8
    """))
    infos = {d.code for d in rep.diagnostics if d.level == "info"}
    assert {"missing-description", "empty-frame"} <= infos


# --------------------------------------------------------------- file with errors


def test_bad_map_finds_all_problems():
    _, rep = validate_file(DATA / "invalid_map.yaml")
    expected = {
        "number-comma", "number-cyrillic-x", "invalid-identifier", "signal-out-of-frame",
        "bit-overlap", "enum-overflow", "name-inconsistent", "duplicate-signal-name",
        "flag-out-of-field", "name-style", "duplicate-can-id", "cycle-unexpected", "mux-no-selector",
    }
    assert expected <= rep.codes()
    assert all(d.line is not None for d in rep.diagnostics)


def test_legacy_map_rejected():
    """The old format does not pass the schema rather than being accepted silently."""
    _, rep = validate_file(DATA / "legacy.yaml")
    assert rep.errors > 0


def test_signed_code():
    def sig(extra: str) -> str:
        return one_bus(OK_SIGNAL.replace("byte_length: 1}", "byte_length: 1, " + extra + "}"))

    assert "signed-code" not in codes(sig("representation: twos_complement"))
    assert "signed-code" in codes(sig("representation: sign_magnitude"))
    assert "signed-code" in codes(sig("representation: ones_complement"))
    res, _ = run(sig("representation: ones_complement"))
    enc = build_view(res.map)["buses"][0]["devices"][0]["frames"][0]["signals"][0]["encoding"]
    assert enc[-1].endswith("обратный код")


@pytest.mark.parametrize("code", sorted(RULES))
def test_every_rule_documented(code):
    level, desc = RULES[code]
    assert level in {"error", "warning", "info"} and desc


# Maps, not the files they include (part_of): those are checked with their map
@pytest.mark.parametrize("path", [p for p in sorted((DATA.parent.parent / "examples").rglob("*.yaml"))
                                  if re.search(r"^mapcan\s*:", p.read_text(encoding="utf-8"), re.MULTILINE)
                                  and not re.search(r"^part_of\s*:", p.read_text(encoding="utf-8"), re.MULTILINE)],
                         ids=lambda p: p.relative_to(DATA.parent.parent / "examples").as_posix())
def test_examples_are_clean(path):
    res, rep = validate_file(path)
    assert res.map is not None and rep.errors == 0 and rep.warnings == 0, [d.format() for d in rep.diagnostics]


def test_format_key_required():
    """The format version key is required; the former key canmap is no longer accepted."""
    res, _ = run(REFERENCE.read_text(encoding="utf-8").replace("mapcan: 1", "canmap: 1"))
    assert res.map is None


@pytest.mark.parametrize(("old", "new"), [("  language: ru\n", ""), ("    protocol: canopen\n", "")])
def test_language_and_protocol_required(old, new):
    res, _ = run(one_bus(OK_SIGNAL).replace(old, new, 1))
    assert res.map is None


def test_missing_title():
    text = one_bus(OK_SIGNAL).replace("    title: Шина\n", "").replace("        title: Устройство\n", "")
    _, report = run(text)
    found = [(d.level, tuple(d.node)) for d in report.diagnostics if d.code == "missing-title"]
    assert found == [("info", ("buses", 0, "title")), ("info", ("buses", 0, "devices", 0, "title"))]


def test_signed_code_range():
    # In ones' complement and sign-magnitude zero has two forms: −128 cannot be expressed in 8 bits
    text = one_bus(OK_SIGNAL.replace("byte_length: 1}", "byte_length: 1, representation: CODE,"
                                     " values: {-128: MIN}}").replace("encoding: raw", "encoding: enum"))
    assert "enum-overflow" in codes(text.replace("CODE", "ones_complement"))
    assert "enum-overflow" in codes(text.replace("CODE", "sign_magnitude"))
    assert "enum-overflow" not in codes(text.replace("CODE", "twos_complement"))


def test_brs_without_fd():
    frame_brs = one_bus(OK_SIGNAL.replace("          length: 8\n", "          length: 8\n          brs: true\n"))
    assert "brs-without-fd" in codes(frame_brs)
    bus_brs = one_bus(OK_SIGNAL).replace("    protocol: canopen\n", "    protocol: canopen\n    brs: false\n")
    assert "brs-without-fd" in codes(bus_brs)
    fd = frame_brs.replace("    protocol: canopen\n", "    protocol: canopen\n    fd: true\n    brs: false\n")
    assert "brs-without-fd" not in codes(fd)


def test_can_fd_data_phase():
    fd = one_bus(OK_SIGNAL, protocol="can").replace("    protocol: can\n", "    protocol: can\n    fd: true\n"
                                                    "    bitrate: 500000\n    data_bitrate: DATA\n")
    assert not {"data-bitrate-range", "bitrate-nonstandard"} & codes(fd.replace("DATA", "2000000"))
    assert "data-bitrate-range" in codes(fd.replace("DATA", "250000"))
    assert "bitrate-nonstandard" in codes(fd.replace("DATA", "3000000"))
    classic = fd.replace("    fd: true\n", "").replace("DATA", "2000000")
    assert "data-bitrate-without-fd" in codes(classic)


def test_can_fd_bus_load():
    """The data phase of BRS frames is estimated at data_bitrate; without it the load is not estimated."""
    frames = "\n".join(f"""
        - name: f{i}
          id: 0x{0x100 + i:X}
          length: 64
          cycle_ms: 1
          signals: []""" for i in range(3))
    fd = one_bus(frames, protocol="can").replace("    protocol: can\n", "    protocol: can\n    fd: true\n"
                                                 "    bitrate: 500000\n")
    assert "bus-load" not in codes(fd)                                    # BRS frames, no data_bitrate
    assert "bus-load" in codes(fd.replace("    fd: true\n", "    fd: true\n    data_bitrate: 2000000\n"))
    assert "bus-load" not in codes(fd.replace("    fd: true\n", "    fd: true\n    data_bitrate: 8000000\n")
                                   .replace("cycle_ms: 1", "cycle_ms: 10"))


def test_receive_timeout():
    text = one_bus(OK_SIGNAL.replace("cycle_ms: 100", "cycle_ms: 100\n          timeout_ms: TIMEOUT"))
    assert "timeout-short" not in codes(text.replace("TIMEOUT", "300"))
    assert "timeout-short" in codes(text.replace("TIMEOUT", "100"))
    res, _ = run(text.replace("TIMEOUT", "300"))
    frame =build_view(res.map)["buses"][0]["devices"][0]["frames"][0]
    assert frame["period"] == "цикл 100 мс, тайм-аут 300 мс" and frame["timeout_ms"] == 300


def test_string_signals():
    def sig(extra: str) -> str:
        return one_bus(OK_SIGNAL.replace("encoding: raw, description: x, byte: 0, byte_length: 1",
                                         "encoding: string, description: x, " + extra))
    assert not {"string-field", "encoding-field", "schema"} & codes(sig("byte: 0, byte_length: 8, terminator: '*'"))
    assert "string-field" in codes(sig("start_bit: 4, bit_length: 16"))
    assert "string-field" in codes(sig("byte: 0, byte_length: 8, terminator: '**'"))
    assert "encoding-field" in codes(one_bus(OK_SIGNAL.replace("byte_length: 1}", "byte_length: 1, charset: ascii}")))
