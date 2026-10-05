"""Язык интерфейса: полнота каталогов переводов, английские сообщения, переключение языка."""

from __future__ import annotations

import ast
import json
import re
import shutil
import string

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from canmap import i18n
from canmap.locale.en import EN
from canmap.userconfig import UserConfig
from canmap.web.app import create_app
from canmap.web.session import EditorSession

from .conftest import REFERENCE, ROOT, one_bus, run

SRC = ROOT / "src" / "canmap"
WEB = ROOT / "web" / "src"


def _fields(s: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(s) if f is not None}


def _backend_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    for f in SRC.rglob("*.py"):
        if "locale" in f.parts:
            continue
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("_", "N_")
                    and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                keys.setdefault(n.args[0].value, f"{f.relative_to(ROOT)}:{n.lineno}")
    return keys


# t("…") / N_("…") с литералом — ключи фронтенда
_T_CALL = re.compile(r"""\b(?:t|N_)\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")


def _frontend_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    for f in list(WEB.rglob("*.ts")) + list(WEB.rglob("*.vue")):
        for m in _T_CALL.finditer(f.read_text(encoding="utf-8")):
            raw = m.group(1) if m.group(1) is not None else m.group(2)
            keys.setdefault(json.loads('"' + raw.replace("\\'", "'") + '"'), str(f.relative_to(ROOT)))
    return keys


def test_backend_catalog_complete():
    keys = _backend_keys()
    assert len(keys) > 200
    missing = {k: v for k, v in keys.items() if k not in EN}
    assert not missing, missing
    bad = {k: EN[k] for k in keys if _fields(k) != _fields(EN[k])}
    assert not bad, bad


def test_backend_catalog_has_no_stale_entries():
    stale = set(EN) - set(_backend_keys())
    assert not stale, stale


def test_frontend_catalog_complete():
    en = json.loads((WEB / "locale" / "en.json").read_text(encoding="utf-8"))
    keys = _frontend_keys()
    assert len(keys) > 200
    missing = {k: v for k, v in keys.items() if k not in en}
    assert not missing, missing
    bad = {k: en[k] for k in keys if _fields(k) != _fields(en[k])}
    assert not bad, bad
    stale = set(en) - set(keys)
    assert not stale, stale


def test_english_validation_messages(monkeypatch):
    monkeypatch.setattr(i18n, "_lang", "en")
    _, report = run(one_bus("""
        - name: f
          id: 0x100
          dlc: 1
          signals:
            - {name: a, byte: 0}
            - {name: b, byte: 0, description: x}
    """))
    msgs = {d.code: d.message for d in report.diagnostics}
    assert msgs["bit-overlap"] == "signal 'b' overlaps 'a': bits 0..7 (byte 0)"
    assert msgs["missing-description"] == "signal 'a' has no description"
    cyr = re.compile("[А-Яа-яЁё]")
    assert not [m for m in msgs.values() if cyr.search(m.replace("Тест", ""))]


def test_language_resolution(monkeypatch):
    monkeypatch.setattr(i18n, "_lang", None)
    assert i18n.get_language() == "en"                    # по умолчанию
    cfg = UserConfig.load()
    cfg.language = "ru"
    cfg.save()
    monkeypatch.setattr(i18n, "_lang", None)
    assert i18n.get_language() == "ru"                    # из настроек
    monkeypatch.setenv("CANMAP_LANG", "en")
    monkeypatch.setattr(i18n, "_lang", None)
    assert i18n.get_language() == "en"                    # переменная окружения важнее


def test_api_language_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "_lang", "en")
    p = tmp_path / "canmap.yaml"
    shutil.copyfile(REFERENCE, p)
    with TestClient(create_app(EditorSession(p))) as c:
        meta = c.get("/api/meta").json()
        assert meta["language"] == "en" and meta["language_chosen"] is False
        assert meta["templates"]["empty"] == "Empty: just a bus"
        en_msgs = [d["message"] for d in c.get("/api/state").json()["diagnostics"]]

        meta = c.put("/api/language", json={"language": "ru"}).json()
        assert meta["language"] == "ru" and meta["language_chosen"] is True
        assert meta["templates"]["empty"] == "Пустая: только шина"
        ru_msgs = [d["message"] for d in c.get("/api/state").json()["diagnostics"]]
        assert en_msgs and en_msgs != ru_msgs
        assert UserConfig.load().language == "ru"

        assert c.put("/api/language", json={"language": "de"}).status_code == 400


def test_new_map_in_ui_language(monkeypatch):
    from canmap.validate import validate_text
    from canmap.web.newmap import TEMPLATES, new_map_text

    for lang in ("en", "ru"):
        monkeypatch.setattr(i18n, "_lang", lang)
        for t in TEMPLATES:
            text = new_map_text(t, "")
            res, report = validate_text(text)
            assert res.map is not None and report.errors == 0, (lang, t, report.sorted())
            assert res.map.document.language == lang
    monkeypatch.setattr(i18n, "_lang", "en")
    assert 'title: "New map"' in new_map_text("can", "")


def test_cli_language_command():
    from canmap.cli import app

    r = CliRunner().invoke(app, ["language", "ru"])
    assert r.exit_code == 0 and UserConfig.load().language == "ru"
    r = CliRunner().invoke(app, ["language", "xx"])
    assert r.exit_code != 0

