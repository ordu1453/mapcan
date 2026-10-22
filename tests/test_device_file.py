"""A new device in a file of its own (#136): the web editor's session and API, and the language server."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mapcan.loader import load
from mapcan.lsp import analysis as A
from mapcan.lsp import edits as E
from mapcan.web.app import create_app
from mapcan.web.devicefile import device_file_target, part_is_empty
from mapcan.web.session import EditorSession
from mapcan.web.yamlops import OpError

from .conftest import ROOT

DEVICE = {"name": "node_c", "title": "Device 3", "node_id": 3, "frames": []}


@pytest.fixture
def drive(tmp_path) -> Path:
    """A map without include."""
    p = tmp_path / "drive.yaml"
    shutil.copyfile(ROOT / "examples" / "canopen-node.yaml", p)
    return p


@pytest.fixture
def tractor(tmp_path) -> Path:
    """A map that includes a file already."""
    for f in ("tractor.yaml", "powertrain.yaml"):
        shutil.copyfile(ROOT / "examples" / "tractor" / f, tmp_path / f)
    return tmp_path / "tractor.yaml"


def test_session_adds_a_device_in_a_new_file(drive):
    s = EditorSession(drive)
    s.add_device_file(["buses", 0], DEVICE, "devices/node_c.yaml")
    # A new include goes to its place, as on one line, separated as the other keys are
    assert "  language: en\n\ninclude: [devices/node_c.yaml]\n\nbuses:\n" in s.text
    new = drive.parent / "devices" / "node_c.yaml"
    assert not new.exists()                     # written by Save
    st = s.state()
    assert st["dirty_files"] == ["devices/node_c.yaml"]
    assert {"path": ["buses", 0, "devices", 2], "file": "devices/node_c.yaml",
            "local": ["buses", 0, "devices", 0]} in st["included"]
    assert [d["name"] for d in st["included_buses"][0]["devices"]][-1] == "node_c"
    assert not [d for d in st["diagnostics"] if d["level"] == "error"]

    s.save()
    assert new.read_text(encoding="utf-8") == (
        "# yaml-language-server: $schema=https://ordu1453.github.io/mapcan/schema/part-v1.json\n\n"
        "mapcan: 1\npart_of: ../drive.yaml\n\nbuses:\n  - name: drive_bus\n    devices:\n"
        "      - name: node_c\n        title: Device 3\n        node_id: 0x03\n        frames: []\n")
    m = load(drive)
    assert "node_c" in [d.name for d in m.map.buses[0].devices]


@pytest.mark.parametrize(("file", "name"), [
    ("devices/pump.yaml", "pump"),             # named after the file
    ("devices/drive.yaml", "node_c"),          # taken on the bus
    ("devices/2nd-node.yaml", "node_c"),       # not an identifier
    ("devices/class.yaml", "node_c"),          # a keyword
])
def test_the_device_is_named_after_its_file(drive, file, name):
    s = EditorSession(drive)
    s.add_device_file(["buses", 0], DEVICE, file)
    assert s.state()["included_buses"][0]["devices"][-1]["name"] == name


def test_undo_removes_the_new_file_and_redo_brings_it_back(drive):
    s = EditorSession(drive)
    before = s.text
    s.add_device_file(["buses", 0], DEVICE, "devices/node_c.yaml")
    assert s.undo()
    assert s.text == before and not s.dirty and s.state()["dirty_files"] == []
    s.save()
    assert not (drive.parent / "devices").exists()
    assert s.redo()
    assert s.state()["dirty_files"] == ["devices/node_c.yaml"]
    # Undone and made again: the same name is free
    s.undo()
    s.add_device_file(["buses", 0], DEVICE, "devices/node_c.yaml")
    assert "devices/node_c.yaml" in s.text


def test_the_file_joins_an_existing_include(tractor):
    s = EditorSession(tractor)
    s.add_device_file(["buses", 0], DEVICE, "devices/node_c.yaml")
    assert "include: [powertrain.yaml, devices/node_c.yaml]" in s.text
    s.save()
    assert "part_of: ../tractor.yaml" in (tractor.parent / "devices" / "node_c.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("file", ["", "devices/node_c.txt", "drive.yaml"])
def test_wrong_names_are_refused(drive, file):
    s = EditorSession(drive)
    with pytest.raises(OpError):
        s.add_device_file(["buses", 0], DEVICE, file)
    assert not s.dirty and not s.undo_stack


def test_absolute_path_is_refused(drive):
    with pytest.raises(ValueError):
        device_file_target(drive, str(drive.parent / "x.yaml"))
    target, line = device_file_target(drive, "shared/../devices/a.yml")
    assert line == "devices/a.yml" and target == (drive.parent / "devices" / "a.yml").resolve()


def test_api(drive):
    with TestClient(create_app(EditorSession(drive), poll_interval=0.05)) as c:
        r = c.post("/api/device_file", json={"bus": ["buses", 0], "device": DEVICE, "file": "devices/node_c.yaml"})
        assert r.status_code == 200, r.text
        assert r.json()["dirty_files"] == ["devices/node_c.yaml"]
        r = c.post("/api/device_file", json={"bus": ["buses", 0], "device": DEVICE, "file": "devices/node_c.yaml"})
        assert r.status_code >= 400
        assert c.post("/api/save", json={}).status_code == 200
    assert (drive.parent / "devices" / "node_c.yaml").is_file()


class _Server:
    """The language server's state the command needs: the analysis of open documents and the files on the disk."""

    def __init__(self, path: Path):
        self.uri = path.as_uri()
        self.a = A.analyze_part(path.read_text(encoding="utf-8"), str(path)) if "part_of" in path.read_text(
            encoding="utf-8") else A.analyze(path.read_text(encoding="utf-8"), str(path))

    def analysis(self, uri: str):
        return self.a if uri == self.uri else None

    @staticmethod
    def read(f: str) -> str | None:
        return A.read_disk(f)

    def routed(self, a, ops, style):
        from mapcan.lsp.server import MapcanServer

        return MapcanServer.routed(self, a, ops, style)


