"""Готовые примеры карт для стартового экрана («Примеры» → копия в выбранную папку)."""

from __future__ import annotations

from pathlib import Path

from ..i18n import N_, _

_PACKAGE_DIR = Path(__file__).resolve().parent.parent

# Подписи на стартовом экране (на языке интерфейса); пример без подписи показывается по имени файла.
EXAMPLES = {
    "minimal": N_("Minimal"),
    "j1939": N_("SAE J1939"),
    "vehicle-can": N_("Electric vehicle"),
    "canopen-node": N_("CANopen drive"),
    "tractor": N_("Tractor: a map in several files"),
}


def examples_dir() -> Path:
    """Папка примеров: внутри пакета (wheel, mapcan.exe) или в корне репозитория (разработка)."""
    bundled = _PACKAGE_DIR / "examples"
    return bundled if bundled.is_dir() else _PACKAGE_DIR.parent.parent / "examples"


def _example_path(name: str) -> Path | None:
    """Файл примера: ``name.yaml`` или, у примера из нескольких файлов, ``name/name.yaml``."""
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
    """Текст примера для копии; ссылка на схему убрана — относительный путь в копии будет битым."""
    path = _example_path(name)
    if path is None:
        raise ValueError(_("unknown example: {name}", name=name))
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if lines and lines[0].startswith("# yaml-language-server:"):
        lines = lines[1:]
        if lines and lines[0].strip() == "#":
            lines = lines[1:]
    return "".join(lines)


def example_includes(name: str) -> dict[str, str]:
    """Файлы, которые подключает пример (``include``): путь относительно карты → текст.

    Копируются рядом с копией карты, иначе у неё не нашлось бы подключённых файлов."""
    from ruamel.yaml import YAML

    path = _example_path(name)
    if path is None:
        raise ValueError(_("unknown example: {name}", name=name))
    data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    files = data.get("include") if isinstance(data, dict) else None
    return {f: (path.parent / f).read_text(encoding="utf-8") for f in files or [] if isinstance(f, str)}
