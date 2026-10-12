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
| Units in keys | A time carries its unit in the key (`cycle_ms`). Other quantities have one fixed unit stated in the field's description: bit rates in bit/s (`bitrate`), lengths in bytes (`length`, `byte_length`) or bits (`bit_length`) |
| Raw and physical values | A key holding a raw (unscaled) value ends in `_raw`; every other value of a signal is physical: `physical = raw * factor + offset` |

The numbering is stated explicitly by `document.bit_numbering: lsb0` and printed in every
document.

## File structure

```yaml
mapcan: 1                 # format version (required)
document: {...}           # metadata and revision history
include: [common.yaml]    # included files (optional, see below)
lint: {...}               # style rules (optional)
value_tables: {...}       # named value tables (optional, see below)
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
| `language` | ISO 639-1 code | Default document language (required): `ru`, `en`, `de`…; `--lang` overrides it at export. Document labels (table headings and so on) exist in Russian and English; other languages get the English ones, and units their international symbols |
| `bit_numbering` | `lsb0` | Explicit statement of the bit numbering |
| `logo` | path | Company logo (PNG/JPG/SVG/GIF/WEBP), relative to the map file |
| `designation`, `litera`, `city` | string | Document designation, letter and city for the GOST template |
| `signatures` | object | `{developed, checked, tech_control, norm_control, approved}`: title block signatures |
| `approve`, `agree` | `{position, name}`, list | "Approved" (УТВЕРЖДАЮ) and "Agreed" (СОГЛАСОВАНО) blocks on the title page |
| `history` | list | `{version, date, author, github, changes: [text, ...]}`; `github` is the author's GitHub user name |

**Text** fields accept a string or an object with translations: `{en: "State", ru: "Состояние"}`.
Keys are ISO 639-1 language codes (`de`, `fr`…). Documents use the translation for the selected language; without it, the document language (`document.language`), then English, then any other.

### Text fields

Buses, devices, frames and signals use the same keys for their texts, with the same meaning:

| Key | Meaning | Where it is shown |
|---|---|---|
| `name` | Identifier | Generated code, DBC, references (`sender`, `receivers`) |
| `title` | Name for people, in normal case ("States", "Battery voltage") | Editor tree, headings in documents |
| `description` | What it is and what for | Documents, comments in generated code, DBC |
| `comment` | A note or caveat (frames and signals) | Documents ("Note:"), DBC after the description |
| `short` | Device abbreviation ("BMS") | Document tables, editor tree before the name |

Without `description`, documents and code comments use `title`.

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
| `title` | Name for people ("Powertrain CAN"); without it, `missing-title` is reported |
| `description` | What the bus is for |
| `interface` | Interface (`can0`, `PCAN_USBBUS1`, …) |
| `bitrate` | Bit rate, bit/s |
| `protocol` | Required. `canopen`: IDs are computed from the function code and `node_id`; `j1939`: from the PGN, priority and device address; `can`: IDs are set explicitly |
| `fd` | `true` for CAN FD (DLC up to 64) |
| `brs` | CAN FD: bit rate switch (BRS) of the frames by default, `true` if omitted. Set `false` when the nodes or the wiring cannot handle the data phase bit rate |
| `frames` | Broadcast frames with no owning device (`nmt`, `sync`, `time`) |
| `devices` | Devices |

### Device (`devices[]`)

| Field | Description |
|---|---|
| `name` | Identifier (`imd`) |
| `short` | Abbreviation (`BMS`) |
| `title` | Full name ("Battery management system"); without it, `missing-title` is reported |
| `node_id` | CANopen node address (1..127) |
| `address` | J1939 source address (0..253) |
| `description` | What the device is |
| `frames` | The device's frames: those it transmits, plus RX frames whose ID depends on its address (see [Sender and receivers](#sender-and-receivers)) |

### Frame (`frames[]`)

| Field | Description |
|---|---|
| `name` | Frame identifier (unique on the bus) |
| `title` | Name for people ("States") |
| `description` | What the frame carries |
| `type` | `nmt`, `sync`, `emcy`, `time`, `pdo_tx1..4`, `pdo_rx1..4`, `sdo_tx`, `sdo_rx`, `heartbeat`, `raw` (default) |
| `id` | Explicit CAN ID (required on `can` buses; on CANopen and J1939 it overrides the computed ID) |
| `pgn`, `priority`, `destination` | J1939: parameter group number, priority 0..7 (default 6), destination address for PDU1 (default 0xFF) |
| `receivers` | Names of the bus devices that receive the frame |
| `sender` | Name of the bus device that transmits the frame when it is not the owner: an RX frame (a node's PDO RX sent by the master) or a bus frame (NMT, SYNC). If omitted, the sender is outside the map |
| `extended` | 29-bit ID |
| `brs` | CAN FD: bit rate switch (BRS), the data field is sent at the data phase bit rate. If omitted, the bus `brs` applies. Written to DBC as the `CANFD_BRS` attribute |
| `length` | Data length, bytes (formerly `dlc`: the DLC on the bus is the code of this length). Required, except for CANopen service frames, which take the CiA 301 length of the type when it is omitted: NMT 2, SYNC 0, TIME 6, Heartbeat 1, SDO 8. On a J1939 bus up to 1785 bytes (see [Transport protocol](#transport-protocol)) |
| `direction` | `tx` / `rx` relative to the owning device. Defaults from the type: `pdo_tx*`, `sdo_tx`, `emcy`, `heartbeat` → `tx`; `pdo_rx*`, `sdo_rx`, `nmt` → `rx`; a frame without a CANopen type whose `sender` is another device → `rx`; otherwise `tx` |
| `cycle_ms` | Cyclic transmission period, ms |
| `trigger` | Non-cyclic transmission: `event` (on event) or `on_request`. Cannot be combined with `cycle_ms` |
| `signals` | Signals |
| `sdo` | SDO exchanges (for `sdo_tx`/`sdo_rx`) |
| `comment` | A note or caveat (see [Text fields](#text-fields)) |

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
| `title` | Name for people ("Battery voltage") |
| `description` | What the signal means |
| `encoding` | Required: `enum`, `flag`, `bitfield`, `scaled`, `raw`, `float`, `bytes` |
| `start_bit` + `bit_length` | Canonical position |
| `byte` [+ `bit`] + `byte_length` \| `bit_length` | Shorthand position (see below) |
| `byte_order` | `little_endian` (default) or `big_endian` |
| `signed` | Signed value |
| `signed_code` | Signed number representation: `twos_complement` (default), `ones_complement` or `sign_magnitude`. Generated C and Python code packs and unpacks the value in this code, and the value range is symmetric (−127…127 for 8 bits). DBC stores two's complement only, so the export warns about such signals |
| `values` | Value table: `{0: NO_DATA, 1: {name: OK, description: "normal"}}` |
| `value_format` | `dec` \| `hex`: how values are shown in documents |
| `flags` | Bit field flags: `{bit, bit_length: 1, name, description, values}`; `bit` is the offset from the least significant bit of the field |
| `factor`, `offset`, `unit`, `min`, `max` | Physical conversion and range (in physical units) |
| `multiplexer` | `true` for the multiplexer selector signal |
| `mux` | Selector value (or list of values) for which the signal is present |
| `initial` | Default value in physical units (`…_INITIAL_RAW` in C, `GenSigStartValue` in DBC) |
| `invalid` | Raw value (or list) meaning "not available / invalid", e.g. `0xFF` |
| `index`, `subindex` | CANopen dictionary object mapped into the PDO (see [Object dictionary and EDS](#object-dictionary-and-eds)) |
| `spn` | J1939 suspect parameter number (SAE J1939-71), 0..524287. Shown in documents, written to DBC as the `SPN` signal attribute and to code as `<FRAME>_<SIGNAL>_SPN` |
| `comment` | A note or caveat (see [Text fields](#text-fields)) |

#### Encodings

`encoding` says how the bits are read, and which value fields apply:

| `encoding` | Meaning | Value fields |
|---|---|---|
| `raw` | Integer as is | `signed`, `unit`, `min`, `max`, `invalid`, `initial` |
| `scaled` | Scaled physical value: `raw * factor + offset` | `signed`, `factor`, `offset`, `unit`, `min`, `max`, `invalid`, `initial` |
| `enum` | Value from the `values` table | `values`, `value_format`, `signed`, `invalid`, `initial` |
| `flag` | One yes/no bit | `values`, `initial` |
| `bitfield` | Set of flags | `flags` |
| `float` | IEEE 754 | `factor`, `offset`, `unit`, `min`, `max`, `initial` |
| `bytes` | Byte array | — |

A field that does not apply is an error (`encoding-field`). `signed_code` follows `signed`.

The length (`bit_length` or `byte_length`) is required. Only two encodings set it
themselves: a `flag` is 1 bit, and a `float` is 32 bits unless `bit_length: 64` is given.

#### Floating point

`encoding: float` is IEEE 754, 32 bits (default) or 64 bits (`bit_length: 64`), in either byte order.
`factor` and `offset` are allowed. In C the field is a `float` or `double`; in DBC the signal is
marked as float.

```yaml
- {name: pack_voltage, byte: 0, encoding: float, unit: V}
- {name: timestamp, byte: 0, encoding: float, bit_length: 64, unit: s}
```

#### Shorthand position

| Shorthand | Equivalent |
|---|---|
| `byte: 2, byte_length: 1` | `start_bit: 16, bit_length: 8` |
| `byte: 1, byte_length: 2` | `start_bit: 8, bit_length: 16` |
| `byte: 1, bit: 3, bit_length: 1` | `start_bit: 11, bit_length: 1` |
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
    encoding: enum
    byte: 0
    bit: 0
    bit_length: 1
    multiplexer: true
    values: {0: VOLTAGES, 1: TEMPERATURES}
  - {name: voltage_data,     byte: 1, byte_length: 7, encoding: bytes, mux: 0}
  - {name: temperature_data, byte: 1, byte_length: 7, encoding: bytes, mux: 1}
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
            length: 8
            cycle_ms: 20
            receivers: [cluster]
            signals:
              - {name: engine_speed, encoding: scaled, byte: 3, byte_length: 2, factor: 0.125, unit: rpm, invalid: 0xFFFF}
      - name: cluster
        address: 0x17
      - name: diag
        address: 0xF9
        frames:
          - name: request
            pgn: 0xEA00          # PDU1: addressed
            destination: 0x00    # → ID 0x18EA00F9
            length: 3
```

