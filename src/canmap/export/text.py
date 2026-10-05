"""Экспорт в Markdown и HTML через Jinja2-шаблоны."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ..docmodel import build_view
from ..model import CanMap

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def _env(template_dir: Path, autoescape: bool) -> Environment:
    return Environment(
        loader=FileSystemLoader([str(template_dir), str(TEMPLATES)]),
        autoescape=select_autoescape(["html"]) if autoescape else False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
    )


def render(cmap: CanMap, kind: str, template: str | Path | None = None, lang: str | None = None) -> str:
    """kind: "md" или "html". ``template`` — свой Jinja2-шаблон."""
    default = {"md": "document.md.j2", "html": "document.html.j2"}[kind]
    if template:
        tpl = Path(template)
        env, name = _env(tpl.parent, kind == "html"), tpl.name
    else:
        env, name = _env(TEMPLATES, kind == "html"), default
    if kind == "html":
        env.autoescape = True
    out = env.get_template(name).render(**build_view(cmap, lang))
    if kind == "md":
        # Убрать лишние пустые строки, которые остаются от управляющих блоков.
        lines, blank = [], 0
        for line in out.splitlines():
            blank = blank + 1 if not line.strip() else 0
            if blank <= 1:
                lines.append(line.rstrip())
        out = "\n".join(lines).strip() + "\n"
    return out


def export_text(cmap: CanMap, out: str | Path, kind: str, template=None, lang=None) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(cmap, kind, template, lang), encoding="utf-8")
    return out
