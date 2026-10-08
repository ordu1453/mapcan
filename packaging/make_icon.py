"""App icon (packaging/mapcan.ico): the same picture as the web editor's favicon.

The source is web/public/favicon.svg; each size is rasterized from it separately.

    uv run --with resvg-py python packaging/make_icon.py
"""

import io
from pathlib import Path

import resvg_py
from PIL import Image

HERE = Path(__file__).parent
SVG = HERE.parent / "web" / "public" / "favicon.svg"
OUT = HERE / "mapcan.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> Image.Image:
    png = resvg_py.svg_to_bytes(svg_path=str(SVG), width=size, height=size)
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


if __name__ == "__main__":
    images = [render(s) for s in reversed(SIZES)]
    images[0].save(OUT, sizes=[(s, s) for s in SIZES], append_images=images[1:])
    print(OUT)