#### Transport protocol

A PGN longer than one frame (8 bytes, or 64 on CAN FD) is sent with the J1939-21 transport
protocol: give its full length in `length`, up to 1785 bytes. mapcan reports it as a note
(`j1939-tp`): BAM when it goes to everyone (a PDU2 PGN, or `destination` 0xFF), RTS/CTS when it
goes to one device. The bus load counts its TP.DT packets and TP.CM frames. Generated code packs
and unpacks the whole payload; splitting it into packets is the job of the J1939 stack.

```yaml
- name: soft
  pgn: 0xFEDA            # Software identification
  length: 20                # 3 TP.DT packets + BAM
  trigger: on_request
  signals:
    - {name: software_id, encoding: bytes, spn: 234, byte: 0, byte_length: 20}
```

A signal longer than 64 bits can only be a byte array (`encoding: bytes`, little-endian, starting
at a byte boundary).

### Object dictionary and EDS

A signal of a device's PDO can name the dictionary object it carries: `index` and, for an entry of
a record, `subindex` (0 by default). Signals sharing an `index` with different subindices form a
record. Documents show the object (`OD 0x6041:00`), and `mapcan export eds` writes an EDS file
(CiA 306) per device of a CANopen bus: the mandatory objects (1000, 1001, 1018), the producer
heartbeat time (1017, from a heartbeat frame's `cycle_ms`), the communication and mapping
parameters of each PDO with mapped signals (1400/1600 for RPDOs, 1800/1A00 for TPDOs; COB-ID
`$NODEID+base`, event timer from `cycle_ms`) and the objects themselves. Gaps between mapped
signals are filled with dummy objects.

```yaml
- name: drive_status
  type: pdo_tx1
  length: 6
  cycle_ms: 10
  signals:
    - {name: statusword, encoding: raw, index: 0x6041, byte: 0, byte_length: 2}
    - {name: actual_velocity, encoding: scaled, index: 0x606C, byte: 2, byte_length: 4, signed: true, unit: rpm}
```

The object's data type is the smallest standard type that holds the signal (`UNSIGNED16`,
`INTEGER32`, `REAL32`, `BOOLEAN` for one bit…). Objects of a TPDO are read-only (`ro`), of an
RPDO writable (`rww`). See [examples/canopen-node.yaml](../examples/canopen-node.yaml).

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
      value: {name: alarm_resistance, encoding: scaled, bit_length: 16, unit: kOhm}
