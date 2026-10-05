"""По тесту на каждое правило валидатора."""

import pytest

from canmap.validate import RULES, validate_file

from .conftest import DATA, REFERENCE, codes, one_bus, run

OK_SIGNAL = """
        - name: f
          type: pdo_tx1
          cycle_ms: 100
          signals:
            - {name: a, description: x, byte: 0}
"""


def test_reference_map_is_clean():
    res, report = validate_file(REFERENCE)
    assert res.map is not None
    assert report.errors == 0, [d.format() for d in report.diagnostics]
    assert report.warnings == 0, [d.format() for d in report.diagnostics]


def test_minimal_ok():
    assert codes(one_bus(OK_SIGNAL)) <= {"missing-description"}


# --------------------------------------------------------------- синтаксис


def test_yaml_syntax_error_has_line():
    _, rep = run("canmap: 1\ndocument: [\n")
    d = rep.diagnostics[0]
    assert d.code == "yaml" and d.line is not None


def test_duplicate_key():
    _, rep = run(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - name: a
              byte: 0
              values:
                0: A
                0: B
    """))
    assert "yaml" in rep.codes()


def test_schema_missing_field_and_unknown_field():
    _, rep = run(one_bus("""
        - type: pdo_tx1
          colour: red
    """))
    msgs = " ".join(d.message for d in rep.diagnostics if d.code == "schema")
    assert "name" in msgs and "colour" in msgs


def test_schema_bad_enum_value_points_to_line():
    text = one_bus("""
        - name: f
          type: pdo_tx9
    """)
    _, rep = run(text)
    d = next(d for d in rep.diagnostics if d.code == "schema")
    assert text.splitlines()[d.line - 1].strip() == "type: pdo_tx9"


def test_number_comma():
    text = one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: v, description: x, byte: 0, factor: "0,1"}
    """)
    _, rep = run(text)
    d = next(d for d in rep.diagnostics if d.code == "number-comma")
    assert d.level == "error" and "0.1" in d.message
    assert "factor" in text.splitlines()[d.line - 1]


def test_number_cyrillic_x():
    assert "number-cyrillic-x" in codes(one_bus("""
        - name: f
          id: 0х196
    """))


def test_number_quoted_hex():
    assert "number-quoted" in codes(one_bus("""
        - name: f
          id: "0x196"
    """))


# --------------------------------------------------------------- имена


def test_invalid_identifier():
    assert "invalid-identifier" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 0, values: {0: NO DATA}}
    """))


def test_name_style():
    c = codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: BadName, description: x, byte: 0, values: {0: lower_case}}
    """))
    assert "name-style" in c


def test_name_style_configurable():
    text = one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: BadName, description: x, byte: 0}
    """, lint="lint:\n  signal_name: PascalCase\n")
    assert "name-style" not in codes(text)


def test_rule_can_be_disabled():
    text = one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: BadName, description: x, byte: 0}
    """, lint="lint:\n  disable: [name-style]\n")
    assert "name-style" not in codes(text)


def test_name_inconsistent():
    _, rep = run(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 0, values: {0: NO_DATA, 1: OK}}
            - {name: b, description: x, byte: 1, values: {0: NO DATA}}
    """))
    d = next(d for d in rep.diagnostics if d.code == "name-inconsistent")
    assert "'NO DATA'" in d.message and "'NO_DATA'" in d.message


def test_duplicate_signal_name():
    assert "duplicate-signal-name" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 0}
            - {name: a, description: x, byte: 1}
    """))


def test_duplicate_flag_vs_signal_name():
    """Случай 0x198: флаг битового поля назван как сигнал кадра."""
    assert "duplicate-signal-name" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: dc_status, description: x, byte: 0}
            - name: errors
              description: x
              byte: 1
              flags:
                - {bit: 0, name: dc_status}
    """))


def test_duplicate_enum_name():
    assert "duplicate-enum-name" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 0, values: {0: OK, 1: OK}}
    """))


# --------------------------------------------------------------- шина


def test_duplicate_can_id():
    assert "duplicate-can-id" in codes(one_bus("""
        - name: f
          type: pdo_tx1
        - name: g
          id: 0x190
    """))


def test_duplicate_frame_name():
    assert "duplicate-frame-name" in codes(one_bus("""
        - name: f
          type: pdo_tx1
        - name: f
          type: pdo_tx2
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
          type: raw
    """))
    text = one_bus(OK_SIGNAL).replace("        node_id: 0x10\n", "")
    assert "frame-id-missing" in codes(text)


def test_can_id_range():
    assert "can-id-range" in codes(one_bus("""
        - name: f
          id: 0x800
    """))


def test_dlc_range():
    assert "dlc-range" in codes(one_bus("""
        - name: f
          id: 0x100
          dlc: 12
    """))


def test_frame_type_protocol():
    assert "frame-type-protocol" in codes(one_bus("""
        - name: f
          id: 0x100
          type: pdo_tx1
    """, protocol="can"))


def test_direction_mismatch():
    assert "direction-mismatch" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          direction: rx
    """))


def test_cycle_rules():
    assert "cycle-missing" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          transmission: {mode: cyclic}
    """))
    assert "cycle-unexpected" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          transmission: {mode: event, cycle_ms: 10}
    """))


# --------------------------------------------------------------- раскладка


def test_signal_out_of_frame():
    assert "signal-out-of-frame" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          dlc: 2
          signals:
            - {name: a, description: x, byte: 1, byte_length: 2}
    """))