def test_language_server_command(drive):
    pytest.importorskip("pygls")
    from mapcan.lsp.server import device_file_command

    ls = _Server(drive)
    args = {"uri": ls.uri, "path": ["buses", 0]}
    assert device_file_command(ls, args) == {"file": "devices/device.yaml"}
    r = device_file_command(ls, {**args, "file": "devices/device.yaml"})
    assert r["create"]["uri"] == (drive.parent / "devices" / "device.yaml").resolve().as_uri()
    assert "      - name: device\n        title: Device 3\n        node_id: 0x02\n" in r["create"]["text"]
    lines = r["create"]["text"].splitlines()
    line, col = r["cursor"]
    assert lines[line][col:] == "device"
    assert [e["text"] for e in r["edits"]] and "others" not in r
    assert "include: [devices/device.yaml]" in E.apply_edits(ls.a.text, [
        E.Edit(tuple(e["range"][:2]), tuple(e["range"][2:]), e["text"]) for e in r["edits"]])
    r = device_file_command(ls, {**args, "file": "devices/pump.yaml"})
    assert "      - name: pump\n" in r["create"]["text"]
    assert "      - name: device\n" in device_file_command(ls, {**args, "file": "devices/drive.yaml"})["create"]["text"]
    assert "error" in device_file_command(ls, {**args, "file": "drive.yaml"})
    assert "error" in device_file_command(ls, {**args, "path": ["buses", 5]})


def test_language_server_command_from_an_included_file(tractor):
    """With the included file open, the line of include goes to the main file (others)."""
    pytest.importorskip("pygls")
    from mapcan.lsp.server import device_file_command

    ls = _Server(tractor.parent / "powertrain.yaml")
    r = device_file_command(ls, {"uri": ls.uri, "path": ["buses", 1], "file": "devices/ecu2.yaml"})
    assert not r["edits"] and [o["uri"] for o in r["others"]] == [tractor.resolve().as_uri()]
    assert "devices/ecu2.yaml" in r["others"][0]["edit"]["text"]
    assert "  - name: powertrain\n" in r["create"]["text"] and "part_of: ../tractor.yaml" in r["create"]["text"]


def test_a_device_added_to_the_bus_file_keeps_its_fields():
    a = A.analyze((ROOT / "examples" / "canopen-node.yaml").read_text(encoding="utf-8"), "m.yaml")
    change = E.add_node(a, ("buses", 0), "device")
    assert "      - name: device\n        title: Device 3\n        node_id: 0x02\n" in change.text