```

The value's `encoding` (`enum`, `scaled` or `raw`) and `bit_length` (8, 16, 24 or 32) are required.

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
        length: 8
        receivers: [node]
  - name: node
    node_id: 0x05
    frames:
      - name: node_command
        type: pdo_rx1          # ID 0x205, from the node's node_id
        length: 8
        sender: master         # sent by the master
      - name: node_status
        type: pdo_tx1
        length: 8
        receivers: [master]
```

On a J1939 bus the computed ID of an RX frame takes its source address from `sender`, not from
the owner: the owner is the receiver (and, for a PDU1 PGN, may be the `destination`). An RX frame
without `sender` and without `id` has no known source address and is reported as
`frame-id-missing`: name the sending device in `sender` (or move the frame to it) or give `id`.

The owner of an RX frame is always one of its receivers, so it does not need to be listed in
`receivers`. From `sender` and `receivers` across all frames on the bus, mapcan builds:

* in the editor, the **Receives** and **Transmits frames of other devices** cards on each device
  page;
* in documents (PDF, HTML, Markdown), the same tables in each device section, and the sender of
  any frame it differs from the owner;
* in Excel, the "Communication matrix" sheet: frames as rows, devices as columns, TX/RX in the
  cells;
* in DBC, the message transmitter and the signal receivers.

