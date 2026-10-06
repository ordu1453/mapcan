"""Логотип для README (docs/logo-light.svg, docs/logo-dark.svg) — как BrandMark.vue на стартовом экране.

Иконка — web/public/favicon.svg, надпись «mapcan» — контуры букв Sora ExtraBold из шрифта
веб-редактора (GitHub не подгружает шрифты в SVG). Пропорции и цвета — из .brandmark в style.css.

    uv run --with fonttools --with brotli python packaging/make_logo.py
"""

import re
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).parent.parent
ICON = ROOT / "web" / "public" / "favicon.svg"
FONT = ROOT / "web" / "src" / "assets" / "sora-800-wordmark.woff2"
OUT = ROOT / "docs"

EM = 100                    # font-size надписи
ICON_SIZE = 1.45 * EM       # .brandmark-icon: 1.45em
GAP = 0.4 * EM              # .brandmark: gap 0.4em
TRACKING = -0.01 * EM       # .brandmark-word: letter-spacing -0.01em
THEMES = {                  # --brand-map, --brand-can
    "light": ("#1e40af", "#d97706"),
    "dark": ("#ffffff", "#fbbf24"),
}


def word_paths(font: TTFont, text: str, x: float, baseline: float) -> tuple[list[str], float]:
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = EM / font["head"].unitsPerEm
    paths = []
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        paths.append(pen.getCommands())
        x += glyphs[name].width * scale + TRACKING
    return paths, x - TRACKING


def main() -> None:
    font = TTFont(FONT)
    hhea = font["hhea"]
    upm = font["head"].unitsPerEm
    # Строка высотой 1em (line-height: 1) по центру иконки; базовая линия — как у браузера.
    content = (hhea.ascent - hhea.descent) / upm * EM
    baseline = (ICON_SIZE - EM) / 2 + (EM - content) / 2 + hhea.ascent / upm * EM
    x0 = ICON_SIZE + GAP
    map_paths, x = word_paths(font, "map", x0, baseline)
    can_paths, width = word_paths(font, "can", x, baseline)

    icon = ICON.read_text(encoding="utf-8")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", icon, re.S).group(1).strip()
    for theme, (map_color, can_color) in THEMES.items():
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {ICON_SIZE:.1f}" '
            f'width="{width:.0f}" height="{ICON_SIZE:.0f}">\n'
            f'<title>mapcan</title>\n'
            f'<svg width="{ICON_SIZE:.1f}" height="{ICON_SIZE:.1f}" viewBox="0 0 32 32">\n{inner}\n</svg>\n'
            f'<path fill="{map_color}" d="{"".join(map_paths)}"/>\n'
            f'<path fill="{can_color}" d="{"".join(can_paths)}"/>\n'
            "</svg>\n"
        )
        out = OUT / f"logo-{theme}.svg"
        out.write_text(svg, encoding="utf-8", newline="\n")
        print(out)


if __name__ == "__main__":
    main()
