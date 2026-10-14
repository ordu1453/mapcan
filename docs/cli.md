# Command line

Every output of mapcan is one command away, for a terminal or a CI pipeline. Export and generation
validate the map first and stop on errors (`--force` generates anyway).

```text
mapcan app         [FILE|DIR] [--browser] [--readonly]
mapcan serve       [FILE|DIR] [--host 127.0.0.1] [--port 8765] [--readonly] [--no-browser] [--token T | --no-auth]
mapcan validate    FILE [--strict] [--info] [--format json] [--disable CODE]
mapcan export xlsx FILE [-o OUT] [--style style.yaml] [--lang en]
mapcan export pdf  FILE [-o OUT] [--template mapcan|gost-2.105|my.typ] [--font-path DIR] [--lang en]
mapcan export md   FILE [-o OUT] [--template my.md.j2] [--lang en]
mapcan export html FILE [-o OUT] [--template my.html.j2] [--lang en]
mapcan export dbc  FILE [-o DIR|file.dbc] [--bus NAME]
mapcan export eds  FILE [-o DIR] [--bus NAME]
mapcan gen c       FILE [-o DIR] [--prefix my_] [--bus NAME]
mapcan gen py      FILE [-o DIR] [--bus NAME]
mapcan build       FILE [-o DIR] [--formats xlsx,pdf,md,html,dbc,eds,c,py] [--pdf-template NAME]
mapcan diff        OLD NEW [--format text|md|json]
mapcan import dbc  FILE.dbc [-o FILE.yaml] [--title TEXT] [--lang en] [--force]
mapcan migrate     FILE… [--check]      # former field names → current ones
mapcan fmt         FILE… [--check]      # keys in one order, comments and layout kept
mapcan schema      [-o schema.json] [--part]   # --part: schema of an included file
mapcan template    --list | pdf [--name gost-2.105] -o FILE | md|html|xlsx-style -o FILE
mapcan rules
```

## Validation

`validate` exits with code 1 on errors, and with `--strict` on warnings too. Every message points to
a file, line and column:

```text
$ mapcan validate tests/data/invalid_map.yaml
tests/data/invalid_map.yaml:21:25: error[number-comma]: value '0,1': decimal comma used, should be 0.1
tests/data/invalid_map.yaml:24:17: error[number-cyrillic-x]: value '0х196': the 0x prefix uses a Cyrillic “х”
tests/data/invalid_map.yaml:33:22: error[invalid-identifier]: value name 'NO DATA': only Latin letters, digits and _ are allowed
tests/data/invalid_map.yaml:62:36: error[duplicate-signal-name]: flag 'dc_status' already exists in frame 'pcu_state' (signal)
...
FAIL: errors: 12, warnings: 2, notes: 4
```

`mapcan rules` lists every rule; any of them can be turned off with `--disable CODE`.

## Documents

Documents can be produced in English or Russian. The default comes from the map's
`document.language`; override it with `--lang` or the language switch in the editor. The ESKD
template (`gost-2.105`) is always produced in Russian. No external programs are required: PDFs are
built by the bundled Typst compiler, and the PT Sans and PT Serif fonts (OFL) ship with the package.

| Format | How to customize |
|---|---|
| **PDF** | Two built-in templates: `mapcan` (standard layout) and ESKD `gost-2.105` (frame and title block). Copy one with `mapcan template pdf --name gost-2.105 -o corp.typ`, edit it, then export with `--template corp.typ`. Document details (designation, letter, signatures, approval blocks) and the company logo are set in `document.print`. See [templates.md](templates.md). |
| **Excel** | `mapcan template xlsx-style -o style.yaml`, adjust fonts, colors and columns, then `mapcan export xlsx map.yaml --style style.yaml`. |
| **Markdown / HTML** | Jinja2 templates over the same data: `mapcan template md -o my.md.j2`. |

## Generated C code

Each bus gets `<bus>.h` and `<bus>.c` with no dynamic memory and no libc beyond `stdint.h`,
`stdbool.h` and `stddef.h`. The code compiles cleanly with `-Wall -Wextra -Wconversion` for x86
and Cortex-M. For [examples/vehicle-can.yaml](../examples/vehicle-can.yaml):

```c
#include "powertrain.h"

vcu_command_t cmd = {0};
cmd.contactor_request = VCU_COMMAND_CONTACTOR_REQUEST_CLOSE;
cmd.torque_request = vcu_command_torque_request_from_phys(120.5f);   /* N·m → raw */
uint8_t buf[8];
int len = vcu_command_pack(buf, sizeof buf, &cmd);                   /* → VCU_COMMAND_ID */

bms_status_t st;
if (bms_status_unpack(&st, rx_data, rx_len) == 0 && st.pack_voltage > 350.0f) { ... }
```

Identifiers are named after the frame (`<FRAME>_ID`, `<frame>_t`, `<frame>_pack()`) and the device
(`<DEVICE>_NODE_ID`). Names are unique only within a bus, so a frame or device whose name is also on
another bus of the map gets its bus in front (`BODY_STATUS_ID`, `body_status_pack()`): a gateway can
include the headers of every bus. The constants of the map are named after the bus
(`<BUS>_MAP_VERSION_MAJOR`, `<BUS>_MAP_LAYOUT_CRC32`), so the headers of two maps build together; the
former `MAP_VERSION_*` and `MAP_LAYOUT_CRC32` stay as deprecated aliases unless `MAPCAN_NO_DEPRECATED`
is defined. `--prefix` puts one more prefix in front of every name and file.

Next to `<FRAME>_ID` and `<FRAME>_LENGTH`, the header tells the CAN driver how to send the frame:
`<FRAME>_IS_EXTENDED` for a 29-bit ID, and on a CAN FD bus `<FRAME>_IS_FD` and `<FRAME>_BRS`
(bit rate switch, `0` or `1`). The classes of the Python module carry the same as `IS_EXTENDED`,
`IS_FD` and `BITRATE_SWITCH`, named after the arguments of python-can's `can.Message`:

```python
msg = can.Message(arbitration_id=VcuCommand.ID, data=cmd.pack(), is_extended_id=VcuCommand.IS_EXTENDED,
                  is_fd=VcuCommand.IS_FD, bitrate_switch=VcuCommand.BITRATE_SWITCH)
```

## Importing a DBC

`mapcan import dbc` turns DBC nodes into devices (the sender of a frame owns it), and brings over
frames with their IDs, length, cycle or send type and receivers, and signals with their layout,
scaling, units, ranges, value tables, initial values and multiplexing. A bus whose frames are
marked J1939 (`VFrameFormat`) becomes a `j1939` bus with PGNs and device addresses; any other
becomes a `can` bus with explicit IDs. Value names become identifiers (`Not available` →
`NOT_AVAILABLE`, the original text goes to the description), and whatever DBC cannot express is
reported as a warning.

## CI

[ci-example.md](ci-example.md) shows a pipeline for map repositories: when the YAML changes, the map
is validated and the PDF, Excel, DBC and C headers are rebuilt and kept as artifacts. The Docker image
`ghcr.io/ordu1453/mapcan:<version>` contains everything needed.
