"""Пользовательские настройки mapcan: профиль автора и недавние файлы.

Хранятся в ``~/.mapcan/config.json`` (каталог можно переопределить переменной
окружения ``MAPCAN_CONFIG_DIR``). Файл общий для CLI и веб-редактора. Каталог прежнего
названия ``~/.canmap`` при первом обращении переименовывается в ``~/.mapcan``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .i18n import _

RECENT_LIMIT = 12
_GITHUB_USER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_GITHUB_URL = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([^/?#\s]+)/?$", re.IGNORECASE)


def config_dir() -> Path:
    env = os.environ.get("MAPCAN_CONFIG_DIR") or os.environ.get("CANMAP_CONFIG_DIR")
    if env:
        return Path(env)
    d = Path.home() / ".mapcan"
    legacy = Path.home() / ".canmap"
    if not d.exists() and legacy.is_dir():
        try:
            legacy.rename(d)
        except OSError:
            return legacy
    return d


def normalize_github(value: str | None) -> str | None:
    """Имя пользователя GitHub из «user», «@user» или ссылки https://github.com/user."""
    if not value:
        return None
    v = value.strip().lstrip("@")
    m = _GITHUB_URL.match(v)
    if m:
        v = m.group(1)
    if not _GITHUB_USER.match(v):
        raise ValueError(_("«{value}» — не имя пользователя GitHub", value=value))
    return v


def github_url(user: str | None) -> str | None:
    return f"https://github.com/{user}" if user else None


@dataclass
class UserProfile:
    name: str = ""
    github: str | None = None

    @property
    def complete(self) -> bool:
        return bool(self.name.strip())

    def to_dict(self) -> dict:
        return {**asdict(self), "github_url": github_url(self.github)}


@dataclass
class UserConfig:
    user: UserProfile = field(default_factory=UserProfile)
    recent: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> UserConfig:
        path = config_dir() / "config.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        u = data.get("user") or {}
        try:
            gh = normalize_github(u.get("github"))
        except ValueError:
            gh = None
        recent = [str(p) for p in data.get("recent", []) if isinstance(p, str)]
        return cls(UserProfile(str(u.get("name", "")), gh), recent[:RECENT_LIMIT])

    def save(self) -> None:
        d = config_dir()
        d.mkdir(parents=True, exist_ok=True)
        data = {"user": asdict(self.user), "recent": self.recent[:RECENT_LIMIT]}
        tmp = d / "config.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(d / "config.json")

    def touch_recent(self, path: str | Path) -> None:
        p = str(Path(path).resolve())
        self.recent = [p] + [r for r in self.recent if os.path.normcase(r) != os.path.normcase(p)]
        del self.recent[RECENT_LIMIT:]
