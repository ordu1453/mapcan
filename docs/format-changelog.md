# Format changelog

Changes of the map format by mapcan version. Up to 0.23 they keep `mapcan: 1`; 0.24 introduces
`mapcan: 2`, and version 1 stays readable: see
[Versioning and compatibility](format.md#versioning-and-compatibility). A map that uses a field
needs at least the version of mapcan that introduced it; former names stay readable.

## 0.24

- **Format version 2** (`mapcan: 2`): a signal has four encodings instead of eight (#140), `number`, `enum`,
  `bitfield` and `bytes`. Version 2 does not read the former values. A map of version 1 (`mapcan: 1`) is still
  read, converted as below, with the note `format-v1`; `mapcan migrate` (or the quick fix in VS Code) rewrites
  it and its included files in version 2, keeping comments and layout. New maps, device files and DBC imports
  are written in version 2. The schemas move to `…/schema/v2.json` and `…/schema/part-v2.json`; those of
  version 1 stay published at `…/v1.json` and `…/part-v1.json`.

  | Version 1 | Version 2 |
  |---|---|
  | `raw`, `scaled` | `number`; `factor` and `offset` make it a physical value |
  | `float` | `number` with `representation: float` (32 bits unless `bit_length: 64`) |
  | `flag` | `enum` with `bit_length: 1` (the length is no longer implied) |
  | `string` | `bytes` with `charset` (`ascii` was the default; now a byte array has no `charset`) |
  | SDO value `raw`, `scaled` | `number` |

- `representation` has the value `float` (IEEE 754), and applies to `number` only. `invalid_raw` and `source` do
  not apply to a float, nor `terminator` to bytes without `charset` (`encoding-field`). The rule `flag-length` is
  gone.
- An `enum` has unsigned values only and no `invalid_raw`: a value that means "no data" is an entry of its table.
  A version 1 enum with `representation` or `invalid_raw` is reported (`encoding-field`) and rewritten by hand.
  DBC import writes a signed signal with a value table as a `number`, with a warning that the table is not
  imported.
- Generated C and Python have the physical-value helpers (`_to_phys`, `_from_phys`, `_phys`) of a signal only when
  its `factor` or `offset` differs from 1 and 0: a former `scaled` signal without them has none, and documents
  show its unit without "1 … /bit". The `min`/`max` range checks (`range-overflow`, `min-max`) cover every integer
  `number`, not only scaled ones.
- The layout fingerprint (`layout_crc32`, `<BUS>_MAP_LAYOUT_CRC32`) is computed from text `v2`, which names the new
  encodings: it changes for every map, so firmware that sends it has to be rebuilt.
- DBC import writes `number` (with `representation: float` for a float signal) and `enum`; a 1-bit signal without
  a value table is a `number`.

## 0.23

- With a `history`, the document's version and date are those of its latest entry:
  `document.version` and `document.date` are no longer written there. Written anyway and equal to
  the entry, they are the warning `version-redundant`, and `mapcan migrate` (or the quick fix in
  VS Code) removes them; written and different, `history-version` as before. A map without a
  history keeps them. New maps, Add to history and Release version write the entry only (and
  remove the document's own copies); documents and generated code read the version as before.
- New frame field `inhibit_ms`: the minimum time between two transmissions (CANopen inhibit time,
  DBC `GenMsgDelayTime`). It goes to DBC (whole milliseconds, rounded up) and back, to the TPDO's
  inhibit time in EDS, to generated code as `<FRAME>_INHIBIT_US` (C) and `<FRAME>_INHIBIT_MS`
  (Python), and to documents next to the transmission. New rules: `inhibit-long` (longer than
  `cycle_ms`) and `inhibit-cyclic` (on a frame sent only cyclically). The `bus-load` estimate counts
  frames sent on an event at their minimum interval.
- A frame may have `cycle_ms` together with `trigger: event`: it is sent every period and at once
  on an event. Documents read "every 100 ms and on event"; DBC export writes `GenMsgSendType =
  CyclicAndSpontaneous`, and DBC import reads `CyclicAndSpontaneous`, `CyclicIfActive` and the like
  as the period with `trigger: event` instead of dropping the event part. `cycle-unexpected` now
  reports `cycle_ms` with `trigger: on_request` only.
- The frame field `direction` is deprecated: the direction follows from the CANopen function and
  `sender`, and a frame from outside the map is written in the frames of its bus with the
  receiving devices in `receivers` (the bus's `frames` were for NMT, SYNC and TIME only). Maps with
  `direction` still read the same, with the warning `direction-deprecated`; `mapcan migrate` (and
  the quick fix in VS Code) removes it and moves such frames. The editors have no Direction field:
  the sender says who sends a frame. It will be removed from the format in version 2.
- Documents name the section of the frames of a bus "Outside the map" (formerly "Broadcast").
- Generated C: a frame or device whose name is also on another bus is named with its bus
  (`<BUS>_<FRAME>_ID`, `<bus>_<frame>_pack()`, `<BUS>_<DEVICE>_NODE_ID`), so the headers of all buses
  build in one firmware; unique names do not change. The map constants are `<BUS>_MAP_VERSION_*` and
  `<BUS>_MAP_LAYOUT_CRC32`; `MAP_VERSION_*` and `MAP_LAYOUT_CRC32` remain as deprecated aliases, left
  out when `MAPCAN_NO_DEPRECATED` is defined.
- Generated code: a value out of a field's range is saturated by `<frame>_pack()` in C and makes
  `pack()` in Python raise `ValueError`, instead of being cut to its low bits; the Python
  `<signal>_phys` setter rounds half away from zero and saturates, as `_from_phys()` in C does.
- Generated C: `<frame>_init()` sets every signal to its initial value; `<frame>_unpack()` of a
  multiplexed frame gives the signals of another selector value their initial values.
- Generated Python: fields of signals with named values hold members of their `IntEnum` (a raw
  value without a name stays an `int`).
- Generated C: `float`/`double` are converted to raw bits with `memcpy` (from `string.h`) instead of
  a union, so the headers are well-defined in C++ too; the code is built as C99 and C++17 in the
  tests. The bit helpers carry their revision in `MAPCAN_BITS_HELPERS`: headers generated by mapcan
  versions with different helpers stop the build with an `#error`.
- Generated C: each signal is read and written with the shifts and masks of the bytes it touches,
  in an unsigned type of its width, instead of a loop over bits in 64-bit arithmetic (about 40 %
  less code on Cortex-M). `mapcan gen c --phys-type double` makes the physical values of all scaled
  signals `double` (by default `float`, `double` only for fields longer than 24 bits).
- Generated code: `<frame>_<signal>_in_range(raw)` for signals with `min`/`max` (C and Python),
  `<FRAME>_ON_EVENT` for frames sent on an event, and in C the constant `<FRAME>_INITIAL` and
  `<frame>_<signal>_is_active(&msg)` for multiplexed signals.
- Generated C: `--phys-type int` computes physical values in integers (units of the factor's decimals)
  for MCUs without an FPU. The code is checked with cppcheck and MISRA C:2012 in CI (the deviations
  are listed in docs/cli.md), and its Cortex-M code size within a budget; comparisons in expressions are
  in parentheses, the selector is compared with literals of its signedness, and the helpers of the
  signed representations work in explicit steps. The bit helpers index bytes with `uint16_t`: a
  transport-protocol PGN longer than 256 bytes was read at wrong offsets.
- Generated C: `--target zephyr` adds an adapter to the Zephyr RTOS CAN API (`<frame>_to_can_frame()`,
  `<frame>_from_can_frame()`, and for a device its `struct can_filter`s, dispatch, sending and a TX
  schedule on `k_work_delayable`); the repository is a Zephyr module with `mapcan_generate()`, which
  generates the code from the map at build time (docs/zephyr.md). The code of a device has `<device>_tx_t`
  with `<device>_tx_init()` and `<device>_tx_pack()`.
- Generated C per device: `mapcan gen c --device <name>` (or `--devices`) writes the frames a device
  sends and receives, its TX schedule, the frames it receives with acceptance filters, and
  `<device>_rx_dispatch()`, which unpacks a received frame into the device's RX state and notes when
  it came, with `<device>_rx_timed_out()` for the timeout supervision. `mapcan gen py --device` writes
  the frames of one device as a Python module for test benches.

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
- `mapcan fmt [--check]` writes the keys of every node in one order (see
  [Canonical layout](format.md#canonical-layout)); the map itself does not change.
- `mapcan migrate` rewrites former field names; the rule `deprecated-key` reports them.
