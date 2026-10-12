"""Sender and receivers of frames: sender, computed exchange summaries, rules, DBC, documents."""

from __future__ import annotations

import textwrap

import cantools

from mapcan.diff import diff_maps
from mapcan.docmodel import build_view
from mapcan.export.dbc import bus_database
from mapcan.export.text import render
from mapcan.loader import loads

from .conftest import codes, run

# A bus of our own devices: the master sends a PDO RX to the node (ID from the node's node_id) and NMT, the node answers
# with a PDO TX.
CANOPEN = """
mapcan: 1
document:
  title: Тест
  language: ru
buses:
  - name: bus
    protocol: canopen
    frames:
      - name: nmt
        type: nmt
        sender: master
        receivers: [node]
    devices:
      - name: master
        node_id: 0x01
        frames:
          - name: master_status
            type: pdo_tx1
            dlc: 8
            receivers: [node]
      - name: node
        node_id: 0x05
        frames:
          - name: node_command
            type: pdo_rx1
            dlc: 8
            sender: master
          - name: node_status
            type: pdo_tx1
            dlc: 8
            receivers: [master]
"""


def _can(frames_a: str, frames_b: str = "") -> str:
    """A can bus of two devices a and b with the given frames."""
    def block(frames: str) -> str:
        return textwrap.indent(textwrap.dedent(frames).strip("\n"), " " * 10) + "\n" if frames.strip() else ""
    return (
        "mapcan: 1\ndocument:\n  title: Тест\n  language: ru\nbuses:\n  - name: bus\n    protocol: can\n    devices:\n"
        "      - name: a\n        frames:\n" + block(frames_a)
        + "      - name: b\n        frames:" + ("\n" + block(frames_b) if frames_b.strip() else " []\n")
    )


def _map(text: str):
    res = loads(text, "t.yaml")
    assert res.map is not None, [d.format() for d in res.report.diagnostics]
    return res.map


def test_sender_and_receivers_resolved():
    bus = _map(CANOPEN).buses[0]
    frames = {f.name: f for f in bus.all_frames()}
    assert frames["node_command"].can_id == 0x205          # the ID is still from the receiver's node_id
    assert frames["node_command"].sender_name == "master"
    assert frames["node_command"].receiver_names == ["node"]
    assert frames["master_status"].sender_name == "master"
    assert frames["nmt"].sender_name == "master" and frames["nmt"].receiver_names == ["node"]
    assert [f.name for f in bus.received_by("node")] == ["nmt", "master_status", "node_command"]
    assert [f.name for f in bus.sent_by("master")] == ["nmt", "master_status", "node_command"]


def test_clean_map_has_no_exchange_diagnostics():
    c = codes(CANOPEN)
    assert not c & {"unknown-sender", "sender-mismatch", "rx-duplicate", "rx-no-sender", "duplicate-can-id"}


def test_raw_frame_with_foreign_sender_is_rx():
    f = _map(_can("[]", """
        - name: cmd
          id: 0x100
          dlc: 8
          sender: a
    """)).buses[0].devices[1].frames[0]
    assert f.direction == "rx" and f.sender_name == "a" and f.receiver_names == ["b"]


def test_unknown_sender():
    _, rep = run(_can("""
        - name: cmd
          id: 0x100
          dlc: 8
          sender: nobody
    """))
    [d] = [d for d in rep.diagnostics if d.code == "unknown-sender"]
    assert d.node[-1] == "sender"


def test_sender_mismatch():
    assert "sender-mismatch" in codes(_can("""
        - name: st
          id: 0x100
          dlc: 8
          direction: tx
          sender: b
    """))
    assert "sender-mismatch" in codes(_can("""
        - name: cmd
          id: 0x100
          dlc: 8
          direction: rx
          sender: a
    """))
    _, rep = run(_can("""
        - name: st
          id: 0x100
          dlc: 8
          receivers: [b, a]
    """))
    [d] = [d for d in rep.diagnostics if d.code == "sender-mismatch"]
    assert list(d.node[-2:]) == ["receivers", 1]


def test_rx_duplicate_replaces_duplicate_can_id():
    _, rep = run(_can("""
        - name: st
          id: 0x100
          dlc: 8
    """, """
        - name: st_in
          id: 0x100
          dlc: 8
          direction: rx
    """))
    c = rep.codes()
    assert "rx-duplicate" in c and "duplicate-can-id" not in c
    [d] = [d for d in rep.diagnostics if d.code == "rx-duplicate"]
    assert d.node[-1] == 0 and d.node[-3] == 1             # on the RX frame of device b
    # Two TX frames with one ID: still duplicate-can-id
    assert "duplicate-can-id" in codes(_can("""
        - name: st
          id: 0x100
          dlc: 8
    """, """
        - name: st2
          id: 0x100
          dlc: 8
    """))
    # An 11-bit and a 29-bit ID with the same number are different identifiers
    assert not {"duplicate-can-id", "rx-duplicate"} & codes(_can("""
        - name: std
          id: 0x100
          dlc: 8
    """, """
        - name: ext
          id: 0x100
          extended: true
          dlc: 8
    """))


def test_rx_no_sender_hint():
    _, rep = run(_can("[]", """
        - name: cmd
          id: 0x100
          dlc: 8
          direction: rx
    """))
    [d] = [d for d in rep.diagnostics if d.code == "rx-no-sender"]
    assert d.level == "info" and d.node[-1] == "sender"
    # CANopen RX frames without sender (the master is outside the map): no note
    assert "rx-no-sender" not in codes(CANOPEN.replace("            sender: master\n", ""))


def test_dbc_senders_and_receivers():
    m = _map(CANOPEN)
    db = cantools.database.load_string(bus_database(m, m.buses[0]).as_dbc_string(), "dbc")
    cmd = db.get_message_by_name("node_command")
    assert cmd.senders == ["master"]
    nmt = db.get_message_by_name("nmt")
    assert nmt.senders == ["master"]


def test_document_exchange_view():
    v = build_view(_map(CANOPEN), "ru")
    bus = v["buses"][0]
    master, node = bus["devices"]
    assert [(c["name"], c["peer"]) for c in node["receives"]] == [
        ("nmt", "MASTER 0x01"), ("master_status", "MASTER 0x01"), ("node_command", "MASTER 0x01")]
    assert [(c["name"], c["peer"]) for c in master["sends_other"]] == [
        ("nmt", "Широковещательные"), ("node_command", "NODE 0x05")]
    assert node["frames"][0]["sender"] == "MASTER 0x01"
    assert node["frames"][1]["sender"] == ""                # a TX frame's sender is obvious
    ex = bus["exchange"]
    assert ex["columns"] == ["MASTER 0x01", "NODE 0x05"]
    assert {r["name"]: r["cells"] for r in ex["rows"]} == {
        "nmt": ["TX", "RX"], "master_status": ["TX", "RX"], "node_status": ["RX", "TX"], "node_command": ["TX", "RX"]}
    md = render(_map(CANOPEN), "md")
    assert "**Принимает**" in md and "**Передаёт кадры других устройств**" in md
    assert "**Отправитель:** MASTER 0x01" in md


def test_diff_reports_sender_change():
    d = diff_maps(_map(CANOPEN), _map(CANOPEN.replace("            sender: master\n", "")))
    assert [(c.frame, c.field, c.old, c.new) for c in d.changes] == [("node_command", "sender", "master", None)]