def test_big_endian_out_of_frame_start():
    assert "signal-out-of-frame" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, start_bit: 0, bit_length: 16, byte_order: big_endian}
    """))


def test_bit_overlap():
    _, rep = run(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 0}
            - {name: b, description: x, start_bit: 4, bit_length: 8}
    """))
    d = next(d for d in rep.diagnostics if d.code == "bit-overlap")
    assert "биты 4..7" in d.message


def test_mux_signals_do_not_overlap():
    c = codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: sel, description: x, byte: 0, multiplexer: true, values: {0: A, 1: B}}
            - {name: a, description: x, byte: 1, mux: 0}
            - {name: b, description: x, byte: 1, mux: 1}
    """))
    assert "bit-overlap" not in c


def test_mux_overlap_same_value():
    assert "bit-overlap" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: sel, description: x, byte: 0, multiplexer: true}
            - {name: a, description: x, byte: 1, mux: [0, 1]}
            - {name: b, description: x, byte: 1, mux: 1}
    """))


def test_mux_overlap_with_plain_signal():
    assert "bit-overlap" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: sel, description: x, byte: 0, multiplexer: true}
            - {name: a, description: x, byte: 1, mux: 0}
            - {name: b, description: x, byte: 1}
    """))


def test_mux_rules():
    assert "mux-no-selector" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 1, mux: 0}
    """))
    c = codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: sel, description: x, start_bit: 0, bit_length: 1, multiplexer: true, values: {0: A, 1: B}}
            - {name: sel2, description: x, byte: 2, multiplexer: true, mux: 1}
            - {name: a, description: x, byte: 1, mux: 2}
            - {name: b, description: x, byte: 3, mux: 1}
    """))
    assert {"mux-multiple-selectors", "mux-value-overflow", "mux-selector-muxed"} <= c
    assert "mux-value-unknown" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: sel, description: x, byte: 0, multiplexer: true, values: {0: A}}
            - {name: a, description: x, byte: 1, mux: 5}
    """))


def test_enum_overflow():
    assert "enum-overflow" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, start_bit: 0, bit_length: 2, values: {4: TOO_BIG}}
    """))
    assert "enum-overflow" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 0, values: {-1: NEG}}
    """))
    assert "enum-overflow" not in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 0, signed: true, values: {-1: NEG}}
    """))


def test_flags_rules():
    c = codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - name: a
              description: x
              byte: 0
              flags:
                - {bit: 0, name: f0}
                - {bit: 0, name: f1}
                - {bit: 8, name: f2}
    """))
    assert {"flag-overlap", "flag-out-of-field"} <= c
    assert "flags-kind" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 0, kind: enum, flags: [{bit: 0, name: f0}]}
    """))
    assert "flag-length" in codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, start_bit: 0, bit_length: 2, kind: flag}
    """))


def test_metric_rules():
    c = codes(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, description: x, byte: 0, factor: 0.1, unit: В, min: 0, max: 100}
            - {name: b, description: x, byte: 1, factor: 0}
            - {name: c, description: x, byte: 2, unit: В, min: 10, max: 5}
    """))
    assert {"metric-range", "metric-factor", "min-max"} <= c


def test_sdo_rules():
    c = codes(one_bus("""
        - name: f
          type: pdo_tx1
          sdo:
            - {name: a, command: 0x2B, index: 0x4010, subindex: 1}
            - {name: b, command: 0x2B, index: 0x4010, subindex: 1}
    """))
    assert {"sdo-frame-type", "sdo-duplicate"} <= c


def test_info_rules():
    _, rep = run(one_bus("""
        - name: f
          type: pdo_tx1
          signals:
            - {name: a, byte: 0}
        - name: g
          type: pdo_tx2
    """))
    infos = {d.code for d in rep.diagnostics if d.level == "info"}
    assert {"missing-description", "empty-frame"} <= infos


# --------------------------------------------------------------- файл с ошибками


def test_bad_map_finds_all_problems():
    _, rep = validate_file(DATA / "bad_map.yaml")
    expected = {
        "number-comma", "number-cyrillic-x", "invalid-identifier", "signal-out-of-frame",
        "bit-overlap", "enum-overflow", "name-inconsistent", "duplicate-signal-name",
        "flag-out-of-field", "name-style", "duplicate-can-id", "cycle-missing", "mux-no-selector",
    }
    assert expected <= rep.codes()
    assert all(d.line is not None for d in rep.diagnostics)


def test_legacy_map_rejected():
    """Старый формат не проходит схему, а не молча принимается."""
    _, rep = validate_file(DATA / "legacy_v0.yaml")
    assert rep.errors > 0


@pytest.mark.parametrize("code", sorted(RULES))
def test_every_rule_documented(code):
    level, desc = RULES[code]
    assert level in {"error", "warning", "info"} and desc


@pytest.mark.parametrize("path", sorted((DATA.parent.parent / "examples").rglob("*.yaml")),
                         ids=lambda p: p.relative_to(DATA.parent.parent / "examples").as_posix())
def test_examples_are_clean(path):
    res, rep = validate_file(path)
    assert res.map is not None and rep.errors == 0 and rep.warnings == 0, [d.format() for d in rep.diagnostics]
