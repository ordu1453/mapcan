# mapcan for VS Code

Language support for [mapcan](https://github.com/ordu1453/mapcan) CAN signal maps. A map is a YAML
file with a top-level `mapcan: 1` key. Other YAML files are left alone.

## Features

* **Validation as you type.** mapcan reports errors and warnings in the editor and in the Problems
  panel, each with its rule code.
* **Hovers.**
  * A field key shows what the field means.
  * A signal shows its bits, scaling, unit, range and value table.
  * A frame shows its CAN ID, DLC, cycle, sender and receivers, plus a byte-by-bit layout table.
* **Inlay hints.** Computed CAN IDs appear next to frames that have no explicit `id` (CANopen,
  J1939), and the occupied bits appear next to each signal.
* **Completion.** Enumerated values such as `kind`, `byte_order`, `protocol` and `type`, and device
  names for `sender` and `receivers`.
* **Outline and breadcrumbs.** Buses, devices, frames, signals and flags.

For completion of keys, install the
[YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) and add
the schema comment that `mapcan` maps already use:

```yaml
# yaml-language-server: $schema=https://…/mapcan.schema.json
```

## Requirements

The extension runs the language server from the `mapcan` command-line tool:

```sh
pip install "mapcan[lsp]"
```

If `mapcan` is not on `PATH`, set **mapcan.server.path** to the executable.

## Settings

| Setting | Default | Description |
|---|---|---|
| `mapcan.server.path` | `""` | Path to the `mapcan` executable; empty uses `PATH` |
| `mapcan.server.args` | `["lsp"]` | Arguments for the executable |

## Commands

* **mapcan: Restart Language Server**
* **mapcan: Show Language Server Output**

## Development

```sh
cd vscode
npm install
npm run build
```

Open the `vscode/` folder in VS Code and press F5. The Extension Development Host opens the
`examples/` folder and runs the language server from the repository's `.venv`
(`pip install -e ".[lsp]"`).
