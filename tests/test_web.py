"""Бэкенд веб-редактора: операции, сохранение комментариев, undo/redo, экспорт, diff."""

from __future__ import annotations

import difflib
import io
import shutil
import subprocess
import zipfile

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mapcan.web.app import create_app
from mapcan.web.session import EditorSession

from .conftest import REFERENCE

SIG = ["buses", 0, "devices", 0, "frames", 1, "signals", 4]       # imd_data.bus_voltage


@pytest.fixture
def mapfile(tmp_path):
    p = tmp_path / "mapcan.yaml"
    shutil.copyfile(REFERENCE, p)
    return p


@pytest.fixture
def client(mapfile):
    with TestClient(create_app(EditorSession(mapfile), poll_interval=0.05)) as c:
        yield c


def _changed_lines(a: str, b: str) -> list[tuple[str, str]]:
    out = []
    for line in difflib.unified_diff(a.splitlines(), b.splitlines(), n=0, lineterm=""):
        if line[:1] in "+-" and not line.startswith(("+++", "---")):
            out.append((line[0], line[1:]))
    return out


def ops(client, *items):
    r = client.post("/api/ops", json={"ops": list(items)})
    assert r.status_code == 200, r.text
    return r.json()


def test_state(client):
    st = client.get("/api/state").json()
    assert st["file"] == "mapcan.yaml" and not st["dirty"]
    assert not [d for d in st["diagnostics"] if d["level"] == "error"]
    assert st["data"]["buses"][0]["name"] == "bus1"
    f = next(f for f in st["resolved"]["frames"] if f["name"] == "imd_state")
    assert f["can_id"] == 0x1A1
    assert f["signals"][1]["flags"][0]["occupied"] == [8]
    assert f["sender"] == "imd" and f["receivers"] == []
    sdo = next(f for f in st["resolved"]["frames"] if f["name"] == "imd_sdo_request")
    assert sdo["signals"][0]["synthetic"]
    assert sdo["sender"] is None and sdo["receivers"] == ["imd"]


def test_set_preserves_everything_else(client, mapfile):
    before = mapfile.read_text(encoding="utf-8")
    st = ops(client, {"op": "set", "path": SIG + ["factor"], "value": 0.01})
    assert st["dirty"]
    assert _changed_lines(before, st["text"]) == [("-", "                factor: 0.1"),
                                                  ("+", "                factor: 0.01")]
    client.post("/api/save", json={})
    assert mapfile.read_text(encoding="utf-8") == st["text"]
    assert not client.get("/api/state").json()["dirty"]


def test_flow_mapping_untouched_when_neighbour_changes(client):
    before = client.get("/api/state").json()["text"]
    st = ops(client, {"op": "set", "path": ["buses", 0, "devices", 0, "frames", 3, "description"],
                      "value": "Настройка"})
    assert len(_changed_lines(before, st["text"])) == 2
    assert "                value: {name: alarm_resistance, encoding: metric, bit_length: 16, unit: кОм,\n" in st["text"]


def test_hex_kept(client):
    st = ops(client, {"op": "set", "path": ["buses", 0, "devices", 0, "node_id"], "value": 0x20})
    assert "node_id: 0x20" in st["text"]
    f = next(f for f in st["resolved"]["frames"] if f["name"] == "imd_state")
    assert f["can_id"] == 0x1A0


def test_set_layout_sugar_and_validation(client):
    st = ops(client, {"op": "set_layout", "path": SIG, "start_bit": 40, "bit_length": 16})
    assert "                byte: 5\n                byte_length: 2\n                factor: 0.1" in st["text"]
    d = next(d for d in st["diagnostics"] if d["code"] == "bit-overlap")
    assert d["node"][:6] == SIG[:6]


def test_set_layout_canonical(client):
    st = ops(client, {"op": "set_layout", "path": SIG, "start_bit": 50, "bit_length": 12})
    assert "                start_bit: 50\n                bit_length: 12\n" in st["text"]


