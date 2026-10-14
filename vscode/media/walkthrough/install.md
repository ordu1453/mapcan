# Install mapcan

The extension runs the language server of the `mapcan` command-line tool. Install it once:

```sh
uv tool install "mapcan[lsp]"
```

or `pipx install "mapcan[lsp]"`. In a project with its own Python environment (venv), install it there:
the extension finds `mapcan` in the environment selected in the Python extension, then on `PATH`.
