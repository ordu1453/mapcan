"""media/icon.png (the extension's icon in the Marketplace and the list of extensions) from media/icon.svg.

    uv run --with resvg-py python vscode/scripts/make_icon.py
"""

from pathlib import Path

import resvg_py

MEDIA = Path(__file__).resolve().parent.parent / "media"

if __name__ == "__main__":
    png = resvg_py.svg_to_bytes(svg_path=str(MEDIA / "icon.svg"), width=256, height=256)
    (MEDIA / "icon.png").write_bytes(bytes(png))
    print(MEDIA / "icon.png")
