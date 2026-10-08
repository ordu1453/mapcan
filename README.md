<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-dark.svg">
    <img src="docs/logo-light.svg" alt="mapcan" height="110">
  </picture>
</p>

<p align="center">
  <b>CAN signal maps as code.</b><br>
  One YAML file → documentation, DBC, C firmware code and Python test helpers.
</p>

<p align="center">
  <a href="https://github.com/ordu1453/mapcan/actions/workflows/ci.yml"><img src="https://github.com/ordu1453/mapcan/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/ordu1453/mapcan/releases/latest"><img src="https://img.shields.io/badge/release-latest-2f6fb3" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/python-3.12-3776ab?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555" alt="Platforms">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-2f6fb3" alt="License: Apache-2.0"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/CANopen-✓-1f883d" alt="CANopen">
  <img src="https://img.shields.io/badge/SAE%20J1939-✓-1f883d" alt="SAE J1939">
  <img src="https://img.shields.io/badge/CAN%202.0A%2FB-✓-1f883d" alt="CAN 2.0A/B">
  <img src="https://img.shields.io/badge/CAN%20FD-✓-1f883d" alt="CAN FD">
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#installation">Installation</a> ·
  <a href="#outputs">Outputs</a> ·
  <a href="#web-editor">Web editor</a> ·
  <a href="#commands">Commands</a> ·
  <a href="docs/format.md">Map format</a> ·
  <a href="#development">Development</a>
</p>

---

**mapcan** creates and edits CAN signal maps for any device or system. The map lives in a single
YAML file, which is the single source of truth: documents, firmware code and files for bus
analyzers are all generated from it, so they never drift apart.

* **Protocols** — CANopen (IDs from the function code and `node_id`), SAE J1939 (IDs from PGN,
  priority and address), CAN 2.0A/B with explicit 11/29-bit IDs, CAN FD with DLC up to 64.
* **Signals** — signed and unsigned integers of any length and position, little- and big-endian;
  enumerations, flags and bit fields; physical quantities with `factor`, `offset`, unit and range;
  float32/float64; byte arrays; multiplexing; default and "not available" values.
* **Frames** — cycle time, direction, sender and receivers, CANopen SDO exchanges. Each frame is
  described once, at its sender; what every device receives is derived for the editor, the
  documents (including an Excel communication matrix) and DBC.
* **Validation** — every error points to a file, line and column, before anything is generated.

```yaml
mapcan: 1

document:
  title: Electric vehicle example map
  version: 0.1.0
  language: en

buses:
  - name: powertrain
    bitrate: 500000
    protocol: can
    devices:
      - name: bms
        frames:
          - name: bms_status
            id: 0x100
            dlc: 8
            cycle_ms: 100
            receivers: [vcu]
            signals:
              - {name: pack_voltage, byte: 0, encoding: float, unit: V, min: 0, max: 1000}
              - {name: pack_current, byte: 4, encoding: float, unit: A, initial: 0}
      - name: vcu
```

## Quick start

```sh
mapcan app
```

The editor opens in its own window. Click **New map…** and pick a template — CANopen, J1939,
CAN with explicit IDs or an empty map — or start from one of the examples on the start screen.
Add devices, frames and signals in the tree, and draw signals with the mouse on the frame's bit
layout. Errors show up as you type; <kbd>Ctrl</kbd>+<kbd>S</kbd> saves the file.

Prefer a text editor? Write the YAML by hand with completion and hints from the JSON Schema in
VS Code — see [docs/format.md](docs/format.md).

## Installation

