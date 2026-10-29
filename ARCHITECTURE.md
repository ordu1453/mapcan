# Architecture

mapcan turns one YAML file, the **map** of a CAN network, into everything that has to agree with it:
validation, documents, DBC/EDS, C and Python code, and two editors. This page tells you where each
piece lives and how data flows between them. How to build and test is in
[CONTRIBUTING.md](CONTRIBUTING.md); the format itself is in [docs/format.md](docs/format.md).

## The pipeline

```text
 map.yaml ──► loader.py ──► model.py ──► resolve.py ──► validate.py ──► outputs
 (+ include)  YAML with     pydantic     CAN IDs,       diagnostics       docmodel.py ─► export/ md, html, pdf, xlsx
              positions     models       bit layout,    with file:line    export/dbc.py, export/eds.py
                                         references                       codegen/ c.py, py.py
                                                                          diff.py (changelog between versions)
```

1. **[loader.py](src/mapcan/loader.py)** reads YAML with ruamel and keeps the line and column of
   every node (`SourceMap`), so any later message can point at the source. It merges `include`d
   files and `value_tables`, catches typical typos (a decimal comma, a Cyrillic "х" in `0x`), and
   turns pydantic errors into diagnostics.
2. **[model.py](src/mapcan/model.py)** is the format: pydantic models with a description on every
   field. Those descriptions are the single source of field help. They end up in the JSON Schema
   ([schema/mapcan.schema.json](schema/mapcan.schema.json), `mapcan schema`), the YAML hover of the
   language server and both form editors.
3. **[resolve.py](src/mapcan/resolve.py)** computes what the map does not spell out: CAN IDs
   ([protocols.py](src/mapcan/protocols.py), [canopen.py](src/mapcan/canopen.py)), signal positions
   from `byte`/`bit` shorthands, the owner device and bus of each frame, the layout of SDO exchanges.
4. **[validate.py](src/mapcan/validate.py)** runs the rules. Every rule has a code in `RULES`
   (`mapcan rules` lists them) and reports with `ctx.emit(code, message, path)`; the path is turned
   into file:line:column through the `SourceMap`.
5. **Outputs** read the resolved model only, never the YAML:
   - [docmodel.py](src/mapcan/docmodel.py) builds one view of the map for all documents;
     [export/text.py](src/mapcan/export/text.py) (Markdown, HTML via Jinja2),
     [export/pdf.py](src/mapcan/export/pdf.py) (Typst templates in `templates/pdf`) and
     [export/xlsx.py](src/mapcan/export/xlsx.py) render it.
   - [export/dbc.py](src/mapcan/export/dbc.py) (through cantools) and
     [export/eds.py](src/mapcan/export/eds.py) write files for other tools;
     [importers/dbc.py](src/mapcan/importers/dbc.py) goes the other way.
   - [codegen/](src/mapcan/codegen) writes C and Python. [bits.py](src/mapcan/bits.py) is the
     reference for bit positions and pack/unpack; tests compare the C code, the Python module and
     cantools byte for byte.

[cli.py](src/mapcan/cli.py) wires the pipeline into commands (`validate`, `export`, `gen`, `build`, …).

## Editors

Both editors change the YAML text, not the model, so comments and formatting survive. They share the
operations and the forms.

```text
 web editor (web/, Vue)  ──HTTP/WS──►  web/app.py + session.py ──► web/yamlops.py ─► map.yaml
 VS Code (vscode/)       ──LSP──────►  lsp/server.py + edits.py ──► web/yamlops.py ─► map.yaml
         └─ both render the node forms from packages/forms (one description of fields and help)
```

- **[web/yamlops.py](src/mapcan/web/yamlops.py)**: operations on the YAML document (`set`,
  `insert`, `remove`, `set_layout`, …) that keep the rest of the file as written.
- **[web/session.py](src/mapcan/web/session.py)** and **[web/app.py](src/mapcan/web/app.py)**:
  `mapcan serve` / `mapcan app` (the app is the same server in a pywebview window, see
  [launcher.py](src/mapcan/launcher.py)). The session holds the file, undo/redo and the git
  integration; the browser UI is built from [web/](web) into `src/mapcan/web/static`.
- **[lsp/](src/mapcan/lsp)**: `mapcan lsp`, the language server of the
  [VS Code extension](vscode). [analysis.py](src/mapcan/lsp/analysis.py) answers hover, completion,
  hints and definitions from the text; [edits.py](src/mapcan/lsp/edits.py) applies the same YAML
  operations as the web editor and serves the data of the node form.