@pytest.mark.parametrize("start, length", [
    (1.5, 8), (10**20, 8), (512, 8), (-1, 8), (0, 65), (0, 0), ("8", 8), (True, 8),
])
def test_set_layout_rejects_bad_position(client, start, length):
    before = client.get("/api/state").json()["text"]
    op = {"op": "set_layout", "path": SIG, "start_bit": start, "bit_length": length}
    r = client.post("/api/ops", json={"ops": [op]})
    assert r.status_code == 400
    assert client.get("/api/state").json()["text"] == before


def test_insert_signal_and_remove(client):
    path = ["buses", 0, "devices", 1, "frames", 0, "signals"]
    st = ops(client,
             {"op": "insert", "path": path, "value": {"name": "spare", "encoding": "raw", "description": "Резерв", "byte": 2, "byte_length": 1}},
             {"op": "set", "path": ["buses", 0, "devices", 1, "frames", 0, "dlc"], "value": 3})
    assert "- name: spare" in st["text"]
    assert not [d for d in st["diagnostics"] if d["level"] == "error"]
    st = ops(client, {"op": "remove", "path": path + [2]})
    assert "- name: spare" not in st["text"]


def test_insert_into_missing_list(client):
    st = ops(client, {"op": "insert", "path": ["buses", 0, "devices", 3, "frames", 0, "signals"],
                      "value": {"name": "mode", "encoding": "raw", "description": "Режим", "byte": 0, "byte_length": 1}})
    f = next(f for f in st["resolved"]["frames"] if f["name"] == "bypass_command")
    assert f["signals"][0]["name"] == "mode"


def test_move(client):
    path = ["buses", 0, "devices", 0, "frames", 0, "signals"]
    st = ops(client, {"op": "move", "path": path + [2], "to": 0})
    assert st["data"]["buses"][0]["devices"][0]["frames"][0]["signals"][0]["name"] == "imd_state"


def test_enum_key_rename_and_add(client):
    vals = ["buses", 0, "devices", 0, "frames", 0, "signals", 0, "values"]
    st = ops(client,
             {"op": "rename_key", "path": vals + ["3"], "new_key": "7"},
             {"op": "set", "path": vals + ["8"], "value": {"name": "SERVICE", "description": "сервис"}})
    assert "                  7:\n" in st["text"] and "name: SERVICE" in st["text"]
    keys = list(st["data"]["buses"][0]["devices"][0]["frames"][0]["signals"][0]["values"])
    assert keys == ["0", "1", "2", "7", "8"] or keys == [0, 1, 2, 7, 8]


def test_set_none_removes_key(client):
    st = ops(client, {"op": "set", "path": SIG + ["unit"], "value": None})
    assert "unit: В\n" not in st["text"].split("bus_voltage")[1].split("- name")[0]


def test_localized_text_and_date(client):
    st = ops(client,
             {"op": "set", "path": ["document", "title"], "value": {"ru": "Карта", "en": "Map"}},
             {"op": "set", "path": ["document", "date"], "value": "2026-11-01"})
    assert "date: 2026-11-01\n" in st["text"]
    assert "en: Map" in st["text"]


def test_bad_op_is_atomic(client):
    before = client.get("/api/state").json()["text"]
    r = client.post("/api/ops", json={"ops": [
        {"op": "set", "path": SIG + ["factor"], "value": 2},
        {"op": "remove", "path": ["buses", 9]},
    ]})
    assert r.status_code == 400
    after = client.get("/api/state").json()
    assert after["text"] == before and not after["dirty"]
    assert "factor: 3" in ops(client, {"op": "set", "path": SIG + ["factor"], "value": 3})["text"]


def test_undo_redo(client):
    t0 = client.get("/api/state").json()["text"]
    t1 = ops(client, {"op": "set", "path": SIG + ["unit"], "value": "кВ"})["text"]
    st = client.post("/api/undo").json()
    assert st["text"] == t0 and st["can_redo"] and not st["dirty"]
    assert client.post("/api/redo").json()["text"] == t1


def test_text_with_errors(client):
    st = client.post("/api/text", json={"text": "mapcan: 1\ndocument: [\n"}).json()
    assert st["data"] is None
    assert st["diagnostics"][0]["code"] == "yaml" and st["diagnostics"][0]["line"]
    r = client.post("/api/ops", json={"ops": [{"op": "set", "path": ["mapcan"], "value": 1}]})
    assert r.status_code == 400
    assert client.get("/api/export/md").status_code == 409


