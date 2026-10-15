"""Export from the editor: the document's text (also unsaved) → files, as ``mapcan build`` does."""

from __future__ import annotations

from pathlib import Path

from ..i18n import _
from ..loader import loads
from ..validate import check
from .analysis import Reader, part_of, read_disk

FORMATS = ("xlsx", "pdf", "md", "html", "dbc", "eds", "c", "py")


class ExportError(RuntimeError):
    pass


def map_text(text: str, filename: str, read: Reader) -> tuple[str, str]:
    """The map to export for a text: a file included by a map (``part_of``) gives that map, if it includes the
    file, as when the map is the active editor; otherwise the text itself. Returns (text, file name)."""
    of = part_of(text)
    if not of:
        return text, filename
    own, main = Path(filename).resolve(), (Path(filename).resolve().parent / of).resolve()
    main_text = read(str(main))
    if main_text is None:
        return text, filename
    included = loads(main_text, str(main)).source.includes
    return (main_text, str(main)) if any(Path(f).resolve() == own for _i, f in included) else (text, filename)


def export(text: str, filename: str, formats: list[str], out_dir: str | Path,
           read: Reader | None = None) -> tuple[list[Path], list[str], Path]:
    """Build the map's artifacts in ``out_dir`` (relative to the map's folder): (written files, export warnings,
    the map file). ``read`` gives the texts of the other files of the map (unsaved ones from the editor). For a
    file included by a map the whole map is exported."""
    unknown = sorted(set(formats) - set(FORMATS))
    if unknown:
        raise ExportError(_("unknown formats: {formats}", formats=", ".join(unknown)))
    own, own_text, disk = Path(filename).resolve(), text, read or read_disk

    def files(p: str) -> str | None:
        return own_text if Path(p).resolve() == own else disk(p)

    text, filename = map_text(text, filename, files)
    res = loads(text, filename, read=files)
    report = check(res)
    if res.map is None or report.errors:
        raise ExportError(_("Export canceled: the map has errors ({errors}). Fix them and try again.",
                            errors=report.errors))

    from ..codegen.c import generate_c
    from ..codegen.py import generate_py
    from ..export.dbc import export_dbc
    from ..export.eds import export_eds
    from ..export.pdf import PdfError, export_pdf
    from ..export.text import export_text
    from ..export.xlsx import export_xlsx

    m, stem, out = res.map, Path(filename).stem, Path(filename).resolve().parent / out_dir
    out.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    steps = {
        "xlsx": lambda: export_xlsx(m, out / f"{stem}.xlsx"),
        "pdf": lambda: export_pdf(m, out / f"{stem}.pdf"),
        "md": lambda: export_text(m, out / f"{stem}.md", "md"),
        "html": lambda: export_text(m, out / f"{stem}.html", "html"),
        "dbc": lambda: export_dbc(m, out / "dbc", warn=warnings.append),
        "eds": lambda: export_eds(m, out / "eds", warn=warnings.append),
        "c": lambda: generate_c(m, out / "c"),
        "py": lambda: generate_py(m, out / "py"),
    }
    written: list[Path] = []
    for f in formats:
        try:
            result = steps[f]()
        except PdfError as e:
            raise ExportError(str(e)) from e
        written.extend(result if isinstance(result, (list, tuple)) else [result])
    return [Path(p) for p in written], warnings, Path(filename)
