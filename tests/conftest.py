from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from canmap.loader import load
from canmap.validate import validate_text

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = Path(__file__).resolve().parent / "data" / "reference.yaml"
DATA = Path(__file__).resolve().parent / "data"
GOLDEN = Path(__file__).resolve().parent / "golden"


@pytest.fixture(scope="session")
def ref_map():
    res = load(REFERENCE)
    assert res.map is not None, [d.format() for d in res.report.diagnostics]
    return res.map


def one_bus(frames: str, protocol: str = "canopen", devices_extra: str = "", lint: str = "") -> str:
    """YAML-карта с одним устройством (node_id 0x10) и заданными кадрами."""
    frames = textwrap.indent(textwrap.dedent(frames).strip("\n"), " " * 10)
    return (
        "canmap: 1\n"
        "document:\n  title: Тест\n"
        + (lint or "")
        + "buses:\n"
        f"  - name: bus\n    protocol: {protocol}\n    devices:\n"
        "      - name: dev\n        node_id: 0x10\n        frames:\n"
        + frames + "\n"
        + (devices_extra or "")
    )


def run(yaml_text: str, disable=()):
    res, report = validate_text(yaml_text, "t.yaml", disable)
    return res, report


def codes(yaml_text: str) -> set[str]:
    return run(yaml_text)[1].codes()


@pytest.fixture(autouse=True)
def _isolated_user_config(tmp_path_factory, monkeypatch):
    """Профиль и недавние файлы — во временной папке, а не в ~/.canmap."""
    monkeypatch.setenv("CANMAP_CONFIG_DIR", str(tmp_path_factory.mktemp("canmap-config")))


@pytest.fixture(autouse=True)
def _russian_messages(monkeypatch):
    """Тесты сверяют исходные (русские) сообщения; английские проверяются в test_i18n."""
    from canmap import i18n

    monkeypatch.delenv("CANMAP_LANG", raising=False)
    monkeypatch.setattr(i18n, "_lang", "ru")