| Platform | How |
|---|---|
| **Windows** | Download `mapcan-X.Y.Z-setup.exe` from [Releases](https://github.com/ordu1453/mapcan/releases/latest) and run it. No Python or administrator rights needed. |
| **Linux x64** | Download `mapcan-X.Y.Z-linux-x64.tar.gz`, extract it and run `mapcan/mapcan-app` (editor in the browser) or `mapcan/mapcan` (CLI). |
| **Any OS with Python 3.12** | `uv tool install "mapcan[desktop] @ git+https://github.com/ordu1453/mapcan"` (or `pipx install …`) |
| **Docker** | `ghcr.io/ordu1453/mapcan:<version>` — everything needed for CI |

No external programs are required: PDFs are built by the bundled Typst compiler, and the PT Sans
and PT Serif fonts (OFL) ship with the package.

<details>
<summary><b>Windows installer details</b></summary>

The installer adds mapcan to the Start menu and the desktop, to "Open with" for `.yaml` files and,
optionally, the `mapcan` command to `PATH`. Launching it again or double-clicking a map opens the
map in the window that is already running. A banner at the top of the editor announces new
versions; the update installs over the current one. A portable build is also available:
`mapcan-X.Y.Z-windows-x64.zip`, run `mapcan-app.exe`.

The installer is not code-signed, so SmartScreen may warn about an unknown publisher — click
**More info → Run anyway**.
</details>

<details>
<summary><b>Offline install</b> (corporate network without PyPI)</summary>

Build a wheelhouse on a machine with access and copy the folder over:

```sh
pip wheel . -w wheelhouse
pip install --no-index --find-links wheelhouse mapcan
```
</details>

<details>
<summary><b>Moving from canmap</b></summary>

The tool used to be called canmap. The Windows installer upgrades the old version by itself; with
uv/pipx run `uv tool uninstall canmap`, then install again. Settings move from `~/.canmap` to
`~/.mapcan`, and the `canmap` PDF template is read as `mapcan`. Maps need the `mapcan: 1` key
(see [docs/format.md](docs/format.md)).
</details>

## Outputs

| Output | Command |
|---|---|
| 🖥️ Web editor: tree, forms, bit layout, live validation | `mapcan app` / `mapcan serve` |
| ✅ Validation with file and line numbers | `mapcan validate my-map.yaml` |
| 📊 Excel: addressing, contents, bit layouts, changes | `mapcan export xlsx my-map.yaml` |
| 📄 PDF: title page, contents, bit diagrams, tables | `mapcan export pdf my-map.yaml` |
| 📝 Markdown for a README or wiki, HTML page with search | `mapcan export md` / `mapcan export html` |
| 🔌 DBC for CANalyzer, SavvyCAN, PCAN-View, Wireshark | `mapcan export dbc my-map.yaml -o dbc/` |
| ⚙️ C: ID `#define`s, `enum`s, masks, structs, `pack`/`unpack` | `mapcan gen c my-map.yaml -o firmware/` |
| 🐍 Python module for tests and test benches | `mapcan gen py my-map.yaml -o tools/` |
| 📦 Everything at once, for CI | `mapcan build my-map.yaml -o build/` |
| 🔀 Comparison of two map versions, changelog | `mapcan diff old.yaml my-map.yaml` |
| 📥 Start from an existing DBC | `mapcan import dbc vehicle.dbc -o my-map.yaml` |

Documents can be produced in English or Russian. The default comes from the map's
`document.language`; override it with `--lang` or the language switch in the editor. The ESKD
template (`gost-2.105`) is always produced in Russian.

`mapcan import dbc` turns DBC nodes into devices (the sender of a frame owns it), and brings over
frames with their IDs, DLC, cycle or send type and receivers, and signals with their layout,
scaling, units, ranges, value tables, initial values and multiplexing. A bus whose frames are
marked J1939 (`VFrameFormat`) becomes a `j1939` bus with PGNs and device addresses; any other
becomes a `can` bus with explicit IDs. Value names become identifiers (`Not available` →
`NOT_AVAILABLE`, the original text goes to the description), and whatever DBC cannot express is
reported as a warning.

### Generated C code

Each bus gets `<bus>.h` and `<bus>.c` with no dynamic memory and no libc beyond `stdint.h`,
`stdbool.h` and `stddef.h`. The code compiles cleanly with `-Wall -Wextra -Wconversion` for x86
and Cortex-M. For [examples/vehicle-can.yaml](examples/vehicle-can.yaml):

```c
#include "powertrain.h"

vcu_command_t cmd = {0};
cmd.contactor_request = VCU_COMMAND_CONTACTOR_REQUEST_CLOSE;
cmd.torque_request = vcu_command_torque_request_from_phys(120.5f);   /* N·m → raw */
uint8_t buf[8];
int dlc = vcu_command_pack(buf, sizeof buf, &cmd);                   /* → VCU_COMMAND_ID */

bms_status_t st;
if (bms_status_unpack(&st, rx_data, rx_len) == 0 && st.pack_voltage > 350.0f) { ... }
```

### Validation

Export and generation validate the map first and stop on errors (`--force` generates anyway).
`validate` exits with code 1 on errors, and with `--strict` on warnings too.

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

## Web editor

```sh
mapcan app                    # own window; start screen: new map, open, recent files, examples
mapcan app my-map.yaml        # open a map right away
mapcan serve my-map.yaml      # the same in the browser
```

* Map tree with search by name, ID, PGN and description.
* Property forms that adapt to the bus protocol.
* Bit layout editor: drag across bits to add a signal, drag a signal to move it, drag its edge to
  resize; overlaps are highlighted.
* Value and flag tables, live validation and a YAML tab.
* Preview and download of every format.
* Comparison with any git revision, with the changelog written into the revision history.

Files are saved with their comments and formatting intact, so `git diff` shows only the lines you
changed. More in [docs/web.md](docs/web.md).

## Examples

| File | What it shows |
|---|---|
| [minimal.yaml](examples/minimal.yaml) | Every kind of signal in one CANopen frame: enum, bit field, quantities, big-endian |
| [j1939.yaml](examples/j1939.yaml) | SAE J1939: engine (EEC1, ET1), instrument cluster, addressed PDU1 request, "not available" 0xFF/0xFFFF |
| [vehicle-can.yaml](examples/vehicle-can.yaml) | Explicit 11/29-bit IDs: float32, multiplexed cell voltages, receivers, CAN FD with DLC 64 and float64 |

The same examples are on the editor's start screen: pick one, choose where to save a copy, and it
opens.

## Commands

```text
mapcan app         [FILE|DIR] [--browser] [--readonly]
mapcan serve       [FILE|DIR] [--host 127.0.0.1] [--port 8765] [--readonly] [--no-browser]
mapcan validate    FILE [--strict] [--info] [--format json] [--disable CODE]
mapcan export xlsx FILE [-o OUT] [--style style.yaml] [--lang en]
mapcan export pdf  FILE [-o OUT] [--template mapcan|gost-2.105|my.typ] [--font-path DIR] [--lang en]
mapcan export md   FILE [-o OUT] [--template my.md.j2] [--lang en]
mapcan export html FILE [-o OUT] [--template my.html.j2] [--lang en]
mapcan export dbc  FILE [-o DIR|file.dbc] [--bus NAME]
mapcan gen c       FILE [-o DIR] [--prefix my_] [--bus NAME]
mapcan gen py      FILE [-o DIR] [--bus NAME]
mapcan build       FILE [-o DIR] [--formats xlsx,pdf,md,html,dbc,c,py] [--pdf-template NAME]
mapcan diff        OLD NEW [--format text|md|json]
mapcan import dbc  FILE.dbc [-o FILE.yaml] [--title TEXT] [--lang en] [--force]
mapcan schema      [-o schema.json]
mapcan template    --list | pdf [--name gost-2.105] -o FILE | md|html|xlsx-style -o FILE
mapcan rules
```

## Custom styling

| Format | How to customize |
|---|---|
| **PDF** | Two built-in templates: `mapcan` (standard layout) and ESKD `gost-2.105` (frame and title block). Copy one with `mapcan template pdf --name gost-2.105 -o corp.typ`, edit it, then export with `--template corp.typ`. Document details (designation, letter, signatures, approval blocks) and the company logo are set in `document`. See [docs/templates.md](docs/templates.md). |
| **Excel** | `mapcan template xlsx-style -o style.yaml`, adjust fonts, colors and columns, then `mapcan export xlsx map.yaml --style style.yaml`. |
| **Markdown / HTML** | Jinja2 templates over the same data: `mapcan template md -o my.md.j2`. |

## CI

[docs/ci-example.md](docs/ci-example.md) shows a pipeline for map repositories: when the YAML
changes, the map is validated and the PDF, Excel, DBC and C headers are rebuilt and kept as
artifacts. The [Docker image](Dockerfile) `ghcr.io/ordu1453/mapcan:<version>` contains everything
needed.

## Development

```sh
uv sync                           # environment from uv.lock
uv run mapcan --help
uv run pytest
UPDATE_GOLDEN=1 uv run pytest     # refresh reference files after intentional changes
```

The tests compile the generated C code with `gcc` (and `arm-none-eabi-gcc` if installed) and
compare `pack`/`unpack` byte for byte with the Python module and cantools for every example.
The UI lives in [web/](web/) (Vue 3 + TypeScript + Vite); `npm run build` there writes the bundle
to `src/mapcan/web/static/`.

<details>
<summary><b>Without uv</b></summary>

```sh
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -e .
```
</details>

<details>
<summary><b>Releasing a version</b></summary>

1. Bump the version in `pyproject.toml`, `src/mapcan/__init__.py` and `web/package.json`
   (`uv lock`, `npm run build` in `web/`), commit.
2. Create and push a tag: `git tag -a vX.Y.Z -m "mapcan X.Y.Z: …" && git push origin main vX.Y.Z`.

[release.yml](.github/workflows/release.yml) runs the tests, checks that the tag matches the
version, builds the Windows installer and zip (PyInstaller + Inno Setup), the wheel and the Docker
image, and publishes a GitHub Release; the tag annotation becomes the release notes. Running the
workflow by hand (Actions → release → Run workflow) makes a trial build without publishing.

Building the Windows version locally:

```sh
uv sync --extra desktop --group package
uv run pyinstaller packaging/mapcan.spec --noconfirm        # → dist/mapcan/
iscc /DAppVersion=X.Y.Z packaging/mapcan.iss                # → dist/mapcan-X.Y.Z-setup.exe
```
</details>

<details>
<summary><b>Repository layout</b></summary>

```text
examples/                   example maps (CANopen, J1939, CAN/CAN FD)
schema/mapcan.schema.json   JSON Schema (mapcan schema -o …)
docs/                       format, PDF templates, web editor, CI, logo
src/mapcan/
  model.py                  data model (pydantic)
  loader.py                 YAML loading with node positions
  protocols.py, canopen.py  CAN ID computation: CANopen, J1939, explicit IDs
  resolve.py                references, SDO layout
  validate.py               validation rules
  bits.py                   bit layout, pack/unpack
  docmodel.py               shared view for documents
  export/                   xlsx, pdf (Typst), md/html (Jinja2), dbc
  codegen/                  C and Python
  diff.py                   map version comparison, changelog
  launcher.py               mapcan app: window, single instance, port selection
  updates.py                new version check on GitHub Releases
  web/                      web editor: FastAPI, YAML operations, built UI (static/)
  templates/                document templates (pdf/ — Typst)
  fonts/                    PT Sans, PT Serif (OFL)
web/                        UI sources (Vue 3 + TypeScript + Vite)
packaging/                  Windows build: PyInstaller, Inno Setup installer, icon and logo
tests/                      tests; data/ — fixtures, golden/ — reference files
```
</details>

## Roadmap

- [ ] Import existing maps from DBC and Excel
- [ ] Live bus: log decoding, monitor, simulator

## License

mapcan is free and open source, licensed under the [Apache License 2.0](LICENSE).
Copyright 2026 Ali Ordu — see [NOTICE](NOTICE).

* **Your outputs are yours.** Files generated from your map — C and Python code, DBC, PDF, Excel,
  Markdown and HTML — belong to you and may be used under any terms, including in closed-source
  firmware. The "Generated by mapcan" header is a courtesy, not a requirement.
* **The map format is open.** The format specification ([docs/format.md](docs/format.md)) is
  available under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); the JSON Schema
  ([schema/mapcan.schema.json](schema/mapcan.schema.json)) and the example maps
  ([examples/](examples/)) are dedicated to the public domain under
  [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). Anyone may implement readers,
  writers and tools for the format.
* **Third-party components** bundled with mapcan are listed in
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

If mapcan helps your project, a star on GitHub or a citation ([CITATION.cff](CITATION.cff)) is
much appreciated.
