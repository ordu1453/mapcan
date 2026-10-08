# Build for Windows and Linux: dist/mapcan/ with mapcan-app.exe (window) and mapcan.exe (CLI);
# on Linux mapcan-app and mapcan; without pywebview the editor opens in the browser.
#
#   uv sync --locked --extra desktop --group package
#   uv run pyinstaller packaging/mapcan.spec --noconfirm
#
# onedir mode (not onefile): onefile unpacks itself into a temporary folder on every start,
# which slows the start down by several seconds.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = SPECPATH  # noqa: F821 — set by PyInstaller
ICON = f"{HERE}/mapcan.ico"

datas = collect_data_files("mapcan")               # templates, fonts, the built frontend
datas += [(f"{HERE}/../examples", "mapcan/examples")]   # "Examples" on the start screen
datas += [(f"{HERE}/../{name}", ".") for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")]
hidden = (collect_submodules("mapcan") + collect_submodules("uvicorn") + collect_submodules("cantools"))
excludes = ["tkinter", "matplotlib", "IPython", "pytest"]


def analysis(script):
    return Analysis(  # noqa: F821
        [f"{HERE}/{script}"], pathex=[f"{HERE}/../src"], datas=datas, hiddenimports=hidden,
        excludes=excludes, noarchive=False,
    )


app_a = analysis("entry_app.py")
cli_a = analysis("entry_cli.py")

app_exe = EXE(  # noqa: F821
    PYZ(app_a.pure), app_a.scripts, [], exclude_binaries=True, name="mapcan-app",  # noqa: F821
    console=False, icon=ICON,
)
cli_exe = EXE(  # noqa: F821
    PYZ(cli_a.pure), cli_a.scripts, [], exclude_binaries=True, name="mapcan",  # noqa: F821
    console=True, icon=ICON,
)

COLLECT(  # noqa: F821
    app_exe, app_a.binaries, app_a.datas,
    cli_exe, cli_a.binaries, cli_a.datas,
    name="mapcan",
)
