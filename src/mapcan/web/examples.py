"""Ready example maps for the start screen ("Examples" → a copy in the chosen folder)."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from ..i18n import N_, _
from ..schema import schema_line

_PACKAGE_DIR = Path(__file__).resolve().parent.parent

# Labels on the start screen (in the interface language); an example without a label is shown by its file name.
EXAMPLES = {
    "minimal": N_("Minimal"),
    "j1939": N_("SAE J1939"),
    "vehicle-can": N_("Electric vehicle"),
    "canopen-node": N_("CANopen drive"),
    "tractor": N_("Tractor: a map in several files"),
}


def examples_dir() -> Path:
    """Folder of the examples: inside the package (wheel, mapcan.exe) or at the repository root (development)."""
    bundled = _PACKAGE_DIR / "examples"
    return bundled if bundled.is_dir() else _PACKAGE_DIR.parent.parent / "examples"


def _example_path(name: str) -> Path | None:
    """File of an example: ``name.yaml`` or, for an example of several files, ``name/name.yaml``."""
    if "/" in name or "\\" in name or name in ("", ".", ".."):
        return None
    d = examples_dir()
    for path in (d / f"{name}.yaml", d / name / f"{name}.yaml"):
        if path.is_file():
            return path
    return None


def list_examples() -> list[dict[str, str]]:
    d = examples_dir()
    if not d.is_dir():
        return []
    order = list(EXAMPLES)
    found = [p.stem for p in d.glob("*.yaml")] + [p.name for p in d.iterdir() if (p / f"{p.name}.yaml").is_file()]
    names = sorted(found, key=lambda n: (order.index(n) if n in order else len(order), n))
    return [{"name": n, "title": _(EXAMPLES[n]) if n in EXAMPLES else n} for n in names]


def example_text(name: str) -> str:
    """Text of an example for a copy: its link to the schema, a relative path that would break in the copy, is the
    published schema's."""
    path = _example_path(name)
    if path is None:
        raise ValueError(_("unknown example: {name}", name=name))
    return _published_schema(path.read_text(encoding="utf-8"))


def _published_schema(text: str, part: bool = False) -> str:
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith("# yaml-language-server:"):
        lines[0] = schema_line(part) + "\n"
    return "".join(lines)


def example_includes(name: str, map_file: str | None = None) -> dict[str, str]:
    """Files the example includes (``include``): path relative to the map → text.

    They are copied next to the copy of the map, otherwise its included files would not be found; their
    ``part_of`` names the copy of the map (``map_file``, its file name)."""
    from ruamel.yaml import YAML

    path = _example_path(name)
    if path is None:
        raise ValueError(_("unknown example: {name}", name=name))
    data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    files = data.get("include") if isinstance(data, dict) else None
    out = {}
    for f in files or []:
        if not isinstance(f, str):
            continue
        text = _published_schema((path.parent / f).read_text(encoding="utf-8"), part=True)
        if map_file:
            target = posixpath.relpath(map_file, posixpath.dirname(f) or ".")
            text = re.sub(r"(?m)^part_of\s*:.*$", lambda _m, t=target: f"part_of: {t}", text, count=1)
        out[f] = text
    return out
