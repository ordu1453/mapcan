"""Markdown and HTML export through Jinja2 templates."""

from __future__ import annotations

import base64
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from ..docmodel import build_view
from ..model import MapCan

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def _env(template_dir: Path, autoescape: bool) -> Environment:
    return Environment(
        loader=FileSystemLoader([str(template_dir), str(TEMPLATES)]),
        autoescape=select_autoescape(["html"]) if autoescape else False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
    )


_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
         ".svg": "image/svg+xml", ".webp": "image/webp"}


def logo_data_uri(path: str) -> str:
    """The logo as a data: URI, so the HTML stays one self-contained file."""
    if not path:
        return ""
    p = Path(path)
    mime = _MIME.get(p.suffix.lower())
    if not mime or not p.is_file():
        return ""
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def render(cmap: MapCan, kind: str, template: str | Path | None = None, lang: str | None = None) -> str:
    """kind: "md" or "html". ``template`` is your own Jinja2 template."""
    default = {"md": "document.md.j2", "html": "document.html.j2"}[kind]
    if template:
        tpl = Path(template)
        env, name = _env(tpl.parent, kind == "html"), tpl.name
    else:
        env, name = _env(TEMPLATES, kind == "html"), default
    if kind == "html":
        env.autoescape = True
    view = build_view(cmap, lang)
    if kind == "html":
        view["document"]["logo"] = logo_data_uri(view["document"]["logo_file"])
    out = env.get_template(name).render(**view)
    if kind == "md":
        # Remove the extra empty lines left by the control blocks.
        lines, blank = [], 0
        for line in out.splitlines():
            blank = blank + 1 if not line.strip() else 0
            if blank <= 1:
                lines.append(line.rstrip())
        out = "\n".join(lines).strip() + "\n"
    return out


def export_text(cmap: MapCan, out: str | Path, kind: str, template=None, lang=None) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(cmap, kind, template, lang), encoding="utf-8")
    return out