## Named value tables

A value table used by several signals is described once in `value_tables` and referred to by
name. The same works for flags and SDO values:

```yaml
value_tables:
  dc_states: {0: STATE_INIT, 1: STATE_PRECHARGE, 2: STATE_RUN}
...
- {name: dc_state, encoding: enum, byte: 0, byte_length: 1, values: dc_states}
```

An unknown name is an error (`value-table`). The editors show such a signal's values as a
reference; the table itself is edited in `value_tables`.

## Included files

`include` lists files (paths relative to the map file) whose contents are added to the map,
for example the buses and devices shared by several machines:

```yaml
# vehicle.yaml
mapcan: 1
include: [powertrain.yaml]
document: {title: Vehicle, language: en}
buses:
  - name: can1
    protocol: canopen
    devices: [...]
```

```yaml
# powertrain.yaml
value_tables: {...}
buses:
  - name: can1          # already described: devices and frames are added to it
    devices: [...]
  - name: can2          # new bus
    protocol: j1939
    devices: [...]
```

See [examples/tractor/](../examples/tractor/tractor.yaml) for a complete map in two files.

An included file may contain only `buses` and `value_tables`. A bus that the main file (or an
earlier included file) already describes can only get more `devices` and `frames`; its other
fields, and a value table name used twice, are errors (`include`). Included files are not
nested.

Validation, documents and generated code use the whole map. Messages about an included file
point into that file on the command line; in the editors they are shown on the `include` line
of the main file, with the file and line in the text. The editors' trees show the included buses,
devices and frames in their places, marked with the file name; their forms are read-only (the
editors change the main file only), and clicking such a node in VS Code opens it in its file.
Included devices can be chosen as senders and receivers of the main file's frames.

## Versioning and compatibility

`mapcan: 1` is the version of the format, not of the program. What it promises:

- **Additions keep the version.** New optional fields, new values of an enumeration and new rules
  keep `mapcan: 1`. Every map that was valid stays valid; a map that uses a new field needs a mapcan
  that knows it (see [the format changelog](format-changelog.md)).
- **Renames keep the version too.** When a field gets a clearer name (or several fields become one),
  the former spelling stays accepted for the whole of version 1. It is read as the current one with
  the warning `deprecated-key`; messages about the field still point at what is written. The
  editors show and write the current name: editing such a field renames it in place, keeping its
  position and comment. A map that has both names is an error.