def test_check_text_does_not_apply(client):
    before = client.get("/api/state").json()
    text = before["text"].replace("signals:\n", "signals:\n              -oops: 1\n", 1)
    diags = client.post("/api/check", json={"text": text}).json()["diagnostics"]
    assert diags and diags[0]["code"] == "yaml" and "space after '-'" in diags[0]["message"]
    after = client.get("/api/state").json()
    assert after["text"] == before["text"] and after["version"] == before["version"]



def test_schema_for_yaml_hints(client):
    from mapcan.schema import json_schema

    assert client.get("/api/schema").json() == json_schema()


SYNC = ["buses", 0, "frames", 0]


def _with_refs(client):
    """Кадр sync со ссылками на устройства imd и cmu."""
    return ops(client, {"op": "set", "path": SYNC + ["sender"], "value": "imd"},
               {"op": "set", "path": SYNC + ["receivers"], "value": ["cmu", "imd"]})


def _rename(text, old, new):
    assert f"      - name: {old}\n" in text
    return text.replace(f"      - name: {old}\n", f"      - name: {new}\n", 1)


def test_text_rename_device_updates_refs(client):
    t0 = _with_refs(client)["text"]
    st = client.post("/api/text", json={"text": _rename(t0, "imd", "iso")}).json()
    sync = st["data"]["buses"][0]["frames"][0]
    assert sync["sender"] == "iso" and sync["receivers"] == ["cmu", "iso"]
    assert not [d for d in st["diagnostics"] if d["level"] == "error"]
    assert client.post("/api/undo").json()["text"] == t0


def test_text_swap_devices_keeps_refs(client):
    t0 = _with_refs(client)["text"]
    text = _rename(_rename(_rename(t0, "imd", "tmp"), "cmu", "imd"), "tmp", "cmu")
    sync = client.post("/api/text", json={"text": text}).json()["data"]["buses"][0]["frames"][0]
    assert sync["sender"] == "imd" and sync["receivers"] == ["cmu", "imd"]


def test_live_text_is_one_undo_step(client):
    t0 = _with_refs(client)["text"]
    # Ввод по буквам: промежуточные имена, в том числе пустое, не должны сбить ссылки.
    for name in ("im", "", "is", "iso"):
        st = client.post("/api/text", json={"text": _rename(t0, "imd", name), "live": True}).json()
    sync = st["data"]["buses"][0]["frames"][0]
    assert sync["sender"] == "iso" and sync["receivers"] == ["cmu", "iso"]
    final = client.post("/api/text", json={"text": _rename(t0, "imd", "iso")}).json()
    assert final["text"] == st["text"]
    st = client.post("/api/undo").json()
    assert st["text"] == t0 and st["can_undo"]                # шаг правки ссылок формой остался
    assert client.post("/api/undo").json()["data"]["buses"][0]["frames"][0].get("sender") is None


def test_live_text_back_to_start_leaves_no_step(client):
    t0 = _with_refs(client)["text"]
    client.post("/api/text", json={"text": _rename(t0, "imd", "iso"), "live": True})
    st = client.post("/api/text", json={"text": t0, "live": True}).json()
    assert st["text"] == t0
    # Последний шаг отмены — правка ссылок формой, а не пустая серия ввода.
    assert client.post("/api/undo").json()["data"]["buses"][0]["frames"][0].get("sender") is None


def test_save_conflict(client, mapfile):
    ops(client, {"op": "set", "path": SIG + ["unit"], "value": "кВ"})
    mapfile.write_text(mapfile.read_text(encoding="utf-8") + "\n# внешняя правка\n", encoding="utf-8")
    assert client.get("/api/state").json()["disk_changed"]
    assert client.post("/api/save", json={}).status_code == 409
    assert client.post("/api/save", json={"force": True}).status_code == 200
    assert "кВ" in mapfile.read_text(encoding="utf-8")


