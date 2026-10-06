"""Готовые примеры карт для стартового экрана («Примеры» → копия в выбранную папку)."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from ..i18n import _

_PACKAGE_DIR = Path(__file__).resolve().parent.parent


def examples_dir() -> Path:
    """Папка примеров: внутри пакета (wheel, mapcan.exe) или в корне репозитория (разработка)."""
    bundled = _PACKAGE_DIR / "examples"
    return bundled if bundled.is_dir() else _PACKAGE_DIR.parent.parent / "examples"


def _title(path: Path) -> str:
    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
        title = data["document"]["title"]
    except Exception:  # noqa: BLE001 — битый пример не должен ломать стартовый экран
        return path.stem
    if isinstance(title, dict):         # локализованный текст {ru: …, en: …}
        title = next(iter(title.values()), path.stem)
    return str(title)


def list_examples() -> list[dict[str, str]]:
    d = examples_dir()
    if not d.is_dir():
        return []
    return [{"name": p.stem, "title": _title(p)} for p in sorted(d.glob("*.yaml"))]


def example_text(name: str) -> str:
    """Текст примера для копии; ссылка на схему убрана — относительный путь в копии будет битым."""
    path = examples_dir() / f"{name}.yaml"
    if "/" in name or "\\" in name or not path.is_file():
        raise ValueError(_("неизвестный пример: {name}", name=name))
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if lines and lines[0].startswith("# yaml-language-server:"):
        lines = lines[1:]
        if lines and lines[0].strip() == "#":
            lines = lines[1:]
    return "".join(lines)
