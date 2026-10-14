# Changelog

## Unreleased

* Needs mapcan 0.21 or newer. The extension checks the version of the language server when it
  starts and, for an older one, offers the update command in a terminal (also when the server
  cannot be started at all). **mapcan: Show Server Version** gives both versions for bug reports.
* Works in Restricted Mode (a folder that is not trusted): the command of the language server and
  the export folder come from the user's settings only, not from the folder's
  `.vscode/settings.json`. Trusting the folder restarts the server with its settings.
* Follows mapcan 0.21: the frame field **DLC** is **Length, bytes** (`length`). A map with the former
  name `dlc` still works; the form writes `length` in its place, and the quick fix of `deprecated-key`
  updates the whole map.
* A signal's **Signed** and **Sign encoding** are one field, **Number representation**
  (`representation`: unsigned, two's complement, ones' complement, sign-magnitude).
* A frame's **Type** is **CANopen function** (`canopen`); "none — explicit ID" leaves it out.
* A signal's **Invalid (raw)** is **Not available (raw)** (`invalid_raw`) and takes ranges such as
  `0xFF00..0xFFFF`. Values given by meaning (`not_available`, `error`) are shown read-only.
* A bus's **Interface** is **Connector** (`connector`): the connector or harness for documents. The CAN
  adapter and channel of a workstation are not part of the map.
* The print details of the title page (logo, designation, signatures…) are in `document.print`; the
  quick fix of `deprecated-key` moves them there.
* A raw signal has **Value from the map** (`source`): the map version or the layout CRC32, for a
  frame in which a device reports the map it was built from.
* A file included by a map, which now starts with `mapcan: 1` and `part_of`, is checked as a part of
  that map: its problems show in it (also with unsaved changes in either file), the Map view shows the
  whole map with the nodes of the other file marked with it, and Go to Definition on a receiver leads to
  the device in the main file.
* Nodes of an included file are edited in that file from either file's Map view: the form writes their
  fields there, and **Add**, **Duplicate**, **Rename** and **Delete** change that file. A node added to a
  bus of the main file goes to the main file, one added to a node of the included file to the included
  file. Rename Symbol (F2) and Find All References on a device cover every file of the map: renaming a
  receiver in the main file renames the device described in an included file too, and the other way
  round.
* A change the panel or the Map view writes to another file of the map that is not open in an editor
  is named in a message with **Save** and **Open**, so its changes are not left unsaved unnoticed.
* New fields from mapcan 0.21: a frame's **Receive timeout**, a bus's sample points and CAN FD data
  phase bit rate, and the `string` encoding of signals with **Charset** and **Terminator**.
* The language server is started when the first map is opened, not for any YAML file, and only maps
  are sent to it. Other YAML files (CI configs, manifests) no longer start a `mapcan` process or show
  an error when `mapcan` is not installed. A new file is picked up once `mapcan:` is typed into it.
* The language server stops when no map has been open in an editor tab for five minutes and starts
  again with the next map.
* When the server cannot be started, the message suggests installing mapcan from PyPI with
  `uv tool install "mapcan[lsp]"` or `pipx install "mapcan[lsp]"`.

## 0.5.1

* Fixed the empty **Node** panel: its bundled script was outside the webview's resource roots
  and did not load.
* The **Map** view shows the buses, devices and frames of included files (`include`), marked with
  the file name; clicking one opens it in its file, and its **Node** panel is read-only.

## 0.5.0

* Follows the stricter map format of mapcan 0.19: every signal names its `encoding` (renamed from
  `kind`, no automatic choice), its length is explicit, frames have `dlc`, transmission is
  `cycle_ms` and `trigger`, and SDO values name their encoding and length. The **Node** panel edits
  these fields and shows the computed frame direction.
* New fields in the **Node** panel: J1939 `spn` and the CANopen dictionary object (`index`,
  `subindex`) of a PDO signal. A signal that uses a named value table shows the table read-only.
* **Export…** offers EDS: one file per CANopen device with its mapped objects and PDOs.
* Diagnostics of included files are shown on the `include` line of the main map.

## 0.4.0

* The **Node** panel shows the frame's bit layout for frames, signals, flags and SDO exchanges, as
  the web editor does: drag over free bits to add a signal, drag the shown signal to move it or its
  edge to change its length. The value table of a signal or flag and the flags of a bit field are
  edited in the panel instead of only in the YAML.
* The **Map** view marks nodes added (**A**) or modified (**M**) since the last commit, as Source
  Control marks files; unsaved edits count. Setting: `mapcan.tree.showChanges`.
* **Release Version…** in the **History** panel: a revision history entry, the document's version
  and date, a commit of the map and the tag `v<version>` in one action. The History panel shows tags.

## 0.3.0

* New frames are made as in the web editor: a frame of a CANopen device gets the first free PDO
  type (`pdo_tx1`…`pdo_rx4`, its ID computed from the node ID), a J1939 frame a free PGN with
  priority 6, other frames a free explicit ID; all with DLC 8 and a 100 ms cycle. The **Type**
  field of the Node panel (CANopen buses only) drops a DLC that the new type does not allow.
* The **Type** field disables types whose CAN ID another frame already has and names that frame; a
  frame of the bus itself offers only the types that do not depend on a node ID. A duplicate
  CAN ID from a PDO type has a quick fix: a free PDO of the same direction.
* **History** panel in the side bar: the map's Git commits and uncommitted changes. Commit or
  discard the changes of the map, compare any two versions, open or restore a version, and add the
  changes to the revision history in the YAML (`document.history`). Comparisons open in one
  **Changes** tab instead of a new preview each time.
* The **Node** panel has all the fields of the web editor: byte order of any signal longer than a
  byte (not only on CAN buses), signed code, "no data" values, value format, multiplexer selector and
  mux values, notes of frames and signals, the bus interface, the J1939 destination address and the
  value of an SDO exchange.

## 0.2.0

* The Map view shows names for people (titles, "abbreviation · full name" for devices, the sender
  of received frames) instead of identifiers, as the web editor does; identifiers are in tooltips.
* The **+** buttons open the new node in the **Node** panel, whose fields are written to the YAML as
  you type, with a list of standard units for the unit field. **Edit…** opens existing nodes there. New buses and devices get a default full name.
* **Add Bus** in the Map view title.
* Export moved to its own **Export** panel in the side bar: formats, output folder, exported files.

## 0.1.0

* First version: validation, hovers with frame bit layouts, inlay hints with computed CAN IDs and
  signal bits, value completion and document outline. Runs `mapcan lsp`.
* Map view in the Activity Bar that follows the cursor.
* **mapcan: Export…** for DBC, C, Python, Excel, PDF, Markdown and HTML.
* Map view: add, rename, duplicate and delete nodes; problems on nodes.
* Quick fixes, device references and rename, snippets.
* Document preview and comparison with a Git revision.
