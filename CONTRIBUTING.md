# Contributing to mapcan

Thanks for helping. Bug reports, examples of real maps that mapcan handles badly, and pull requests
are all welcome. Start with [ARCHITECTURE.md](ARCHITECTURE.md) for a map of the code.

## Reporting a problem

Open an issue from the bug report form with the smallest map that shows it (a few lines of YAML), the command or editor
action, and what you expected. For a wrong DBC, document or generated code, say which tool reads it
and what it shows.

Security problems are reported privately, not in an issue: see [SECURITY.md](SECURITY.md).

## Setting up

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12), and for the UI parts
Node.js 24. A C compiler (`gcc`, and `arm-none-eabi-gcc` if you have it) lets the tests compile the
generated C code; without one those tests are skipped.

```sh
uv sync                     # Python environment from uv.lock, with the lsp and desktop extras
uv run pre-commit install   # ruff before every commit, as in CI
uv run mapcan --help
```

Running the pieces:

| What | How |
|---|---|
| CLI | `uv run mapcan validate examples/vehicle-can.yaml` |
| Web editor, backend | `uv run mapcan serve examples/vehicle-can.yaml --no-browser` (API on :8765) |
| Web editor, UI with hot reload | `cd web && npm ci && npm run dev` (http://localhost:5173) |
| VS Code extension | `cd vscode && npm ci && npm run build`, open `vscode/` in VS Code, press F5 |

## Tests

Run the tests of what you changed; CI runs all of them on every push and pull request.

| Part | Command |
|---|---|
| Python: format, validation, exports, code generation, LSP, web API | `uv run pytest` |
| Lint | `uv run ruff check src tests` |
| Web UI: types, build, unit tests | `cd web && npm run build && npm test` |
| VS Code extension: types, integration tests in a real VS Code | `cd vscode && npm run typecheck && npm test` |

Some outputs are compared with reference files in `tests/golden`. After an intended change,
refresh them with `UPDATE_GOLDEN=1 uv run pytest` and check the diff before committing.

Generated files that are committed, and that CI checks are up to date:

- `schema/mapcan.schema.json`: `uv run mapcan schema -o schema/mapcan.schema.json` after changing
  [model.py](src/mapcan/model.py).
- `src/mapcan/web/static`: `npm run build` in `web/` after changing anything in `web/src`.

## Writing code

- **English** everywhere: code, comments, docstrings, docs, commit messages. Some older comments are
  still in Russian (#52); translate the ones you touch if you like.
- **Messages for users** go through `_("…")` in Python or `t("…")` in the web UI and need a Russian
  translation in [src/mapcan/locale/ru.py](src/mapcan/locale/ru.py) or
  [web/src/locale/ru.json](web/src/locale/ru.json); `tests/test_i18n.py` lists what is missing.
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

Maintainers release by bumping the version and pushing a tag; the steps are in the
[README](README.md#development) under "Releasing a version".
