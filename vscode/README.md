# mapcan for VS Code

Language support for [mapcan](https://github.com/ordu1453/mapcan) CAN signal maps. A map is a YAML
file with a top-level `mapcan: 1` key. Other YAML files are left alone.

## Features

* **Map view.** The mapcan icon in the Activity Bar opens the buses, devices, frames, signals and
  flags of the active map, with computed CAN IDs and signal bits.
  * Clicking a node selects its lines in the editor, and moving the cursor selects the node under it.
  * The **+** button and the context menu add devices, frames and signals. The context menu also
    renames (F2), duplicates and deletes (Delete) nodes. Every change is a normal edit, so Undo
    reverts it.
  * Nodes with errors or warnings are colored, and a badge shows how many problems they have.
* **Quick fixes** (the light bulb, Ctrl+.):
  * decimal commas, a Cyrillic «х» in hex numbers and hex numbers in quotes;
  * a missing space after `-`;
  * misspelled keys, values, receivers and senders;
  * overlapping signals moved to free bits, `extended: true` for 29-bit IDs, names in the lint
    style, the document version from the history.
* **Device references.** Go to Definition (F12) from `receivers` and `sender` to the device, Find
  All References (Shift+F12), and Rename (F2) that updates every reference.
* **Snippets.** After `- `, completion offers a device, a frame and signals (plain, with a value
  table, a physical quantity, a bit field).
* **Preview and comparison.** **mapcan: Open Document Preview** shows the map's document in the
  Markdown preview and follows edits. **mapcan: Compare with Revision…** lists the map's Git
  history and shows what changed since the chosen version.
* **Export.** **mapcan: Export…** (also the button in the Map view) builds DBC, C and Python code,
  Excel, PDF, Markdown and HTML from the current text of the map, unsaved edits included, into
  `build/` next to the map. It refuses while the map has errors.
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
| `mapcan.export.outputDir` | `"build"` | Export folder, relative to the map's folder |

## Commands

* **mapcan: Export…**
* **mapcan: Open Document Preview**
* **mapcan: Compare with Revision…**
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
(`uv sync --extra lsp`).

`npm test` runs the integration tests in a separate VS Code that it downloads into `.vscode-test/`.
To use an installed VS Code instead, set `VSCODE_PATH` to its executable; that VS Code must not be
running.
