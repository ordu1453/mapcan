# Signal map format (mapcan, v1)

A signal map is a single YAML file, and every document and code artifact is generated from it.
The format is defined by the JSON Schema in
[`schema/mapcan.schema.json`](../schema/mapcan.schema.json). Add this line at the top of a map:

```yaml
# yaml-language-server: $schema=./schema/mapcan.schema.json
```

and VS Code with the Red Hat *YAML* extension will complete field names and underline errors as
you type. `mapcan schema -o schema.json` writes the schema anywhere you need it.

## Conventions

| Topic | Rule |
|---|---|
| Byte numbering | Starts at 0 |
| Bit numbering | `lsb0`: bit 0 is the least significant bit of byte 0; bit `N` is in byte `N div 8` at position `N mod 8` |
| Signal position | `start_bit` is the position of the **least significant** bit of the value |
| Physical value | `physical = raw * factor + offset` |
| Numbers | Decimal or `0x…`; use a decimal point (`0.1`, not `0,1`) |
| Names | Latin letters, digits and `_` (valid C/Python identifiers). The naming style is set in `lint` |

The numbering is stated explicitly by `document.bit_numbering: lsb0` and printed in every
document.

## File structure

```yaml
mapcan: 1                 # format version (maps with the legacy key canmap: 1 are also accepted)
document: {...}           # metadata and revision history
lint: {...}               # style rules (optional)
buses: [...]              # one or more buses
```

### `document`

| Field | Type | Description |
|---|---|---|
| `title` | text | Document title (required) |
| `subtitle` | text | Subtitle |
| `version` | string | Map version (default `0.1`) |
| `date` | date `YYYY-MM-DD` | Release date |
| `author`, `organization` | string | |
| `language` | `ru` \| `en` | Default document language (default `ru`); `--lang` overrides it at export |
| `bit_numbering` | `lsb0` | Explicit statement of the bit numbering |
| `logo` | path | Company logo (PNG/JPG/SVG/GIF/WEBP), relative to the map file |
| `designation`, `litera`, `city` | string | Document designation, letter and city for the GOST template |
| `signatures` | object | `{developed, checked, tech_control, norm_control, approved}`: title block signatures |
| `approve`, `agree` | `{position, name}`, list | "Approved" (УТВЕРЖДАЮ) and "Agreed" (СОГЛАСОВАНО) blocks on the title page |
| `history` | list | `{version, date, author, github, changes: [text, ...]}`; `github` is the author's GitHub user name |

**Text** fields accept a string or an object with translations: `{en: "State", ru: "Состояние"}`.
Documents use the translation for the selected language and fall back to the other one.

See [templates.md](templates.md) for how the document details are laid out in PDF.

### `lint`

```yaml
lint:
  signal_name: snake_case     # snake_case | UPPER_SNAKE | camelCase | PascalCase | any
  frame_name: snake_case
  device_name: snake_case
  value_name: UPPER_SNAKE
  disable: [missing-description]   # turn rules off by code
```

### Bus (`buses[]`)

| Field | Description |
|---|---|
| `name` | Bus identifier (used for DBC and C file names) |
| `title` | Display name in documents and the editor tree ("Powertrain CAN"); without it, `missing-title` is reported |
| `description` | Description |
| `interface` | Interface (`can0`, `PCAN_USBBUS1`, …) |
| `bitrate` | Bit rate, bit/s |
| `protocol` | `canopen` (default): IDs are computed from the function code and `node_id`; `j1939`: from the PGN, priority and device address; `can`: IDs are set explicitly |
| `fd` | `true` for CAN FD (DLC up to 64) |
| `frames` | Broadcast frames with no owning device (`nmt`, `sync`, `time`) |
| `devices` | Devices |

### Device (`devices[]`)

| Field | Description |
|---|---|
| `name` | Identifier (`imd`) |
| `short` | Short label for tables (`BMS`) |
| `title` | Full name, shown in documents and the editor tree; without it, `missing-title` is reported |
| `node_id` | CANopen node address (1..127) |
| `address` | J1939 source address (0..253) |
| `description` | Description |
| `frames` | The device's frames: those it transmits, plus RX frames whose ID depends on its address (see [Sender and receivers](#sender-and-receivers)) |

