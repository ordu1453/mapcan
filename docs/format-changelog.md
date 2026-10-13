# Format changelog

Changes of the map format by mapcan version. All of them keep `mapcan: 1`: see
[Versioning and compatibility](format.md#versioning-and-compatibility). A map that uses a field
needs at least the version of mapcan that introduced it; former names stay readable.

## 0.21

- The frame field `dlc` is now `length` (data length in bytes). On CAN FD and with the J1939
  transport protocol the length is not a DLC code; the code follows from it. `dlc` is still read
  with a `deprecated-key` warning. Generated code: `<FRAME>_LENGTH` (C) and `LENGTH` (Python);
  `<FRAME>_DLC` / `DLC` remain as deprecated aliases.
- The signal fields `signed` and `signed_code` are one field, `representation`: `unsigned`
  (default), `twos_complement`, `ones_complement` or `sign_magnitude`; `signed: true` alone is
  `twos_complement`. An SDO value's `signed: true` is `representation: twos_complement`.
- The frame field `type` is `canopen`, the frame's CANopen function. `type: raw` is written as no
  `canopen` at all: a frame without a function has an explicit ID.
- The signal field `invalid` is `invalid_raw`: raw-valued keys end in `_raw`. It also accepts
  ranges (`0xFF00..0xFFFF`) and values by meaning (`{not_available: …, error: …}`), with
  `…_is_not_available()` / `…_is_error()` in the generated C and Python code.
- The bus field `interface` is `connector`: the connector or harness of the bus, shown in documents.
  The CAN adapter and channel (`can0`, `PCAN_USBBUS1`) depend on the workstation and are not part of
  the map.
- The print details of the title page (`logo`, `designation`, `litera`, `city`, `signatures`,
  `approve`, `agree`) move from `document` into `document.print`. The former place is still read
  with `deprecated-key`; `mapcan migrate` moves them, keeping comments. Templates get them where
  they were (`doc.designation`…).
- An included file starts with `mapcan: 1` and `part_of: <map>`; the loader checks that it is
  included by that map (`include`), and warns about files without them (`include-part-of`).
  Its JSON Schema is `schema/mapcan-part.schema.json` (`mapcan schema --part`).
- Buses have `sample_point`, and CAN FD buses `data_bitrate` and `data_sample_point`. The
  `bus-load` estimate covers CAN FD buses (the data phase of BRS frames at `data_bitrate`).
- Frames have `timeout_ms`, the receive timeout (`<FRAME>_TIMEOUT_MS` in code; rule `timeout-short`).
- Signals have `encoding: string` with `charset` and `terminator` (text such as a VIN or a
  software identification).
- `document.version` is `MAJOR.MINOR[.PATCH]`; another form is the warning `version-format`.
- Signals have `source`: `map_version.major`, `.minor`, `.patch` or `layout_crc32`, so a device
  sends the map it was built from (rule `source-value`). Generated code has `MAP_VERSION_*` and
  `MAP_LAYOUT_CRC32`.
- `mapcan migrate` rewrites former field names; the rule `deprecated-key` reports them.
