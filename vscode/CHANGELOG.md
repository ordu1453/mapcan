# Changelog

## Unreleased

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