- **`mapcan migrate FILE…`** rewrites the former names in the map and its included files, keeping
  comments and layout; `mapcan migrate --check` exits 1 if anything is left (for CI). In VS Code the
  quick fix of `deprecated-key` does the same.
- **Removing a field or changing its meaning** would need `mapcan: 2`, read side by side with
  version 1 and converted by `mapcan migrate`. None is planned.
- **Rule codes do not change**, so `lint.disable` and `--disable` keep working: `dlc-range`, for
  example, keeps its code after `dlc` became `length`.

| Former name | Current name | Since |
|---|---|---|
| frame `dlc` | `length` | 0.21 |

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
| `deprecated-key` | warning | A field under its former name: still read, `mapcan migrate` rewrites it (an error when the current name is set too). See [Versioning and compatibility](#versioning-and-compatibility) |
| `include` | error | Included file not found, or it has keys that cannot be included |
| `value-table` | error | `values` names a table that is not in `value_tables` |

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
| `brs-without-fd` | warning | brs is set on a bus that is not CAN FD and is not used |
| `duplicate-node-id` | error | Duplicate node_id on the bus |
| `node-id-range` | error | CANopen node_id outside 1..127 |
| `frame-id-missing` | error | Cannot determine the frame's CAN ID |
| `duplicate-can-id` | error | Duplicate CAN ID on the bus |
| `can-id-range` | error | CAN ID does not fit in 11 bits (needs extended: true) |
| `dlc-range` | error | Frame length that no DLC can encode: above 8 on a classic CAN bus, not 0..8, 12, 16, 20, 24, 32, 48, 64 on CAN FD |
| `dlc-missing` | error | Frame has no `length` (only CANopen service frames may omit it) |
| `canopen-dlc` | warning | Length of a CANopen service frame does not match CiA 301 |
| `frame-type-protocol` | warning | CANopen frame type on a non-CANopen bus |
| `direction-mismatch` | warning | Direction conflicts with the CANopen frame type |

### SAE J1939

| Code | Severity | What is checked |
|---|---|---|
| `j1939-address` | error | J1939 address outside 0..253 or repeated on the bus |
| `j1939-pdu1-pgn` | warning | PDU1 PGN (PF < 240) with a non-zero low byte |
| `j1939-destination` | warning | destination set for a PDU2 PGN (PF ≥ 240) and unused |
| `j1939-field-protocol` | warning | pgn/priority/destination/address/spn on a non-J1939 bus |
| `j1939-spn-duplicate` | warning | The same SPN on several signals of the bus |
| `j1939-tp` | info | A PGN longer than 8 bytes is sent with the J1939-21 transport protocol |
| `canopen-od` | warning | Dictionary object on a signal outside a device's PDO, outside 0x2000..0x9FFF, or big-endian |
| `od-duplicate` | warning | The same dictionary object on several signals of a device |

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
| `cycle-unexpected` | error | cycle_ms set together with trigger |

### Signal layout

| Code | Severity | What is checked |
|---|---|---|
| `signal-out-of-frame` | error | Signal extends beyond the frame length |
| `bit-overlap` | error | Overlapping signals (multiplexing-aware) |
| `float-length` | error | A float signal must be 32 or 64 bits |
| `signal-length` | error | A signal longer than 64 bits that is not an aligned byte array |

### Values and conversion

| Code | Severity | What is checked |
|---|---|---|
| `enum-overflow` | error | Enum value does not fit in the field width |
| `zero-factor` | error | Zero factor |
| `range-overflow` | warning | min/max outside the range the field can represent |
| `min-max` | error | min is greater than max |
| `initial-range` | warning | Default value outside the signal's range |
| `invalid-overflow` | error | invalid value does not fit in the signal width |
| `invalid-in-range` | warning | invalid value falls inside the min..max range |
| `signed-code` | info | Signed number code cannot be expressed in DBC, or is set on an unsigned signal |
| `missing-unit` | info | Physical quantity without a unit |

### Bit fields

| Code | Severity | What is checked |
|---|---|---|
| `encoding-field` | error | A field is set that does not apply to the signal's encoding (see [Encodings](#encodings)) |
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
