# Contributing to mapcan

Thanks for helping. Bug reports, examples of real maps that mapcan handles badly, and pull requests
are all welcome. Start with [ARCHITECTURE.md](ARCHITECTURE.md) for a map of the code.

## Reporting a problem

Open an issue from the bug report form with the smallest map that shows it (a few lines of YAML), the command or editor
action, and what you expected. For a wrong DBC, document or generated code, say which tool reads it
and what it shows.

Security problems are reported privately, not in an issue: see [SECURITY.md](SECURITY.md).

## Setting up

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12, the version of `.python-version`;
3.13 and 3.14 are supported too), and for the UI parts
Node.js 24. A C compiler (`gcc`, and `arm-none-eabi-gcc` if you have it) lets the tests compile the
generated C code; without one those tests are skipped.

```sh
uv sync                     # Python environment from uv.lock, with every extra (mapcan[all])
uv run pre-commit install   # ruff before every commit, as in CI
uv run mapcan --help
npm ci                      # the web editor and the VS Code extension (npm workspaces, one lock file at the root)
```

The npm projects (`web`, `vscode` and the shared packages in `packages/`) are
[npm workspaces](https://docs.npmjs.com/cli/using-npm/workspaces) with one `package-lock.json` at the
root: install and add dependencies from the root (`npm install -D vite -w web`), not inside a folder.

Running the pieces:

| What | How |
|---|---|
| CLI | `uv run mapcan validate examples/vehicle-can.yaml` |
| Web editor, backend | `uv run mapcan serve examples/vehicle-can.yaml --no-browser` (API on :8765) |
| Web editor, UI with hot reload | `cd web && npm run dev` (http://localhost:5173) |
| VS Code extension | `cd vscode && npm run build`, open `vscode/` in VS Code, press F5 |

Without uv:

```sh
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -e ".[all]"
```

## Tests

Run the tests of what you changed; CI runs all of them on every push and pull request.

| Part | Command |
|---|---|
| Python: format, validation, exports, code generation, LSP, web API | `uv run pytest` |
| Lint | `uv run ruff check src tests` |
| Web UI: types, build, unit tests | `cd web && npm run build && npm test` |
| Shared forms: types, unit tests | `npm run typecheck -w @mapcan/forms && npm test -w @mapcan/forms` |
| Web UI in a browser: user flows and the accessibility check (`web/e2e`) | `cd web && npx playwright install chromium && npm run e2e` (or `PLAYWRIGHT_CHANNEL=msedge` / `chrome` with an installed browser) |
| VS Code extension: types, integration tests in a real VS Code | `cd vscode && npm run typecheck && npm test` |
| All npm workspaces: types, builds, unit and integration tests | `npm run typecheck`, `npm run build`, `npm test` at the root |

Some outputs are compared with reference files in `tests/golden`. After an intended change,
refresh them with `UPDATE_GOLDEN=1 uv run pytest` and check the diff before committing.

Generated files that are committed, and that CI checks are up to date:

- `schema/mapcan.schema.json`: `uv run mapcan schema -o schema/mapcan.schema.json` after changing
  [model.py](src/mapcan/model.py).
- `src/mapcan/web/static`: `npm run build` in `web/` after changing anything in `web/src`.

The tests compile the generated C code with `gcc` (and `arm-none-eabi-gcc` if installed) and compare
`pack`/`unpack` byte for byte with the Python module and cantools for every example.

## Screenshots

The pictures in the READMEs are taken by scripts, in the light and the dark theme, into `docs/images/`
(Windows; the window of the browser or of VS Code may show meanwhile):

- `cd web && npm run screenshots`: the web editor and pages of a PDF, for the main README;
- `cd vscode && npm run screenshots`: VS Code, for both READMEs; the walkthrough's own pictures come from
  `vscode/scripts/walkthrough-scenes.cjs`.

## Writing code

- **English** everywhere: code, comments, docstrings, docs, commit messages. Some older comments are
  still in Russian (#52); translate the ones you touch if you like.
- **Messages for users** go through `_("…")` in Python or `t("…")` in the web UI and need a Russian
  translation in [src/mapcan/locale/ru.py](src/mapcan/locale/ru.py),
  [web/src/locale/ru.json](web/src/locale/ru.json) or, for the forms,
  [packages/forms/src/locale/ru.json](packages/forms/src/locale/ru.json); `tests/test_i18n.py` lists what is missing.
- **Style**: ruff with a line length of 120 (configured in `pyproject.toml`). Match the code around
  you: short comments that say why, not what.
- **Changing the format** (a new field, a new rule): follow the checklist in
  [ARCHITECTURE.md](ARCHITECTURE.md#adding-a-field-to-the-format). Keep old maps valid; if that is
  impossible, say so in the pull request.
- **Tests** come with the change: a validation rule gets a test in `tests/test_validate.py`, an
  export or generator change one next to the existing tests of that output.

## Commits and pull requests

- One logical change per commit. The subject is an imperative sentence in English without a
  trailing period ("Add a bit rate switch (BRS) flag to CAN FD frames"); the body explains why and
  what a reader of the diff would not see. Reference issues with `Closes #N` / `Part of #N`.
- Open the pull request against `main` and fill in the template. Describe what changes for users of the format, the CLI or
  the editors; screenshots help for UI changes.

## Releases

Maintainers release by bumping the version and pushing a tag.

### mapcan

1. Bump the version in `pyproject.toml`, `src/mapcan/__init__.py`, `web/package.json` and
   `CITATION.cff` (also its `date-released`) (`uv lock`, `npm run build` in `web/`), commit.
2. Create and push a tag: `git tag -a vX.Y.Z -m "mapcan X.Y.Z: …" && git push origin main vX.Y.Z`.

[release.yml](.github/workflows/release.yml) runs the tests, checks that the tag matches the version,
builds the Windows installer and zip (PyInstaller + Inno Setup), the wheel and the Docker image, and
publishes a GitHub Release (the tag annotation becomes the release notes) and then the package on PyPI.
[pages.yml](.github/workflows/pages.yml) publishes the JSON Schemas of the release on GitHub Pages.
Running release.yml by hand (Actions → release → Run workflow) makes a trial build without publishing;
with **Publish to TestPyPI** checked, the package goes to [TestPyPI](https://test.pypi.org/project/mapcan/)
to check the upload and the project page.

Building the Windows version locally:

```sh
uv sync --extra desktop --group package
uv run pyinstaller packaging/mapcan.spec --noconfirm        # → dist/mapcan/
iscc /DAppVersion=X.Y.Z packaging/mapcan.iss                # → dist/mapcan-X.Y.Z-setup.exe
```

### The VS Code extension

1. If the extension needs a newer language server, release mapcan first and raise `MIN_SERVER` in
   `vscode/src/version.ts`.
2. In `vscode/`: `npm version X.Y.Z --no-git-tag-version`; in `vscode/CHANGELOG.md` rename
   `## Unreleased` to `## X.Y.Z`; commit.
3. Create and push a tag: `git tag -a extension-vX.Y.Z -m "mapcan for VS Code X.Y.Z" && git push origin main extension-vX.Y.Z`.

[extension-release.yml](.github/workflows/extension-release.yml) checks that the tag matches
`vscode/package.json` and that the changelog has the section, runs the typecheck and the integration
tests, packages the `.vsix`, publishes a GitHub Release with it and the changelog section, and then the
extension on [Open VSX](https://open-vsx.org/extension/ordu1453/mapcan) (secret `OVSX_PAT`) and the
[Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=ordu1453.mapcan) (secret
`VSCE_PAT`, a token of the publisher `ordu1453` with the scope Marketplace → Manage; without it that step
only warns, and the `.vsix` of the release is uploaded by hand). Running the workflow by hand makes a
trial `.vsix` (an artifact) without releasing.

## Repository layout

```text
examples/                   example maps (CANopen, J1939, CAN/CAN FD, a map in two files)
schema/                     JSON Schemas of a map and of an included file (mapcan schema -o …)
docs/                       format, command line, PDF templates, web editor, CI; images/ — screenshots
src/mapcan/
  model.py                  data model (pydantic)
  loader.py                 YAML loading with node positions
  protocols.py, canopen.py  CAN ID computation: CANopen, J1939, explicit IDs
  resolve.py                references, SDO layout
  validate.py               validation rules
  bits.py                   bit layout, pack/unpack
  docmodel.py               shared view for documents
  export/                   xlsx, pdf (Typst), md/html (Jinja2), dbc, eds
  codegen/                  C and Python
  importers/                DBC import
  diff.py                   map version comparison, changelog
  lsp/                      language server for the editors
  launcher.py               mapcan app: window, single instance, port selection
  updates.py                new version check on GitHub Releases
  web/                      web editor: FastAPI, YAML operations, built UI (static/)
  templates/                document templates (pdf/ — Typst)
  fonts/                    PT Sans, PT Serif (OFL)
web/                        UI sources (Vue 3 + TypeScript + Vite)
packages/forms/             @mapcan/forms: node forms of both editors (fields, conditions, help from the schema)
vscode/                     VS Code extension (language server client, map tree, node form in webview/)
packaging/                  Windows build: PyInstaller, Inno Setup installer, icon and logo
tests/                      tests; data/ — fixtures, golden/ — reference files
```
