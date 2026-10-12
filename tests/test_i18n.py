"""English interface: completeness of the translation catalogs, English messages; document language."""

from __future__ import annotations

import ast
import json
import re
import shutil
import string

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mapcan.locale.ru import RU
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


# t("…") / N_("…") with a literal: keys of the frontend
_T_CALL = re.compile(r"""\b(?:t|N_)\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")


def _frontend_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    for f in list(WEB.rglob("*.ts")) + list(WEB.rglob("*.vue")):
        for m in _T_CALL.finditer(f.read_text(encoding="utf-8")):
            raw = m.group(1) if m.group(1) is not None else m.group(2)
            keys.setdefault(json.loads('"' + raw.replace("\\'", "'") + '"'), str(f.relative_to(ROOT)))
    return keys


def _mostly_cyrillic(s: str) -> bool:
    """Russian text rather than English quoting Russian words (a Cyrillic «х», ESKD codes and abbreviations)."""
    return len(re.findall("[а-яё]", s)) > len(re.findall("[A-Za-z]", s))


def test_backend_catalog_complete():
    keys = _backend_keys()
    assert len(keys) > 200
    # Messages are written in English; Russian is a translation
    cyrillic = {k: v for k, v in keys.items() if _mostly_cyrillic(k)}
    assert not cyrillic, cyrillic
    missing = {k: v for k, v in keys.items() if k not in RU}
    assert not missing, missing
    bad = {k: RU[k] for k in keys if _fields(k) != _fields(RU[k])}
    assert not bad, bad


def test_backend_catalog_has_no_stale_entries():
    stale = set(RU) - set(_backend_keys())
    assert not stale, stale


def test_frontend_catalog_complete():
    ru = json.loads((WEB / "locale" / "ru.json").read_text(encoding="utf-8"))
    keys = _frontend_keys()
    assert len(keys) > 200
    cyrillic = {k: v for k, v in keys.items() if _mostly_cyrillic(k)}
    assert not cyrillic, cyrillic
    missing = {k: v for k, v in keys.items() if k not in ru}
    assert not missing, missing
    bad = {k: ru[k] for k in keys if _fields(k) != _fields(ru[k])}
    assert not bad, bad
    stale = set(ru) - set(keys)
    assert not stale, stale


def test_english_validation_messages():
    _, report = run(one_bus("""
        - name: f
          id: 0x100
          length: 1
          signals:
            - {name: a, encoding: raw, byte: 0, byte_length: 1}
            - {name: b, encoding: raw, byte: 0, byte_length: 1, description: x}
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
        # Any ISO 639-1 code; document labels for languages other than ru and en are English,
        # texts without a German translation are in the document language (Russian)
        de = c.get("/api/export/md?lang=de")
        assert de.status_code == 200 and de.text not in (ru, en)
        assert c.get("/api/export/md?lang=1x").status_code == 400
        tpls = {t["name"]: t["lang"] for t in c.get("/api/templates").json()["pdf"]}
        assert tpls["mapcan"] is None
        assert tpls["gost-2.105"] == "ru" and set(tpls) == {"mapcan", "gost-2.105"}


def test_gost_templates_always_russian():
    from mapcan.export.pdf import template_lang

    assert template_lang("gost-2.105") == "ru" and template_lang("gost-7.32") == "ru"
    assert template_lang("mapcan") is None and template_lang(None) is None


def test_any_iso_language():
    from mapcan.docmodel import ViewBuilder
    from mapcan.model import LocalizedText, text

    from .conftest import one_bus, run

    frame = """
        - name: f
          canopen: pdo_tx1
          length: 1
          title: {de: Zustand, en: State}
          signals:
            - {name: a, encoding: raw, description: x, byte: 0, byte_length: 1}
    """
    res, rep = run(one_bus(frame).replace("  language: ru", "  language: de"))
    assert res.map is not None and not rep.errors and res.map.document.language == "de"
    # No translation: the document language, then English, then any other
    assert text(LocalizedText(ru="Состояние", en="State"), "fr") == "State"
    assert text(LocalizedText(ru="Состояние", de="Zustand"), "fr") == "Состояние"
    assert text(LocalizedText(de="Zustand", en="State"), "de") == "Zustand"
    assert text(LocalizedText(de="Zustand", fr="État"), "en", "de") == "Zustand"
    assert text(LocalizedText(ru="Состояние", en="State", de="Zustand"), "fr", "de") == "Zustand"
    assert text(LocalizedText(de="Zustand", en="State"), "fr", "it") == "State"
    # A German map exported in English keeps the German original, not an arbitrary translation
    de_map = one_bus(frame.replace("{de: Zustand, en: State}", "{fr: État, de: Zustand}"))
    res, rep = run(de_map.replace("  language: ru", "  language: de"))
    assert res.map is not None and not rep.errors
    assert ViewBuilder(res.map, "en").t(res.map.buses[0].all_frames()[0].title) == "Zustand"
    # The translation key is only a language code
    res, _ = run(one_bus(frame.replace("de: Zustand", "deutsch: Zustand")))
    assert res.map is None
    res, _ = run(one_bus(frame).replace("  language: ru", "  language: german"))
    assert res.map is None
