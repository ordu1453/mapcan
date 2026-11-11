"""Inheritance and export-facing resolution of reusable structures (#158)."""

from mapcan.loader import loads
from mapcan.od import dictionary

MAP = """mapcan: 2
document: {title: Structures, version: 1.0.0, language: en}
buses:
  - name: bus
    protocol: canopen
    objects:
      - {index: 0x1000, name: mandatory, locked: true, data_type: unsigned32}
      - {index: 0x2000, name: optional, data_type: unsigned8}
    structures:
      states: {values: {4: STOPPED, 5: OPERATIONAL}, locked: [5]}
      warnings: {kind: bitmask, values: {1: HOT, 2: LOW_SUPPLY}, locked: [2]}
    devices:
      - name: drive
        node_id: 5
        excluded_objects: [0x1000, 0x2000]
        objects:
          - {index: 0x1000, name: override, data_type: unsigned8}
        structures:
          states: {values: {5: OVERRIDE, 127: PRE_OPERATIONAL}, excluded: [4, 5]}
          warnings: {kind: bitmask, values: {4: SERVICE}, excluded: [1, 2]}
        frames:
          - name: status
            canopen: pdo_tx1
            length: 2
            signals:
              - {name: state, byte: 0, bit_length: 8, encoding: enum, values: 'structure:states'}
              - {name: warnings, byte: 1, bit_length: 8, encoding: bitfield, values: 'structure:warnings'}
"""


def test_inheritance_locks_and_mask_flags():
    loaded = loads(MAP)
    assert loaded.map is not None
    bus = loaded.map.buses[0]
    device = bus.devices[0]
    assert [(o.index, o.name) for o in dictionary(bus, device)] == [(0x1000, "mandatory")]
    state, warnings = device.frames[0].signals
    assert state.values == {5: "OPERATIONAL", 127: "PRE_OPERATIONAL"}
    assert [(flag.bit, flag.name) for flag in warnings.flags] == [(1, "LOW_SUPPLY"), (2, "SERVICE")]
    assert warnings.values is None
    # Source references survive in the editable YAML data.
    assert loaded.raw["buses"][0]["devices"][0]["frames"][0]["signals"][0]["values"] == "structure:states"


def test_disabling_device_structures_keeps_locked_values():
    loaded = loads(MAP.replace("states: {values: {5: OVERRIDE, 127: PRE_OPERATIONAL}, excluded: [4, 5]}",
                              "states: {enabled: false}"))
    assert loaded.map.buses[0].devices[0].frames[0].signals[0].values == {5: "OPERATIONAL"}


def test_missing_reference_is_reported_at_values():
    loaded = loads(MAP.replace("structure:states", "structure:missing"))
    assert any(d.code == "structure" and d.node[-1] == "values" for d in loaded.report.diagnostics)


def test_effective_mask_rejects_non_power_of_two_device_values():
    loaded = loads(MAP.replace("warnings: {kind: bitmask, values: {4: SERVICE}",
                              "warnings: {values: {3: SERVICE}"))
    assert any(d.code == "structure" for d in loaded.report.diagnostics)
