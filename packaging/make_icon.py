"""Иконка приложения (packaging/canmap.ico) — тот же рисунок, что favicon веб-редактора.

    uv run python packaging/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

BG = (31, 78, 121, 255)          # #1f4e79
SIZE = 256
OUT = Path(__file__).with_name("canmap.ico")


def draw(size: int = SIZE) -> Image.Image:
    k = size / 16                                   # favicon нарисован на сетке 16×16
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=round(3 * k), fill=BG)
    w = max(1, round(1.6 * k))
    for y, x2 in ((4, 13), (8, 9), (12, 11)):
        d.line((3 * k, y * k, x2 * k, y * k), fill="white", width=w)
    return img


if __name__ == "__main__":
    draw().save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(OUT)
