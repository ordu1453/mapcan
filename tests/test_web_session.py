"""The editing session of the web editor on its own: the disk, undo and redo, included files."""

from __future__ import annotations

import shutil

import pytest

from mapcan.web import session as S
from mapcan.web.session import EditorSession
from mapcan.web.yamlops import OpError

from .conftest import ROOT

GATEWAY_TITLE = ["buses", 0, "devices", 1, "title"]        # the gateway of tractor.yaml, in powertrain.yaml


@pytest.fixture
def minimal(tmp_path):
    p = tmp_path / "m.yaml"
    shutil.copyfile(ROOT / "examples" / "minimal.yaml", p)
    return p


@pytest.fixture
def tractor(tmp_path):
    for f in ("tractor.yaml", "powertrain.yaml"):
        shutil.copyfile(ROOT / "examples" / "tractor" / f, tmp_path / f)
    return tmp_path / "tractor.yaml"


def test_disk_changed(minimal):
    s = EditorSession(minimal)
    assert not s.disk_changed()
    minimal.write_bytes(b"\xff\xfe")          # not UTF-8 any more
    assert s.disk_changed()
    minimal.unlink()
    assert s.disk_changed()


def test_disk_changed_of_an_included_file(tractor):
    s = EditorSession(tractor)
    assert not s.disk_changed()
    part = tractor.parent / "powertrain.yaml"
    part.write_bytes(b"\xff\xfe")
    assert s.disk_changed()


def test_undo_and_redo_without_steps(minimal):
    s = EditorSession(minimal)
    assert not s.undo() and not s.redo()
    s.apply([{"op": "set", "path": ["document", "title"], "value": "New"}])
    assert s.undo() and "title: Example map" in s.text
    assert s.redo() and "title: New" in s.text
    assert not s.redo()


def test_recheck_builds_the_messages_again(minimal):
    s = EditorSession(minimal)
    version = s.version
    s.recheck()
    assert s.version == version + 1 and s.map is not None


def test_relative_name_on_another_drive(minimal, monkeypatch):
    s = EditorSession(minimal)

    def other_drive(path, start):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(S.os.path, "relpath", other_drive)
    assert s._rel(minimal.parent / "sub" / "part.yaml") == "part.yaml"


def test_save_as_writes_the_edited_included_files(tractor, tmp_path):
    s = EditorSession(tractor)
    s.apply([{"op": "set", "path": GATEWAY_TITLE, "value": "Gateway ECU"}])
    s.save_as(tmp_path / "copy.yaml")
    assert "title: Gateway ECU" in (tmp_path / "powertrain.yaml").read_text(encoding="utf-8")
    assert not s.dirty


def test_edit_of_an_included_file_that_cannot_be_read(tractor):
    s = EditorSession(tractor)
    (tractor.parent / "powertrain.yaml").unlink()
    s.parts.clear()
    with pytest.raises(OpError, match="powertrain.yaml"):
        s.apply([{"op": "set", "path": GATEWAY_TITLE, "value": "x"}])


def test_add_device_file_refusals(minimal):
    s = EditorSession(minimal)
    device = {"name": "node", "title": "Node", "node_id": 3, "frames": []}
    with pytest.raises(OpError, match="path not found"):
        s.add_device_file(["buses", 7], device, "devices/node.yaml")
    s.set_text("mapcan: [\n")
    with pytest.raises(OpError, match="syntax error"):
        s.add_device_file(["buses", 0], device, "devices/node.yaml")


def test_undo_removes_a_file_made_after_that_state(minimal):
    s = EditorSession(minimal)
    s.add_device_file(["buses", 0], {"name": "node", "title": "Node", "node_id": 3, "frames": []}, "devices/node.yaml")
    [part] = [p for p in s.parts.values() if p.created]
    assert part.text is not None
    assert s.undo()
    assert part.text is None and "include" not in s.text
    assert s.redo() and part.text is not None