def test_crlf_preserved(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_bytes(REFERENCE.read_bytes().replace(b"\n", b"\r\n"))
    with TestClient(create_app(EditorSession(p))) as c:
        ops(c, {"op": "set", "path": SIG + ["unit"], "value": "кВ"})
        c.post("/api/save", json={})
    data = p.read_bytes()
    assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")


def test_reload(client, mapfile):
    ops(client, {"op": "set", "path": SIG + ["unit"], "value": "кВ"})
    st = client.post("/api/reload").json()
    assert not st["dirty"] and st["text"] == mapfile.read_text(encoding="utf-8")


def test_readonly(mapfile):
    with TestClient(create_app(EditorSession(mapfile, readonly=True))) as c:
        assert c.get("/api/state").json()["readonly"]
        assert c.post("/api/ops", json={"ops": []}).status_code == 403
        assert c.post("/api/save", json={}).status_code == 403


@pytest.mark.parametrize("fmt, prefix", [
    ("md", "# Эталонная карта CANopen".encode()),
    ("html", b"<!doctype html>"),
    ("xlsx", b"PK"),
    ("pdf", b"%PDF"),
])
def test_export(client, fmt, prefix):
    r = client.get(f"/api/export/{fmt}")
    assert r.status_code == 200 and r.content.startswith(prefix)


@pytest.mark.parametrize("fmt, names", [
    ("dbc", {"bus1.dbc", "bus2.dbc"}),
    ("c", {"bus1.h", "bus1.c", "bus2.h", "bus2.c"}),
    ("py", {"bus1_mapcan.py", "bus2_mapcan.py"}),
])
def test_export_zip(client, fmt, names):
    r = client.get(f"/api/export/{fmt}")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert set(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == names


def test_export_uses_unsaved_state(client):
    ops(client, {"op": "set", "path": ["document", "title"], "value": "Новая карта"})
    assert client.get("/api/export/md").content.startswith("# Новая карта".encode())


def test_diff_upload(client):
    ops(client, {"op": "set", "path": SIG + ["factor"], "value": 0.01})
    r = client.post("/api/diff/upload", files={"file": ("old.yaml", REFERENCE.read_bytes())})
    assert r.status_code == 200
    assert r.json()["lines"] == ["0x2A1 imd_data: bus_voltage.factor 0.1 → 0.01"]


@pytest.mark.skipif(shutil.which("git") is None, reason="нет git")
def test_git_revs_reason(client, mapfile):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       cwd=mapfile.parent, check=True, capture_output=True)

    assert client.get("/api/git/revs").json() == {"available": False, "tags": [], "all_tags": [], "branches": [],
                                                  "commits": [], "reason": "no-repo"}
    git("init", "-q")
    assert client.get("/api/git/revs").json()["reason"] == "untracked"
    # Тег до появления карты в репозитории: в списке для сравнения его нет
    (mapfile.parent / "other.txt").write_text("x")
    git("add", "other.txt")
    git("commit", "-q", "-m", "other")
    git("tag", "pre")
    git("add", mapfile.name)
    git("commit", "-q", "-m", "init")
    git("tag", "-a", "v1", "-m", "v1")
    git("branch", "side")
    r = client.get("/api/git/revs").json()
    assert r["available"] and [c["subject"] for c in r["commits"]] == ["init"]
    assert r["commits"][0]["tags"] == ["v1"] and r["commits"][0]["author"] == "t"
    assert r["tags"] == ["v1"] and sorted(r["all_tags"]) == ["pre", "v1"]
    assert r["branches"] == ["side"]
    assert client.post("/api/diff/git", json={"rev": "HEAD"}).json()["lines"] == []
    assert client.post("/api/diff/git", json={"rev": "pre"}).json()["code"] == "git-no-file"
    # Ревизия, похожая на ключ git (--output=…), отклоняется
    assert client.post("/api/diff/git", json={"rev": "--output=x"}).status_code == 400

    # Версия из git открывается в редакторе как несохранённая правка
    committed = mapfile.read_text(encoding="utf-8")
    ops(client, {"op": "set", "path": SIG + ["factor"], "value": 0.5})
    st = client.post("/api/git/restore", json={"rev": "v1"}).json()
    assert st["text"] == committed
    assert client.post("/api/undo").json()["text"] != committed


@pytest.mark.skipif(shutil.which("git") is None, reason="нет git")
def test_git_commit_tag_pull(client, mapfile, tmp_path):
    def git(*args, cwd=mapfile.parent):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                              cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8").stdout

    assert client.get("/api/git/status").json() == {"available": False, "reason": "no-repo"}
    assert client.post("/api/git/init").json()["available"]
    assert client.post("/api/git/init").json()["code"] == "git-exists"
    git("config", "user.name", "t")
    git("config", "user.email", "t@t")
    (mapfile.parent / "other.txt").write_text("x")
    st = client.get("/api/git/status").json()
    assert st["available"] and st["file"] == "untracked" and st["last"] is None

    # Несохранённые правки не коммитятся
    ops(client, {"op": "set", "path": SIG + ["factor"], "value": 0.01})
    assert client.post("/api/git/commit", json={"message": "m"}).json()["code"] == "unsaved"
    assert client.post("/api/save", json={}).status_code == 200
    assert client.post("/api/git/commit", json={"message": "  "}).json()["code"] == "git-message"
    assert client.post("/api/git/commit", json={"message": "m", "tag": "-x"}).json()["code"] == "git-tag"

    st = client.post("/api/git/commit", json={"message": "первая версия", "tag": "v1.0"}).json()
    assert st["file"] == "clean" and st["last"]["subject"] == "первая версия"
    assert git("tag").split() == ["v1.0"]
    # Коммитится только карта: посторонний файл остаётся неотслеживаемым
    assert "?? other.txt" in git("status", "--porcelain")
    assert client.post("/api/git/commit", json={"message": "m"}).json()["code"] == "git-nothing"

    assert client.post("/api/git/tag", json={"name": "bad tag"}).json()["code"] == "git-tag"
    client.post("/api/git/tag", json={"name": "v1.1", "message": "релиз"})
    assert git("tag").split() == ["v1.0", "v1.1"]

    # pull из клона: изменения с удалённой стороны подхватываются редактором
    remote = tmp_path / "remote.git"
    git("clone", "-q", "--bare", ".", str(remote))
    assert client.post("/api/git/push").json()["code"] == "no-remote"
    git("remote", "add", "origin", str(remote))
    # Первый push ветки задаёт upstream
    st = client.post("/api/git/push").json()
    assert st["remote"] == "origin" and st["upstream"] == "origin/" + st["branch"]
    assert client.post("/api/gh/create", json={"name": "-bad"}).json()["code"] == "gh-name"
    assert client.post("/api/gh/create", json={"name": "maps"}).json()["code"] in ("gh-remote", "no-gh")
    other = tmp_path / "other"
    git("clone", "-q", str(remote), str(other), cwd=tmp_path)
    p = other / mapfile.name
    p.write_text(p.read_text(encoding="utf-8").replace("factor: 0.01", "factor: 0.02"), encoding="utf-8")
    git("commit", "-q", "-am", "remote", cwd=other)
    git("push", "-q", cwd=other)
    assert client.post("/api/git/pull").status_code == 200
    assert "factor: 0.02" in client.get("/api/state").json()["text"]

    ops(client, {"op": "set", "path": SIG + ["factor"], "value": 0.03})
    assert client.post("/api/save", json={}).status_code == 200
    st = client.post("/api/git/commit", json={"message": "локально"}).json()
    assert st["ahead"] == 1
    assert client.post("/api/git/push").json()["ahead"] == 0
    # Лёгкие теги не уходят с push --follow-tags, поэтому тег всегда аннотированный
    assert git("cat-file", "-t", "v1.0").strip() == "tag"
    client.post("/api/git/tag", json={"name": "v2"})
    assert git("cat-file", "-t", "v2").strip() == "tag"
    client.post("/api/git/push")
    assert "v2" in git("tag", cwd=remote).split()

    # Сервер ушёл вперёд: fetch показывает отставание, push отклоняется понятным сообщением
    git("pull", "-q", cwd=other)
    p.write_text(p.read_text(encoding="utf-8").replace("factor: 0.03", "factor: 0.04"), encoding="utf-8")
    git("commit", "-q", "-am", "remote 2", cwd=other)
    git("push", "-q", cwd=other)
    assert client.post("/api/git/fetch").json()["behind"] == 1
    ops(client, {"op": "set", "path": SIG + ["factor"], "value": 0.05})
    client.post("/api/save", json={})
    client.post("/api/git/commit", json={"message": "параллельно"})
    assert client.post("/api/git/push").json()["code"] == "git-push-rejected"
    assert client.post("/api/git/pull").json()["code"] == "git-diverged"


@pytest.mark.skipif(shutil.which("git") is None, reason="нет git")
def test_git_release(client, mapfile):
    def git(*args):
        return subprocess.run(["git", *args], cwd=mapfile.parent, check=True, capture_output=True,
                              text=True, encoding="utf-8").stdout

    assert client.get("/api/git/release").json()["code"] == "git-unavailable"
    git("init", "-q")
    git("config", "user.name", "t")
    git("config", "user.email", "t@t")
    # Карты ещё нет в git; версия 1.0.0 уже записана в истории — выпускается она, без новой записи
    d = client.get("/api/git/release").json()
    assert (d["version"], d["recorded"], d["base"]) == ("1.0.0", True, None)
    r = client.post("/api/git/release", json={"version": "1.0.0", "changes": d["changes"]}).json()
    assert r["tag"] == "v1.0.0" and r["git"]["file"] == "clean"
    assert git("tag").split() == ["v1.0.0"]
    assert client.get("/api/state").json()["text"].count("- version: 1.0.0") == 1

    # Несохранённая правка: следующая версия, изменения — с тега прошлого выпуска
    ops(client, {"op": "set", "path": SIG + ["factor"], "value": 0.01})
    d = client.get("/api/git/release").json()
    assert (d["version"], d["recorded"], d["base"]) == ("1.0.1", False, "v1.0.0")
    assert d["changes"] == ["0x2A1 imd_data: bus_voltage.factor 0.1 → 0.01"]
    r = client.post("/api/git/release", json={"version": "1.0.1", "changes": d["changes"]}).json()
    assert r["tag"] == "v1.0.1" and r["git"]["file"] == "clean"
    assert git("log", "-1", "--format=%s") == "1.0.1: 0x2A1 imd_data: bus_voltage.factor 0.1 → 0.01\n"
    assert git("tag", "--points-at", "HEAD").split() == ["v1.0.1"]
    st = client.get("/api/state").json()
    assert not st["dirty"]
    doc = st["data"]["document"]
    assert doc["version"] == "1.0.1" and doc["history"][0]["version"] == "1.0.1"
    assert doc["history"][0]["changes"] == d["changes"]
    # Повторно ту же версию выпустить нельзя
    assert client.post("/api/git/release", json={"version": "1.0.1"}).json()["code"] == "git-tag-exists"
    assert client.post("/api/git/release", json={"version": " "}).json()["code"] == "version"


@pytest.mark.skipif(shutil.which("git") is None, reason="нет git")
def test_git_logo_tag_identity(client, mapfile, monkeypatch):
    def git(*args):
        # git пишет UTF-8; без encoding Windows читает вывод в кодировке ANSI (cp1252)
        return subprocess.run(["git", *args], cwd=mapfile.parent, check=True, capture_output=True,
                              text=True, encoding="utf-8").stdout

    # Без глобальных настроек git автор берётся из профиля mapcan
    empty = mapfile.parent / "empty.gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    git("init", "-q")
    git("config", "user.useConfigOnly", "true")        # не угадывать адрес по имени компьютера
    logo = mapfile.parent / "assets" / "logo.png"
    logo.parent.mkdir()
    logo.write_bytes(b"\x89PNG one")
    ops(client, {"op": "set", "path": ["document", "logo"], "value": "assets/logo.png"})
    client.post("/api/save", json={})
    assert client.post("/api/git/commit", json={"message": "m"}).json()["code"] == "git-identity"
    client.put("/api/user", json={"name": "Иван", "github": "ivan"})
    st = client.post("/api/git/commit", json={"message": "m", "tag": "v1"}).json()
    assert st["file"] == "clean"
    assert git("log", "-1", "--format=%an <%ae>").strip() == "Иван <ivan@users.noreply.github.com>"
    # Логотип из подпапки попадает в коммит
    assert "assets/logo.png" in git("ls-files").split()

    # Изменён только логотип — это тоже незакоммиченное изменение
    logo.write_bytes(b"\x89PNG two")
    assert client.get("/api/git/status").json()["file"] == "modified"
    # Занятый тег отклоняется до коммита
    head = git("rev-parse", "HEAD")
    assert client.post("/api/git/commit", json={"message": "m2", "tag": "v1"}).json()["code"] == "git-tag-exists"
    assert git("rev-parse", "HEAD") == head
    assert client.post("/api/git/commit", json={"message": "m2"}).json()["file"] == "clean"

    # Карта в .gitignore
    other = mapfile.parent / "ignored.yaml"
    other.write_text(mapfile.read_text(encoding="utf-8"), encoding="utf-8")
    (mapfile.parent / ".gitignore").write_text("ignored.yaml\n")
    with TestClient(create_app(EditorSession(other), poll_interval=0.05)) as c2:
        assert c2.get("/api/git/status").json()["file"] == "ignored"
        assert c2.post("/api/git/commit", json={"message": "m"}).json()["code"] == "git-ignored"


def test_web_url():
    from mapcan.web.app import _web_url
    assert _web_url("git@github.com:owner/repo.git") == "https://github.com/owner/repo"
    assert _web_url("ssh://git@gitlab.local/team/repo.git") == "https://gitlab.local/team/repo"
    assert _web_url("https://user:token@github.com/owner/repo.git\n") == "https://github.com/owner/repo"
    assert _web_url("/srv/git/repo.git") is None


def test_websocket_notifications(client, mapfile):
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["app"] == client.get("/api/meta").json()["version"]
        ops(client, {"op": "set", "path": SIG + ["unit"], "value": "кВ"})
        assert ws.receive_json()["type"] == "state"
        mapfile.write_text("# внешняя правка\n" + mapfile.read_text(encoding="utf-8"), encoding="utf-8")
        assert ws.receive_json()["type"] == "file-changed"


def test_index_not_cached(client):
    r = client.get("/")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"


def test_appended_item_goes_before_blank_separator(client):
    path = ["buses", 0, "devices", 1, "frames", 0, "signals"]
    st = ops(client, {"op": "insert", "path": path, "value": {"name": "spare", "byte": 2}},
             {"op": "set", "path": ["buses", 0, "devices", 1, "frames", 0, "dlc"], "value": 3})
    assert ("нет связи с датчиком температуры}\n"
            "              - name: spare\n"
            "                byte: 2\n"
            "\n"
            "          - name: cmu_event\n") in st["text"]


def test_appended_key_goes_before_blank_separator(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("mapcan: 1\n\ndocument:\n  title: T\n  version: 0.1.0\n\nbuses: []\n", encoding="utf-8")
    s = EditorSession(p)
    s.apply([{"op": "insert", "path": ["document", "history"], "index": 0,
              "value": {"version": "0.1.0", "changes": ["first"]}}])
    assert s.text == ("mapcan: 1\n\ndocument:\n  title: T\n  version: 0.1.0\n"
                      "  history:\n    - version: 0.1.0\n      changes:\n        - first\n\nbuses: []\n")


def test_guard_rejects_foreign_host(mapfile):
    """DNS rebinding: страница чужого домена, указывающего на 127.0.0.1, не получает API."""
    app = create_app(EditorSession(mapfile), allowed_hosts=("127.0.0.1", "localhost", "::1"))
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/state").status_code == 200
        assert c.get("/api/state", headers={"host": "localhost:5173"}).status_code == 200
        assert c.get("/api/state", headers={"host": "[::1]:8765"}).status_code == 200
        r = c.get("/api/state", headers={"host": "evil.example:8765"})
        assert r.status_code == 403 and r.json()["code"] == "forbidden"


def test_guard_rejects_cross_origin_writes(client):
    """CSRF: изменяющий запрос и WebSocket с чужим Origin отклоняются, свои и без Origin — нет."""
    assert client.post("/api/save", json={}, headers={"origin": "http://evil.example"}).status_code == 403
    assert client.post("/api/save", json={}, headers={"origin": "http://testserver"}).status_code != 403
    assert client.post("/api/save", json={}).status_code != 403
    assert client.get("/api/state", headers={"origin": "http://evil.example"}).status_code == 200
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws", headers={"origin": "http://evil.example"}):
        pass
    with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
        assert ws.receive_json()["type"] == "hello"
