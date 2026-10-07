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
| `title` | Display name in documents ("Powertrain CAN") |
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
| `title` | Full name |
| `node_id` | CANopen node address (1..127) |
| `address` | J1939 source address (0..253) |
| `description` | Description |
| `frames` | The device's frames: those it transmits, plus RX frames whose ID depends on its address (see [Sender and receivers](#sender-and-receivers)) |

### Frame (`frames[]`)

| Field | Description |
|---|---|
| `name` | Frame identifier (unique on the bus) |
| `title` | Short heading ("STATES") |
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

| Code | Severity | What is checked |
|---|---|---|
| `yaml` | error | YAML syntax, duplicate keys |
| `schema` | error | Structure: types, required fields, unknown fields, allowed values |
| `number-comma` | error | `0,1` instead of `0.1` |
| `number-cyrillic-x` | error | Cyrillic "х" in `0х196` |
| `number-quoted` | warning | Number in quotes (`"0x196"`) |
| `invalid-identifier` | error | Name cannot be used in code (`NO DATA`) |
| `name-style` | warning | Name does not follow the `lint` style |
| `name-inconsistent` | warning | The same value name is spelled differently (`NO DATA` / `NO_DATA`) |
| `duplicate-signal-name` | error | Repeated signal or flag name in a frame |
| `duplicate-enum-name` | warning | The same name for different enum values |
| `duplicate-can-id` | error | Repeated CAN ID on a bus |
| `duplicate-frame-name`, `duplicate-device-name`, `duplicate-node-id` | error | Duplicates on a bus |
| `node-id-range`, `can-id-range`, `dlc-range` | error | Values out of range |
| `frame-id-missing` | error | The ID cannot be computed (no `node_id` or `id`) |
| `signal-out-of-frame` | error | Signal extends beyond the DLC |
| `bit-overlap` | error | Overlapping signals (taking `mux` into account) |
| `enum-overflow` | error | Value does not fit in the field width |
| `flag-out-of-field`, `flag-overlap`, `flags-kind`, `flag-length` | error/warning | Bit fields |
| `metric-factor`, `metric-range`, `min-max` | error/warning | Physical conversion |
| `mux-no-selector`, `mux-multiple-selectors`, `mux-value-overflow`, `mux-value-unknown`, `mux-selector-muxed` | error/warning | Multiplexing |
| `cycle-missing`, `cycle-unexpected` | error/warning | Transmission mode |
| `direction-mismatch`, `frame-type-protocol` | warning | Consistency of the frame type |
| `sdo-frame-type`, `sdo-duplicate` | warning/error | SDO descriptions |
| `j1939-address`, `j1939-pdu1-pgn`, `j1939-destination`, `j1939-field-protocol` | error/warning | J1939 address out of range or repeated, PDU1 PGN with a non-zero low byte, destination on a PDU2 PGN, J1939 fields on another bus |
| `unknown-receiver`, `unknown-sender` | error | Frame receiver or sender is not defined on the bus |
| `sender-mismatch` | warning | `sender` on a TX frame, `sender` equal to the owner of an RX frame, or the sender listed among the receivers |
| `rx-duplicate` | error | RX frame duplicates the sender's frame (same CAN ID): describe the frame once at the sender and list the receiver in `receivers` |
| `rx-no-sender` | info | RX frame with no CANopen type and no `sender`: if the sender is in the map, move the frame to it |
| `float-length` | error | Float signal is neither 32 nor 64 bits |
| `initial-range`, `invalid-overflow` | warning/error | Default value out of range; `invalid` does not fit in the field |
| `signed-code` | info | Signed number code is not supported by code generation, or is set on an unsigned signal |
| `logo-missing`, `logo-format` | warning/error | Logo file not found / unsupported format |
| `missing-description`, `empty-frame` | info | Completeness of the description |
