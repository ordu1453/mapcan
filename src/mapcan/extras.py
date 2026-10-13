"""Optional parts of mapcan (the extras of the package) and a clear message when one is not installed.

The core (validation, DBC/EDS/Markdown/HTML, code generation) has no heavy dependencies; the editor, PDF,
Excel, the language server and the app window come with ``pip install "mapcan[<extra>]"`` (``all``: every one).
"""

from __future__ import annotations

from importlib.util import find_spec

from .i18n import _

# extra → modules it installs
EXTRAS: dict[str, tuple[str, ...]] = {
    "web": ("fastapi", "uvicorn", "websockets", "multipart"),
    "pdf": ("typst",),
    "xlsx": ("openpyxl", "PIL"),
    "lsp": ("pygls",),
    "desktop": ("webview",),
}


class MissingExtra(RuntimeError):
    def __init__(self, extra: str):
        self.extra = extra
        super().__init__(_("This needs the optional part “{extra}” of mapcan: pip install \"mapcan[{extra}]\" "
                           "(or \"mapcan[all]\")", extra=extra))


def installed(extra: str) -> bool:
    return all(find_spec(m) is not None for m in EXTRAS[extra])


def require(*extras: str) -> None:
    """Raise :class:`MissingExtra` for the first extra that is not installed."""
    for extra in extras:
        if not installed(extra):
            raise MissingExtra(extra)
