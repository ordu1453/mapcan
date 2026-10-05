# Сборка Windows-версии: dist/canmap/ с canmap-app.exe (окно) и canmap.exe (CLI).
#
#   uv sync --locked --extra desktop --group package
#   uv run pyinstaller packaging/canmap.spec --noconfirm
#
# Режим onedir (не onefile): onefile при каждом запуске распаковывается во временную
# папку, и старт замедляется на несколько секунд.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = SPECPATH  # noqa: F821 — задаётся PyInstaller
ICON = f"{HERE}/canmap.ico"

datas = collect_data_files("canmap")               # шаблоны, шрифты, собранный фронтенд
hidden = (collect_submodules("canmap") + collect_submodules("uvicorn") + collect_submodules("cantools"))
excludes = ["tkinter", "matplotlib", "IPython", "pytest"]


def analysis(script):
    return Analysis(  # noqa: F821
        [f"{HERE}/{script}"], pathex=[f"{HERE}/../src"], datas=datas, hiddenimports=hidden,
        excludes=excludes, noarchive=False,
    )


app_a = analysis("entry_app.py")
cli_a = analysis("entry_cli.py")

app_exe = EXE(  # noqa: F821
    PYZ(app_a.pure), app_a.scripts, [], exclude_binaries=True, name="canmap-app",  # noqa: F821
    console=False, icon=ICON,
)
cli_exe = EXE(  # noqa: F821
    PYZ(cli_a.pure), cli_a.scripts, [], exclude_binaries=True, name="canmap",  # noqa: F821
    console=True, icon=ICON,
)

COLLECT(  # noqa: F821
    app_exe, app_a.binaries, app_a.datas,
    cli_exe, cli_a.binaries, cli_a.datas,
    name="canmap",
)
