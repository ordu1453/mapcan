# Third-party notices

mapcan itself is licensed under the [Apache License 2.0](LICENSE). The Windows and Linux builds,
the Docker image and the VS Code extension bundle the third-party components below. Each is
distributed under its own license; the full texts ship with each package (`*.dist-info/licenses`
for Python packages, `LICENSE` in each npm package) and are available at the linked projects.

## Fonts

| Component | License |
|---|---|
| [PT Sans, PT Serif](https://www.paratype.com/public) — ParaType Ltd. | SIL Open Font License 1.1 ([OFL.txt](src/mapcan/fonts/OFL.txt), [OFL-PTSerif.txt](src/mapcan/fonts/OFL-PTSerif.txt)) |

## Runtime

| Component | License |
|---|---|
| [Python](https://www.python.org) (in the Windows and Linux builds) | PSF-2.0 |
| [PyInstaller](https://pyinstaller.org) bootloader (in the Windows and Linux builds) | GPL-2.0-or-later with the bootloader exception |
| [Typst](https://github.com/typst/typst) via [typst-py](https://github.com/messense/typst-py) | Apache-2.0 |

## Python packages

| Package | License |
|---|---|
| [annotated-doc](https://github.com/fastapi/annotated-doc) | MIT |
| [annotated-types](https://github.com/annotated-types/annotated-types) | MIT |
| [anyio](https://github.com/agronholm/anyio) | MIT |
| [argparse-addons](https://github.com/eerimoq/argparse_addons) | MIT |
| [bitstruct](https://github.com/eerimoq/bitstruct) | MIT |
| [cantools](https://github.com/cantools/cantools) | MIT |
| [click](https://github.com/pallets/click) | BSD-3-Clause |
| [colorama](https://github.com/tartley/colorama) | BSD-3-Clause |
| [crccheck](https://github.com/MartinScharrer/crccheck) | MIT |
| [et_xmlfile](https://foss.heptapod.net/openpyxl/et_xmlfile) | MIT |
| [fastapi](https://github.com/fastapi/fastapi) | MIT |
| [h11](https://github.com/python-hyper/h11) | MIT |
| [idna](https://github.com/kjd/idna) | BSD-3-Clause |
| [Jinja2](https://github.com/pallets/jinja) | BSD-3-Clause |
| [markdown-it-py](https://github.com/executablebooks/markdown-it-py) | MIT |
| [MarkupSafe](https://github.com/pallets/markupsafe) | BSD-3-Clause |
| [mdurl](https://github.com/executablebooks/mdurl) | MIT |
| [openpyxl](https://foss.heptapod.net/openpyxl/openpyxl) | MIT |
| [opentelemetry-api](https://github.com/open-telemetry/opentelemetry-python) | Apache-2.0 |
| [packaging](https://github.com/pypa/packaging) | Apache-2.0 OR BSD-2-Clause |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU |
| [pydantic](https://github.com/pydantic/pydantic), pydantic-core | MIT |
| [Pygments](https://pygments.org) | BSD-2-Clause |
| [python-can](https://github.com/hardbyte/python-can) | LGPL-3.0-only (see below) |
| [python-multipart](https://github.com/Kludex/python-multipart) | Apache-2.0 |
| [rich](https://github.com/Textualize/rich) | MIT |
| [ruamel.yaml](https://sourceforge.net/p/ruamel-yaml/) | MIT |
| [shellingham](https://github.com/sarugaku/shellingham) | ISC |
| [starlette](https://github.com/Kludex/starlette) | BSD-3-Clause |
| [textparser](https://github.com/cantools/textparser) | MIT |
| [typer](https://github.com/fastapi/typer) | MIT |
| [typing_extensions](https://github.com/python/typing_extensions) | PSF-2.0 |
| [typing-inspection](https://github.com/pydantic/typing-inspection) | MIT |
| [uvicorn](https://github.com/Kludex/uvicorn) | BSD-3-Clause |
| [websockets](https://github.com/python-websockets/websockets) | BSD-3-Clause |
| [wrapt](https://github.com/GrahamDumpleton/wrapt) | BSD-2-Clause |

Windows build only (desktop window):

| Package | License |
|---|---|
| [pywebview](https://github.com/r0x0r/pywebview) | BSD-3-Clause |
| [bottle](https://github.com/bottlepy/bottle) | MIT |
| [proxy_tools](https://github.com/jtushman/proxy_tools) | BSD |
| [pythonnet](https://github.com/pythonnet/pythonnet), [clr_loader](https://github.com/pythonnet/clr-loader) | MIT |
| [cffi](https://github.com/python-cffi/cffi) | MIT |
| [pycparser](https://github.com/eliben/pycparser) | BSD-3-Clause |

### python-can (LGPL-3.0)

python-can is a dependency of cantools and is included unmodified as separate Python modules. Its
source code is available at <https://github.com/hardbyte/python-can>. You may replace it with
another version: install mapcan from source (`uv tool install …`, see the README) or rebuild the
Windows/Linux package from this repository with the version of your choice.

## Web editor and VS Code extension

| Package | License |
|---|---|
| [Vue](https://github.com/vuejs/core) | MIT |
| [vscode-languageclient](https://github.com/microsoft/vscode-languageserver-node), vscode-jsonrpc, vscode-languageserver-protocol, vscode-languageserver-types | MIT |
| [minimatch](https://github.com/isaacs/minimatch) | BlueOak-1.0.0 |
| [semver](https://github.com/npm/node-semver) | ISC |
| [brace-expansion](https://github.com/juliangruber/brace-expansion), [balanced-match](https://github.com/juliangruber/balanced-match) | MIT |
