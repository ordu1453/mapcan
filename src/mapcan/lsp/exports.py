"""Экспорт из редактора: текст документа (в том числе несохранённый) → файлы, как ``mapcan build``."""

from __future__ import annotations

from pathlib import Path

from ..i18n import _
from ..loader import loads
from ..validate import check

FORMATS = ("xlsx", "pdf", "md", "html", "dbc", "eds", "c", "py")


class ExportError(RuntimeError):
    pass


def export(text: str, filename: str, formats: list[str], out_dir: str | Path) -> tuple[list[Path], list[str]]:
    """Собрать артефакты карты в ``out_dir``: (записанные файлы, предупреждения экспорта)."""
    unknown = sorted(set(formats) - set(FORMATS))
    if unknown:
        raise ExportError(_("неизвестные форматы: {formats}", formats=", ".join(unknown)))
    res = loads(text, filename)
    report = check(res)
    if res.map is None or report.errors:
        raise ExportError(_("Экспорт отменён: в карте есть ошибки ({errors}). Исправьте их и повторите.",
                            errors=report.errors))

    from ..codegen.c import generate_c
    from ..codegen.py import generate_py
    from ..export.dbc import export_dbc
    from ..export.eds import export_eds
    from ..export.pdf import PdfError, export_pdf
    from ..export.text import export_text
    from ..export.xlsx import export_xlsx

    m, stem, out = res.map, Path(filename).stem, Path(out_dir)
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
    return [Path(p) for p in written], warnings