### Frame (`frames[]`)

| Field | Description |
|---|---|
| `name` | Frame identifier (unique on the bus) |
| `title` | Name: the heading in documents and the label in the editor tree ("STATES") |
| `description` | Purpose of the frame |
| `type` | `nmt`, `sync`, `emcy`, `time`, `pdo_tx1..4`, `pdo_rx1..4`, `sdo_tx`, `sdo_rx`, `heartbeat`, `raw` (default) |
| `id` | Explicit CAN ID (required on `can` buses; on CANopen and J1939 it overrides the computed ID) |
| `pgn`, `priority`, `destination` | J1939: parameter group number, priority 0..7 (default 6), destination address for PDU1 (default 0xFF) |
| `receivers` | Names of the bus devices that receive the frame |
| `sender` | Name of the bus device that transmits the frame when it is not the owner: an RX frame (a node's PDO RX sent by the master) or a bus frame (NMT, SYNC). If omitted, the sender is outside the map |
| `extended` | 29-bit ID |
| `dlc` | Data length (default 8) |
| `direction` | `tx` / `rx` relative to the owning device. Defaults from the type: `pdo_tx*`, `sdo_tx`, `emcy`, `heartbeat` → `tx`; `pdo_rx*`, `sdo_rx`, `nmt` → `rx`; a frame without a CANopen type whose `sender` is another device → `rx`; otherwise `tx` |
| `cycle_ms` | Shorthand for `transmission: {mode: cyclic, cycle_ms: …}` |
| `transmission` | `{mode: cyclic \| event \| on_request, cycle_ms}` |
| `signals` | Signals |
| `sdo` | SDO exchanges (for `sdo_tx`/`sdo_rx`) |
| `comment` | Note |

CANopen ID computation:

| Type | ID |
|---|---|
| `nmt` | `0x000` |
| `sync` | `0x080` |
| `emcy` | `0x080 + node_id` |
| `time` | `0x100` |
| `pdo_tx1` / `pdo_rx1` | `0x180` / `0x200` `+ node_id` |
| `pdo_tx2` / `pdo_rx2` | `0x280` / `0x300` `+ node_id` |
| `pdo_tx3` / `pdo_rx3` | `0x380` / `0x400` `+ node_id` |
| `pdo_tx4` / `pdo_rx4` | `0x480` / `0x500` `+ node_id` |
| `sdo_tx` / `sdo_rx` | `0x580` / `0x600` `+ node_id` |
| `heartbeat` | `0x700 + node_id` |

### Signal (`signals[]`)

| Field | Description |
|---|---|
| `name` | Identifier (unique within the frame, together with flag names) |
| `title` | Human-readable name ("Battery voltage"); the editor tree shows it instead of the identifier |
| `description` | Description |
| `kind` | `enum`, `flag`, `bitfield`, `metric`, `raw`, `float`, `bytes`. If omitted: `flags` present → `bitfield`, `values` present → `enum`, `factor`/`offset`/`unit` present → `metric`, otherwise `raw` |
| `start_bit` + `bit_length` | Canonical position |
| `byte` [+ `bit`] [+ `byte_length` \| `bit_length`] | Shorthand position (see below) |
| `byte_order` | `little_endian` (default) or `big_endian` |
| `signed` | Signed value |
| `signed_code` | Signed number representation: `twos_complement` (default), `ones_complement` or `sign_magnitude`. This is a note for the documents only: generated code and DBC always use two's complement |
| `values` | Value table: `{0: NO_DATA, 1: {name: OK, description: "normal"}}` |
| `value_format` | `dec` \| `hex`: how values are shown in documents |
| `flags` | Bit field flags: `{bit, bit_length: 1, name, description, values}`; `bit` is the offset from the least significant bit of the field |
| `factor`, `offset`, `unit`, `min`, `max` | Physical conversion and range (in physical units) |
| `multiplexer` | `true` for the multiplexer selector signal |
| `mux` | Selector value (or list of values) for which the signal is present |
| `initial` | Default value in physical units (`…_INITIAL_RAW` in C, `GenSigStartValue` in DBC) |
| `invalid` | Raw value (or list) meaning "not available / invalid", e.g. `0xFF` |
| `comment` | Note |

If no length is given, a signal is 8 bits long; a `float` is 32 bits, and a `flag` or a
`byte` + `bit` position without `bit_length` is 1 bit.

#### Floating point

`kind: float` is IEEE 754, 32 bits (default) or 64 bits (`bit_length: 64`), in either byte order.
`factor` and `offset` are allowed. In C the field is a `float` or `double`; in DBC the signal is
marked as float.

```yaml
- {name: pack_voltage, byte: 0, kind: float, unit: V}
- {name: timestamp, byte: 0, kind: float, bit_length: 64, unit: s}
```

#### Shorthand position

| Shorthand | Equivalent |
|---|---|
| `byte: 2` | `start_bit: 16, bit_length: 8` |
| `byte: 1, byte_length: 2` | `start_bit: 8, bit_length: 16` |
| `byte: 1, bit: 3` | `start_bit: 11, bit_length: 1` |
| `byte: 2, bit: 4, bit_length: 4` | `start_bit: 20, bit_length: 4` |
| `byte: 1, byte_length: 2, byte_order: big_endian` | `start_bit: 16, bit_length: 16`, most significant byte in byte 1 |

`start_bit` cannot be combined with `byte`/`bit`, and `bit_length` cannot be combined with
`byte_length`.

#### Big-endian

For `big_endian` (Motorola) signals, `start_bit` is also the position of the least significant
bit. From there the value runs towards the most significant bits of that byte and continues from
bit 0 of the *previous* byte. With the `byte:` shorthand you give the first (most significant)
byte of the field, the way it is usually read in a table.

#### Multiplexing

```yaml
signals:
  - name: parse_type
    byte: 0
    bit: 0
    multiplexer: true
    values: {0: VOLTAGES, 1: TEMPERATURES}
  - {name: voltage_data,     byte: 1, byte_length: 7, kind: bytes, mux: 0}
  - {name: temperature_data, byte: 1, byte_length: 7, kind: bytes, mux: 1}
```

Signals with different `mux` values may occupy the same bits; this is not an overlap. A signal
without `mux` is present for every selector value.

### Protocols and CAN IDs

| `protocol` | How the ID is obtained |
|---|---|
| `canopen` | From the frame `type` and the device `node_id` (see the table above); `id` overrides it |
| `j1939` | 29 bits: `priority << 26 \| PGN << 8 \| address`. For PDU1 (PF < 240) the low byte of the PGN is replaced by `destination` |
| `can` | Explicit `id` only; `extended: true` for a 29-bit ID; `fd: true` on the bus for CAN FD |

J1939 example:

```yaml
buses:
  - name: j1939
    protocol: j1939
    bitrate: 250000
    devices:
      - name: engine
        address: 0x00
        frames:
          - name: eec1
            pgn: 0xF004          # PDU2 → ID 0x0CF00400
            priority: 3
            cycle_ms: 20
            receivers: [cluster]
            signals:
              - {name: engine_speed, byte: 3, byte_length: 2, factor: 0.125, unit: rpm, invalid: 0xFFFF}
      - name: cluster
        address: 0x17
      - name: diag
        address: 0xF9
        frames:
          - name: request
            pgn: 0xEA00          # PDU1: addressed
            destination: 0x00    # → ID 0x18EA00F9
            dlc: 3
```

### SDO (`sdo[]`)

For `sdo_rx`/`sdo_tx` frames you can describe expedited SDO exchanges instead of `signals`:

```yaml
- name: imd_sdo_request
  type: sdo_rx
  sdo:
    - name: set_alarm_resistance
      description: Set ALARM_RESISTANCE
      command: 0x2B          # CCS: write 2 bytes
      index: 0x4010
      subindex: 0x01
      value: {name: alarm_resistance, bit_length: 16, unit: kOhm}
```

mapcan builds the frame layout itself: byte 0 is the command, bytes 1–2 the index
(little-endian), byte 3 the subindex (the multiplexer selector when all exchanges share one
index), and bytes 4–7 the value.

## Sender and receivers

Every frame has exactly one sender. A frame transmitted by a device in the map is described
**at the sender**, and the receiving devices are listed in `receivers`. Receivers do not need
their own copies of the frame: mapcan derives what each device receives.

Describe an RX frame at a device in two cases only:

* the sender is not in the map (a PC, a tester, a third-party controller); leave `sender` out;
* the frame ID depends on the **receiver's** address: CANopen `pdo_rx*` and `sdo_rx`
  (`0x200 + node_id` of the node). If the master is also in the map, name it in `sender`.

```yaml
devices:
  - name: master
    node_id: 0x01
    frames:
      - name: master_status
        type: pdo_tx1          # sent by master, received by node
        receivers: [node]
  - name: node
    node_id: 0x05
    frames:
      - name: node_command
        type: pdo_rx1          # ID 0x205, from the node's node_id
        sender: master         # sent by the master
      - name: node_status
        type: pdo_tx1
        receivers: [master]
```

The owner of an RX frame is always one of its receivers, so it does not need to be listed in
`receivers`. From `sender` and `receivers` across all frames on the bus, mapcan builds:

* in the editor, the **Receives** and **Transmits frames of other devices** cards on each device
  page;
* in documents (PDF, HTML, Markdown), the same tables in each device section, and the sender of
  any frame it differs from the owner;
* in Excel, the "Communication matrix" sheet: frames as rows, devices as columns, TX/RX in the
  cells;
* in DBC, the message transmitter and the signal receivers.

## YAML anchors

Repeated value tables are easiest to share with anchors:

```yaml
values: &dc_states
  0: STATE_INIT
  1: STATE_PRECHARGE
...
values: *dc_states
```

## Validation rules

`mapcan rules` prints the full list. Severities: **error** (generation stops, exit code 1),
**warning** (exit code 1 only with `--strict`), **info** (shown with `--info`). Any rule can be
turned off with `--disable CODE` or `lint.disable`.

### Syntax and structure

| Code | Severity | What is checked |
|---|---|---|
| `yaml` | error | YAML syntax error, duplicate key |
| `schema` | error | Schema violation: wrong type, missing required field or invalid value |
| `number-comma` | error | Number written with a decimal comma (0,1 instead of 0.1) |
| `number-cyrillic-x` | error | Cyrillic “х” in a hexadecimal number |
| `number-quoted` | warning | Number written as a quoted string |

### Names

| Code | Severity | What is checked |
|---|---|---|
| `invalid-identifier` | error | Name cannot be used as a C/Python identifier |
| `reserved-identifier` | error | Name is a C/Python keyword or a member of the generated class |
| `name-collision` | error | Names collide in generated code (differ only in case, or clash with a _phys property) |
| `name-style` | warning | Name does not match the style rule (lint) |
| `name-inconsistent` | warning | The same value name is spelled differently |
| `duplicate-device-name` | error | Duplicate device name on the bus |
| `duplicate-frame-name` | error | Duplicate frame name on the bus |
| `duplicate-signal-name` | error | Duplicate signal/flag name in the frame |
| `duplicate-enum-name` | warning | Same name for different enum values |
| `duplicate-short` | warning | Duplicate device short label on the bus |

### Bus and addressing

| Code | Severity | What is checked |
|---|---|---|
| `bitrate-nonstandard` | warning | Non-standard bus bit rate |
| `bus-load` | warning | Estimated bus load from cyclic frames above 70% |
| `duplicate-node-id` | error | Duplicate node_id on the bus |
| `node-id-range` | error | CANopen node_id outside 1..127 |
| `frame-id-missing` | error | Cannot determine the frame's CAN ID |
| `duplicate-can-id` | error | Duplicate CAN ID on the bus |
| `can-id-range` | error | CAN ID does not fit in 11 bits (needs extended: true) |
| `dlc-range` | error | Invalid DLC |
| `canopen-dlc` | warning | DLC of a CANopen service frame does not match CiA 301 |
| `frame-type-protocol` | warning | CANopen frame type on a non-CANopen bus |
| `direction-mismatch` | warning | Direction conflicts with the CANopen frame type |

### SAE J1939

| Code | Severity | What is checked |
|---|---|---|
| `j1939-address` | error | J1939 address outside 0..253 or repeated on the bus |
| `j1939-pdu1-pgn` | warning | PDU1 PGN (PF < 240) with a non-zero low byte |
| `j1939-destination` | warning | destination set for a PDU2 PGN (PF ≥ 240) and unused |
| `j1939-field-protocol` | warning | pgn/priority/destination/address on a non-J1939 bus |

### Sender and receivers

| Code | Severity | What is checked |
|---|---|---|
| `unknown-receiver` | error | Frame receiver is not defined on the bus |
| `unknown-sender` | error | Frame sender is not defined on the bus |
| `sender-mismatch` | warning | sender conflicts with the frame direction or matches a receiver |
| `rx-duplicate` | error | RX frame duplicates another device's frame (describe the frame at its sender) |
| `rx-no-sender` | info | RX frame without a sender |
| `no-receivers` | info | Frame has no receivers on the bus |

### Transmission

| Code | Severity | What is checked |
|---|---|---|
| `cycle-missing` | error | cyclic mode without cycle_ms |
| `cycle-unexpected` | warning | cycle_ms set for a non-cyclic frame |

### Signal layout

| Code | Severity | What is checked |
|---|---|---|
| `signal-out-of-frame` | error | Signal extends beyond the DLC |
| `bit-overlap` | error | Overlapping signals (multiplexing-aware) |
| `float-length` | error | A float signal must be 32 or 64 bits |

### Values and conversion

| Code | Severity | What is checked |
|---|---|---|
| `enum-overflow` | error | Enum value does not fit in the field width |
| `metric-factor` | error | Zero factor |
| `metric-range` | warning | min/max outside the range the field can represent |
| `min-max` | error | min is greater than max |
| `initial-range` | warning | Default value outside the signal's range |
| `invalid-overflow` | error | invalid value does not fit in the signal width |
| `invalid-in-range` | warning | invalid value falls inside the min..max range |
| `signed-code` | info | Signed number code is not supported by code generation or is set on an unsigned signal |
| `missing-unit` | info | Physical quantity without a unit |

### Bit fields

| Code | Severity | What is checked |
|---|---|---|
| `flags-kind` | error | flags set on a signal that is not a bitfield |
| `flag-out-of-field` | error | Flag extends beyond the bit field |
| `flag-overlap` | error | Flags overlap inside the bit field |
| `flag-length` | warning | Flag signal longer than 1 bit |

### Multiplexing

| Code | Severity | What is checked |
|---|---|---|
| `mux-no-selector` | error | Multiplexed signal in a frame without a selector |
| `mux-multiple-selectors` | error | More than one selector in the frame |
| `mux-value-overflow` | error | mux value does not fit in the selector |
| `mux-value-unknown` | warning | mux value is not in the selector's value table |
| `mux-selector-muxed` | error | Selector is itself multiplexed |

### SDO

| Code | Severity | What is checked |
|---|---|---|
| `sdo-frame-type` | warning | sdo description on a frame that is not sdo_tx/sdo_rx |
| `sdo-duplicate` | error | Duplicate SDO exchange (command, index, subindex) |

### Document

| Code | Severity | What is checked |
|---|---|---|
| `logo-missing` | warning | Logo file not found |
| `logo-format` | error | Unsupported logo format |
| `history-version` | warning | Document version differs from the latest revision history entry |
| `missing-description` | info | Signal has no description |
| `missing-title` | info | Bus or device has no full name (`title`) |
| `empty-frame` | info | Frame has no signals |
