"""Интерфейс на английском: полнота каталогов переводов, английские сообщения; язык документов."""

from __future__ import annotations

import ast
import json
import re
import shutil
import string

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mapcan.locale.en import EN
from mapcan.web.app import create_app
from mapcan.web.session import EditorSession

from .conftest import REFERENCE, ROOT, one_bus, run

SRC = ROOT / "src" / "mapcan"
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


def test_english_validation_messages():
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


def test_no_interface_language_choice(tmp_path):
    from mapcan.cli import app

    assert CliRunner().invoke(app, ["language", "ru"]).exit_code != 0
    p = tmp_path / "mapcan.yaml"
    shutil.copyfile(REFERENCE, p)
    with TestClient(create_app(EditorSession(p))) as c:
        meta = c.get("/api/meta").json()
        assert "language" not in meta
        assert meta["templates"]["empty"] == "Empty: just a bus"
        assert [e["title"] for e in meta["examples"]][:3] == ["Minimal", "SAE J1939", "Electric vehicle"]
        assert c.put("/api/language", json={"language": "ru"}).status_code in (404, 405)


def test_new_map_in_document_language():
    from mapcan.validate import validate_text
    from mapcan.web.newmap import TEMPLATES, new_map_text

    for lang in ("en", "ru"):
        for t in TEMPLATES:
            text = new_map_text(t, "", lang=lang)
            res, report = validate_text(text)
            assert res.map is not None and report.errors == 0, (lang, t, report.sorted())
            assert res.map.document.language == lang
    assert 'title: "New map"' in new_map_text("can", "")
    assert 'title: "Новая карта"' in new_map_text("can", "", lang="ru")


def test_export_language_choice(tmp_path):
    p = tmp_path / "mapcan.yaml"
    shutil.copyfile(REFERENCE, p)
    with TestClient(create_app(EditorSession(p))) as c:
        ru = c.get("/api/export/md?lang=ru").text
        en = c.get("/api/export/md?lang=en").text
        assert ru != en
        assert c.get("/api/export/md?lang=de").status_code == 400
        tpls = {t["name"]: t["lang"] for t in c.get("/api/templates").json()["pdf"]}
        assert tpls["mapcan"] is None
        assert all(tpls[n] == "ru" for n in ("gost-2.105", "gost-19", "gost-7.32"))


def test_gost_templates_always_russian():
    from mapcan.export.pdf import template_lang

    assert template_lang("gost-2.105") == "ru" and template_lang("gost-7.32") == "ru"
    assert template_lang("mapcan") is None and template_lang(None) is None
