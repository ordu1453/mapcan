"""PDF export through Typst (the ``typst`` pip package with the compiler built in).

Templates: built-in (by name, see :data:`PDF_TEMPLATES`) or your own ``.typ`` file.
The map's data is passed to the template as JSON in ``sys.inputs.data``.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..docmodel import build_view
from ..i18n import N_, _
from ..model import MapCan

PKG_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PKG_DIR / "templates" / "pdf"
FONTS_DIR = PKG_DIR / "fonts"


@dataclass(frozen=True)
class PdfTemplate:
    name: str
    title: str
    description: str
    lang: str | None = None          # the document language is fixed (GOST templates: Russian only)

    @property
    def path(self) -> Path:
        return TEMPLATES_DIR / f"{self.name}.typ"


PDF_TEMPLATES: dict[str, PdfTemplate] = {
    t.name: t
    for t in [
        PdfTemplate("mapcan", N_("mapcan — Standard layout"),
                    N_("Colored bit diagrams, headers and footers, free-form title page.")),
        PdfTemplate("gost-2.105", N_("ESKD — GOST 2.105 / 2.104"),
                    N_("Design text document: frame, title block (forms 2 and 2a), additional columns, title page, "
                       "change log sheet."), "ru"),
    ]
}
# Draft templates: their files and code are kept, but users (CLI, editor) are not offered them
# until they are finished. They can be built only by the path to the .typ (see the tests).
DRAFT_PDF_TEMPLATES: dict[str, PdfTemplate] = {
    t.name: t
    for t in [
        PdfTemplate("gost-19", N_("ESPD — GOST 19.104 / 19.106"),
                    N_("Software document: approval sheet, title page, abstract, designation on every page, change log "
                       "sheet."), "ru"),
        PdfTemplate("gost-7.32", N_("Report — GOST 7.32-2017"),
                    N_("Report: title page, list of contributors, abstract, contents, numbered tables, "
                       "appendix."), "ru"),
    ]
}
DEFAULT_TEMPLATE_NAME = "mapcan"
# Former names of the built-in templates (before canmap was renamed to mapcan).
PDF_TEMPLATE_ALIASES = {"canmap": "mapcan"}


class PdfError(RuntimeError):
    pass


def template_lang(template: str | Path | None) -> str | None:
    """Language fixed by a built-in template (GOST: Russian), or None."""
    name = PDF_TEMPLATE_ALIASES.get(str(template or DEFAULT_TEMPLATE_NAME), str(template or DEFAULT_TEMPLATE_NAME))
    t = PDF_TEMPLATES.get(name) or DRAFT_PDF_TEMPLATES.get(name)
    return t.lang if t else None


def resolve_template(template: str | Path | None) -> Path:
    """Name of a built-in template, path to a .typ or None (the default template)."""
    if template is None or str(template) == "":
        return PDF_TEMPLATES[DEFAULT_TEMPLATE_NAME].path
    name = PDF_TEMPLATE_ALIASES.get(str(template), str(template))
    if name in PDF_TEMPLATES:
        return PDF_TEMPLATES[name].path
    p = Path(template)
    if p.is_file():
        return p
    known = ", ".join(PDF_TEMPLATES)
    raise PdfError(_("template not found: {template} (built-in: {known})", template=template, known=known))


def view_json(cmap: MapCan, lang: str | None = None, logo: str = "") -> str:
    view = build_view(cmap, lang)
    view["document"]["logo"] = logo
    return json.dumps(view, ensure_ascii=False)


def export_pdf(
    cmap: MapCan,
    out: str | Path,
    template: str | Path | None = None,
    font_paths: list[str | Path] = (),
    lang: str | None = None,
    fmt: str = "pdf",
) -> Path:
    """Build a PDF. ``template`` is the name of a built-in template or the path to your own ``.typ``.

    GOST templates are always built in Russian: ``lang`` does not apply to them.
    """
    import typst

    tpl = resolve_template(template)
    lang = template_lang(template) or lang
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fonts = [str(FONTS_DIR)] + [str(p) for p in font_paths]

    # Typst reads files only inside its root. The build runs in a temporary folder with a copy of the
    # template's files (lib.typ etc.) and the logo, so the logo can be anywhere on the disk.
    with tempfile.TemporaryDirectory(prefix="mapcan-pdf-") as tmp:
        root = Path(tmp)
        for f in tpl.parent.iterdir():
            if f.is_file() and f.suffix.lower() in (".typ", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"):
                shutil.copy2(f, root / f.name)
        logo = ""
        src = cmap.logo_path
        if src is not None and src.is_file():
            dst = root / f"__logo__{src.suffix.lower()}"
            shutil.copy2(src, dst)
            logo = "/" + dst.name
        try:
            result = typst.compile(
                str(root / tpl.name),
                root=str(root),
                font_paths=fonts,
                sys_inputs={"data": view_json(cmap, lang, logo)},
                format=fmt,
            )
        except typst.TypstError as e:
            raise PdfError(_("Typst compilation error ({name}): {error}", name=tpl.name, error=e)) from e
    if isinstance(result, list):     # svg/png: a file per page
        stem, suffix = out.stem, out.suffix
        for i, page in enumerate(result, 1):
            out.with_name(f"{stem}-{i}{suffix}").write_bytes(page)
    else:
        out.write_bytes(result)
    return out
