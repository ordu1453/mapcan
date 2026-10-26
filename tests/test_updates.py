"""Check for a new version: what test_launcher.py does not cover (parsing, an old or broken cache, the request)."""

from __future__ import annotations

import io
import json
import time

import pytest

from mapcan import __version__, updates
from mapcan.userconfig import config_dir


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.delenv("MAPCAN_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("CANMAP_NO_UPDATE_CHECK", raising=False)


def _cache() -> dict:
    return json.loads((config_dir() / "update.json").read_text(encoding="utf-8"))


def test_parse_version():
    assert updates.parse_version("v1.2.3") == (1, 2, 3)
    assert updates.parse_version(" 1.2 ") == (1, 2, 0)
    assert updates.parse_version("1.2.3-rc1") is None
    assert updates.parse_version("latest") is None


def test_is_newer_compares_numbers():
    assert updates.is_newer("1.10.0", "1.9.9")
    assert not updates.is_newer("1.2.0", "1.2")
    assert not updates.is_newer("2.0.0", "dev")


def test_disabled(monkeypatch):
    assert not updates.disabled()
    monkeypatch.setenv("MAPCAN_NO_UPDATE_CHECK", "0")
    assert not updates.disabled()
    # The former name of the variable still turns the check off
    monkeypatch.setenv("CANMAP_NO_UPDATE_CHECK", "1")
    monkeypatch.setenv("MAPCAN_NO_UPDATE_CHECK", "")
    assert updates.disabled()


def test_check_writes_the_cache_and_can_skip_it(monkeypatch):
    calls = []

    def fetch(timeout):
        calls.append(timeout)
        return {"latest": "999.0.0", "url": "https://example.org/r", "installer": None}

    monkeypatch.setattr(updates, "_fetch", fetch)
    updates.check(timeout=1.5)
    assert calls == [1.5] and _cache()["latest"] == "999.0.0" and _cache()["checked"] <= time.time()
    updates.check(use_cache=False)
    assert len(calls) == 2


def test_check_expired_or_broken_cache(monkeypatch):
    cache = config_dir() / "update.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(updates, "_fetch", lambda timeout: {"latest": "0.0.1", "url": "", "installer": None})
    for content in (json.dumps({"latest": "999.0.0", "checked": time.time() - updates.CACHE_TTL - 1}),
                    "{not json", json.dumps({"latest": "999.0.0", "checked": "yesterday"})):
        cache.write_text(content, encoding="utf-8")
        r = updates.check()
        # An old version is not newer, and an empty URL falls back to the releases page
        assert (r["latest"], r["newer"], r["url"]) == ("0.0.1", False, updates.RELEASES_URL)


def test_network_error_is_not_cached(monkeypatch):
    def fetch(timeout):
        raise OSError("no network")

    monkeypatch.setattr(updates, "_fetch", fetch)
    assert updates.check()["latest"] is None
    assert not (config_dir() / "update.json").exists()


def test_check_unwritable_cache(monkeypatch):
    monkeypatch.setattr(updates, "_fetch", lambda timeout: {"latest": "", "url": None, "installer": None})
    monkeypatch.setattr(updates, "config_dir", lambda: config_dir() / "update.json" / "x")
    (config_dir() / "update.json").parent.mkdir(parents=True, exist_ok=True)
    (config_dir() / "update.json").write_text("{}", encoding="utf-8")
    # The cache cannot be written (its folder is a file): the answer is still given; an empty tag is no version
    assert updates.check() == {"current": __version__, "latest": None, "newer": False,
                               "url": updates.RELEASES_URL, "installer": None}


def test_fetch(monkeypatch):
    seen = {}

    def urlopen(req, timeout):
        seen.update(url=req.full_url, agent=req.get_header("User-agent"), timeout=timeout)
        return io.BytesIO(json.dumps({
            "tag_name": "v1.4.0", "html_url": "https://github.com/x/releases/tag/v1.4.0",
            "assets": [{"name": "mapcan-1.4.0.tar.gz", "browser_download_url": "https://a/tgz"},
                       {"name": "mapcan-1.4.0-setup.exe", "browser_download_url": "https://a/setup"}],
        }).encode())

    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    assert updates._fetch(2.0) == {"latest": "1.4.0", "url": "https://github.com/x/releases/tag/v1.4.0",
                                   "installer": "https://a/setup"}
    assert seen == {"url": updates.API_URL, "agent": f"mapcan/{__version__}", "timeout": 2.0}

    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda req, timeout: io.BytesIO(b"{}"))
    assert updates._fetch(2.0) == {"latest": "", "url": updates.RELEASES_URL, "installer": None}
