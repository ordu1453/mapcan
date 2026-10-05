"""Бэкенд веб-редактора: операции, сохранение комментариев, undo/redo, экспорт, diff."""

from __future__ import annotations

import difflib
import io
import shutil
import subprocess
import zipfile

import pytest
from fastapi.testclient import TestClient

from canmap.web.app import create_app
from canmap.web.session import EditorSession

from .conftest import REFERENCE

SIG = ["buses", 0, "devices", 0, "frames", 1, "signals", 4]       # imd_data.bus_voltage


@pytest.fixture
def mapfile(tmp_path):
    p = tmp_path / "canmap.yaml"
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
    assert st["file"] == "canmap.yaml" and not st["dirty"]
    assert not [d for d in st["diagnostics"] if d["level"] == "error"]
    assert st["data"]["buses"][0]["name"] == "bus1"
    f = next(f for f in st["resolved"]["frames"] if f["name"] == "imd_state")
    assert f["can_id"] == 0x196
    assert f["signals"][1]["flags"][0]["occupied"] == [8]
    sdo = next(f for f in st["resolved"]["frames"] if f["name"] == "imd_sdo_request")
    assert sdo["signals"][0]["synthetic"]


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
    assert "                value: {name: alarm_resistance, bit_length: 16, unit: кОм,\n" in st["text"]


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


def test_insert_signal_and_remove(client):
    path = ["buses", 0, "devices", 1, "frames", 0, "signals"]
    st = ops(client,
             {"op": "insert", "path": path, "value": {"name": "spare", "description": "Резерв", "byte": 2}},
             {"op": "set", "path": ["buses", 0, "devices", 1, "frames", 0, "dlc"], "value": 3})
    assert "- name: spare" in st["text"]
    assert not [d for d in st["diagnostics"] if d["level"] == "error"]
    st = ops(client, {"op": "remove", "path": path + [2]})
    assert "- name: spare" not in st["text"]


def test_insert_into_missing_list(client):
    st = ops(client, {"op": "insert", "path": ["buses", 0, "devices", 3, "frames", 0, "signals"],
                      "value": {"name": "mode", "description": "Режим", "byte": 0}})
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
    st = client.post("/api/text", json={"text": "canmap: 1\ndocument: [\n"}).json()
    assert st["data"] is None
    assert st["diagnostics"][0]["code"] == "yaml" and st["diagnostics"][0]["line"]
    r = client.post("/api/ops", json={"ops": [{"op": "set", "path": ["canmap"], "value": 1}]})
    assert r.status_code == 400
    assert client.get("/api/export/md").status_code == 409


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
    ("py", {"bus1_canmap.py", "bus2_canmap.py"}),
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
    assert r.json()["lines"] == ["0x296 imd_data: bus_voltage.factor 0.1 → 0.01"]


@pytest.mark.skipif(shutil.which("git") is None, reason="нет git")
def test_git_revs_reason(client, mapfile):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       cwd=mapfile.parent, check=True, capture_output=True)

    assert client.get("/api/git/revs").json() == {"available": False, "tags": [], "commits": [],
                                                  "reason": "no-repo"}
    git("init", "-q")
    assert client.get("/api/git/revs").json()["reason"] == "untracked"
    git("add", mapfile.name)
    git("commit", "-q", "-m", "init")
    r = client.get("/api/git/revs").json()
    assert r["available"] and [c["subject"] for c in r["commits"]] == ["init"]
    assert client.post("/api/diff/git", json={"rev": "HEAD"}).json()["lines"] == []


def test_websocket_notifications(client, mapfile):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        ops(client, {"op": "set", "path": SIG + ["unit"], "value": "кВ"})
        assert ws.receive_json()["type"] == "state"
        mapfile.write_text("# внешняя правка\n" + mapfile.read_text(encoding="utf-8"), encoding="utf-8")
        assert ws.receive_json()["type"] == "file-changed"


def test_appended_item_goes_before_blank_separator(client):
    path = ["buses", 0, "devices", 1, "frames", 0, "signals"]
    st = ops(client, {"op": "insert", "path": path, "value": {"name": "spare", "byte": 2}},
             {"op": "set", "path": ["buses", 0, "devices", 1, "frames", 0, "dlc"], "value": 3})
    assert ("нет связи с датчиком температуры}\n"
            "              - name: spare\n"
            "                byte: 2\n"
            "\n"
            "          - name: cc_event\n") in st["text"]
