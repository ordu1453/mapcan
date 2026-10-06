"""Проверка новой версии mapcan на GitHub Releases.

Результат кешируется на сутки в ``~/.mapcan/update.json``, чтобы не обращаться
к GitHub при каждом запуске. Проверку отключает переменная окружения
``MAPCAN_NO_UPDATE_CHECK=1``.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request

from . import __version__
from .userconfig import config_dir

REPO = "ordu1453/mapcan"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
CACHE_TTL = 24 * 3600


def parse_version(v: str) -> tuple[int, ...] | None:
    """«v1.2.3» / «1.2» → (1, 2, 3) / (1, 2, 0); пред-релизы и мусор → None."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", v.strip())
    return (int(m[1]), int(m[2]), int(m[3] or 0)) if m else None


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def disabled() -> bool:
    flag = os.environ.get("MAPCAN_NO_UPDATE_CHECK") or os.environ.get("CANMAP_NO_UPDATE_CHECK") or ""
    return flag.strip() not in ("", "0")


def _fetch(timeout: float) -> dict:
    req = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"mapcan/{__version__}",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — фиксированный https-адрес
        data = json.load(r)
    installer = next((a["browser_download_url"] for a in data.get("assets", [])
                      if a.get("name", "").endswith("-setup.exe")), None)
    return {"latest": str(data.get("tag_name", "")).lstrip("v"),
            "url": data.get("html_url") or RELEASES_URL,
            "installer": installer}


def check(timeout: float = 4.0, use_cache: bool = True) -> dict:
    """Сведения о последней версии: {current, latest, newer, url, installer}.

    Ошибки сети не пробрасываются: при недоступности GitHub ``newer`` = False.
    """
    result = {"current": __version__, "latest": None, "newer": False, "url": RELEASES_URL, "installer": None}
    if disabled():
        return result
    cache = config_dir() / "update.json"
    info = None
    if use_cache:
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if time.time() - float(cached.get("checked", 0)) < CACHE_TTL:
                info = cached
        except (OSError, ValueError, TypeError):
            pass
    if info is None:
        try:
            info = {**_fetch(timeout), "checked": time.time()}
        except Exception:  # noqa: BLE001 — нет сети, лимит API, неожиданный ответ
            return result
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(info), encoding="utf-8")
        except OSError:
            pass
    latest = info.get("latest") or None
    result.update(latest=latest, newer=bool(latest) and is_newer(latest),
                  url=info.get("url") or RELEASES_URL, installer=info.get("installer"))
    return result
