"""Экспорт в PDF через Typst (pip-пакет ``typst`` со встроенным компилятором)."""

from __future__ import annotations

import json
from pathlib import Path

from ..docmodel import build_view
from ..model import CanMap

PKG_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = PKG_DIR / "templates" / "document.typ"
FONTS_DIR = PKG_DIR / "fonts"


class PdfError(RuntimeError):
    pass


def view_json(cmap: CanMap, lang: str | None = None) -> str:
    return json.dumps(build_view(cmap, lang), ensure_ascii=False)


def export_pdf(
    cmap: CanMap,
    out: str | Path,
    template: str | Path | None = None,
    font_paths: list[str | Path] = (),
    lang: str | None = None,
    fmt: str = "pdf",
) -> Path:
    """Собрать PDF. ``template`` — свой .typ-шаблон (данные в ``sys.inputs.data``)."""
    import typst

    tpl = Path(template) if template else DEFAULT_TEMPLATE
    if not tpl.is_file():
        raise PdfError(f"шаблон не найден: {tpl}")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fonts = [str(FONTS_DIR)] + [str(p) for p in font_paths]
    try:
        result = typst.compile(
            str(tpl),
            root=str(tpl.parent),
            font_paths=fonts,
            ignore_system_fonts=True,   # одинаковый результат на Windows и Linux
            sys_inputs={"data": view_json(cmap, lang)},
            format=fmt,
        )
    except typst.TypstError as e:
        raise PdfError(f"ошибка компиляции Typst: {e}") from e
    if isinstance(result, list):     # svg/png: по файлу на страницу
        stem, suffix = out.stem, out.suffix
        for i, page in enumerate(result, 1):
            out.with_name(f"{stem}-{i}{suffix}").write_bytes(page)
    else:
        out.write_bytes(result)
    return out