# --------------------------------------------------------------------------- deleting the device


@pytest.mark.parametrize(("text", "empty"), [
    ("mapcan: 1\npart_of: m.yaml\nbuses:\n  - name: can1\n    devices: []\n", True),
    ("mapcan: 1\npart_of: m.yaml\n", True),
    ("mapcan: 1\npart_of: m.yaml\nbuses:\n  - name: can1\n    devices: [{name: b}]\n", False),
    ("mapcan: 1\npart_of: m.yaml\nbuses:\n  - name: can1\n    devices: []\n    frames: [{name: f}]\n", False),
    ("mapcan: 1\npart_of: m.yaml\nbuses:\n  - name: can2\n    protocol: can\n    devices: []\n", False),
    ("mapcan: 1\npart_of: m.yaml\nvalue_tables: {t: {0: OFF}}\n", False),
    ("mapcan: [", False),
])
def test_part_is_empty(text, empty):
    assert part_is_empty(text) is empty


def test_deleting_the_device_of_its_own_file_deletes_the_file(drive):
    s = EditorSession(drive)
    s.add_device_file(["buses", 0], DEVICE, "devices/node_c.yaml")
    s.add_device_file(["buses", 0], {**DEVICE, "name": "node_d", "node_id": 4}, "devices/node_d.yaml")
    s.save()
    before = s.text
    devices = drive.parent / "devices"
    s.apply([{"op": "remove", "path": ["buses", 0, "devices", 2]}])
    assert "include: [devices/node_d.yaml]\n" in s.text
    assert s.state()["dirty_files"] == ["devices/node_c.yaml"]
    assert (devices / "node_c.yaml").exists()           # until Save
    s.save()
    assert sorted(p.name for p in devices.iterdir()) == ["node_d.yaml"]
    # The last one: the key goes, without leaving two empty lines
    s.apply([{"op": "remove", "path": ["buses", 0, "devices", 2]}])
    assert "include" not in s.text and "\n\n\n" not in s.text
    s.save()
    assert not list(devices.iterdir())
    # Undo brings back the file and its line
    s.undo()
    s.undo()
    assert s.text == before
    s.save()
    assert sorted(p.name for p in devices.iterdir()) == ["node_c.yaml", "node_d.yaml"]
    assert not [d for d in s.state()["diagnostics"] if d["level"] == "error"]


def test_a_file_with_more_in_it_stays(tractor):
    """powertrain.yaml describes a bus of its own: deleting a device there keeps the file."""
    s = EditorSession(tractor)
    devices = s.state()["included_buses"][1]["devices"]
    s.apply([{"op": "remove", "path": ["buses", 1, "devices", len(devices) - 1]}])
    assert "include: [powertrain.yaml]" in s.text
    assert s.state()["dirty_files"] == ["powertrain.yaml"]


def test_language_server_deletes_the_emptied_file(drive):
    pytest.importorskip("pygls")
    from mapcan.lsp.server import edit_command

    s = EditorSession(drive)
    s.add_device_file(["buses", 0], DEVICE, "devices/node_c.yaml")
    s.save()
    ls = _Server(drive)
    r = edit_command(ls, {"uri": ls.uri, "action": "delete", "path": ["buses", 0, "devices", 2]})
    assert r["delete"] == (drive.parent / "devices" / "node_c.yaml").resolve().as_uri()
    text = E.apply_edits(ls.a.text, [E.Edit(tuple(e["range"][:2]), tuple(e["range"][2:]), e["text"])
                                     for e in r["edits"]])
    assert "include" not in text and "\n\n\n" not in text
    # From the included file itself: the line of include is in the main file
    ls = _Server(drive.parent / "devices" / "node_c.yaml")
    r = edit_command(ls, {"uri": ls.uri, "action": "delete", "path": ["buses", 0, "devices", 2]})
    assert r["delete"] == ls.uri and not r["edits"] and [o["uri"] for o in r["others"]] == [drive.resolve().as_uri()]
    # A device of the main file: an ordinary edit
    r = edit_command(ls, {"uri": ls.uri, "action": "delete", "path": ["buses", 0, "devices", 0]})
    assert "delete" not in r and "edit" in r
