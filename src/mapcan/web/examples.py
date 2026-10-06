"""Готовые примеры карт для стартового экрана («Примеры» → копия в выбранную папку)."""

from __future__ import annotations

from pathlib import Path

from ..i18n import N_, _

_PACKAGE_DIR = Path(__file__).resolve().parent.parent

# Подписи на стартовом экране (на языке интерфейса); пример без подписи показывается по имени файла.
EXAMPLES = {
    "minimal": N_("Минимальный"),
    "j1939": N_("SAE J1939"),
    "vehicle-can": N_("Электромобиль"),
}


def examples_dir() -> Path:
    """Папка примеров: внутри пакета (wheel, mapcan.exe) или в корне репозитория (разработка)."""
    bundled = _PACKAGE_DIR / "examples"
    return bundled if bundled.is_dir() else _PACKAGE_DIR.parent.parent / "examples"


def list_examples() -> list[dict[str, str]]:
    d = examples_dir()
    if not d.is_dir():
        return []
    order = list(EXAMPLES)
    names = sorted((p.stem for p in d.glob("*.yaml")), key=lambda n: (order.index(n) if n in order else len(order), n))
    return [{"name": n, "title": _(EXAMPLES[n]) if n in EXAMPLES else n} for n in names]


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