- **[packages/forms/](packages/forms)** (`@mapcan/forms`, an npm workspace): the forms of all node kinds,
  written once and used by the web editor ([NodeEditor.vue](web/src/components/NodeEditor.vue)) and the VS Code form
  ([vscode/webview/form.js](vscode/webview/form.js), bundled by `vscode/esbuild.mjs`). A form lists
  fields, the conditions under which they apply and their options; the help of a field is its
  description in the model, read from the JSON Schema.

## Interface language

The interface is English. Messages are written in English in the code: `_()` / `N_()` in Python,
`t()` / `N_()` in the web UI. The English text is also the key of the Russian translation in
[src/mapcan/locale/ru.py](src/mapcan/locale/ru.py), [web/src/locale/ru.json](web/src/locale/ru.json) and
[packages/forms/src/locale/ru.json](packages/forms/src/locale/ru.json) (the strings of the forms).
The language of generated documents is a separate thing: `document.language` of the map or the
language chosen on export.

## Adding a field to the format

Tests point at most of the steps when one is missed.

1. **Model**: add the field to the class in [model.py](src/mapcan/model.py) with a `description`
   (`N_("…")`). Write the description for a user: it is the help in the forms and the hover in YAML.
2. **Schema**: `uv run mapcan schema -o schema/mapcan.schema.json` (`test_schema_file_up_to_date`).
3. **Meaning**: compute what follows from it in [resolve.py](src/mapcan/resolve.py) or a property
   of the model, and check it in [validate.py](src/mapcan/validate.py); a new rule gets a code in
   `RULES` and a row in the rule table of [docs/format.md](docs/format.md).
4. **Outputs** that should show or use it: documents ([docmodel.py](src/mapcan/docmodel.py)), DBC
   export and import, generated code, the changelog ([diff.py](src/mapcan/diff.py)).
5. **Forms**: add it to a section in [packages/forms/src/spec.ts](packages/forms/src/spec.ts), or to
   `NOT_IN_FORM` with where it is edited instead (`packages/forms/test/form.test.ts`). If its condition needs
   something new about the node, add it to `FormContext` and fill it in both hosts:
   [NodeEditor.vue](web/src/components/NodeEditor.vue) (from the map in the browser) and
   `node_fields` in [lsp/edits.py](src/mapcan/lsp/edits.py) (for VS Code).
6. **Translations**: Russian for every new message, in `ru.py` (Python) or `ru.json` (web)
   (`tests/test_i18n.py`).
7. **Docs**: the field table in [docs/format.md](docs/format.md), and an example map if the field
   is worth showing.

The commit that added `brs` (bit rate switch of CAN FD frames) is a compact example of most of these
steps: `git log --grep "bit rate switch"`.

## Renaming a field

A rename keeps the format version (see "Versioning and compatibility" in [docs/format.md](docs/format.md)):
the former name stays readable. Add a `Rename` to `RENAMES` in [upgrade.py](src/mapcan/upgrade.py)
(with a converter when the value changes too) and rename the field everywhere else as if it had always
had the new name. The loader rewrites the former key before validation and reports
`deprecated-key`; the editors get the current names
([session.py](src/mapcan/web/session.py), `node_fields` in [lsp/edits.py](src/mapcan/lsp/edits.py));
writing a field renames the former key in place (`upgrade_map` in
[yamlops.py](src/mapcan/web/yamlops.py)); `mapcan migrate` and the quick fix rewrite whole files.
Keep the codes of validation rules, and keep former names in the context of custom document
templates and in generated code as deprecated aliases. Add a row to the table in
[docs/format.md](docs/format.md#versioning-and-compatibility) and an entry to
[docs/format-changelog.md](docs/format-changelog.md). `tests/test_upgrade.py` shows the checks.

## A new format version

Removing a field or a value needs a new `mapcan:` version, with the previous one still read. Version 2
(#140) is the example: `FORMAT_VERSION` and the `mapcan` literal in [model.py](src/mapcan/model.py); the
conversion of the previous version in [upgrade.py](src/mapcan/upgrade.py) (`upgrade_v1`), applied by the loader
with the note `format-v1`, by the editors (`upgrade_data`, `node_fields`) and by `mapcan migrate`
(`migrate_format` in [yamlops.py](src/mapcan/web/yamlops.py)); the schema URLs in
[schema.py](src/mapcan/schema.py), with the previous schemas frozen in `schema/` and published by
[pages.yml](.github/workflows/pages.yml); maps of the previous version frozen in `tests/data/v1`, checked in
`tests/test_format_v1.py` to give the same outputs as the current ones.
