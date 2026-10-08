"""Импорт DBC: карта без ошибок, а экспорт импортированной карты совпадает с исходным DBC."""

from __future__ import annotations

import cantools
import pytest
from typer.testing import CliRunner

from mapcan.cli import app
from mapcan.export.dbc import export_dbc
from mapcan.importers.dbc import import_dbc
from mapcan.loader import load, loads
from mapcan.validate import check

from .conftest import REFERENCE, ROOT

MAPS = [REFERENCE, ROOT / "examples" / "minimal.yaml", ROOT / "examples" / "j1939.yaml",
        ROOT / "examples" / "vehicle-can.yaml"]


def _signals(msg):
    return {s.name: (s.start, s.length, s.byte_order, s.is_signed, s.scale, s.offset, s.is_float,
                     sorted((s.choices or {}).keys()), s.is_multiplexer, s.multiplexer_ids)
            for s in msg.signals}


def _messages(db):
    return {m.frame_id: (m.name, m.length, m.is_extended_frame, m.senders, m.cycle_time, _signals(m))
            for m in db.messages}


@pytest.mark.parametrize("path", MAPS, ids=lambda p: p.stem)
def test_roundtrip(path, tmp_path):
    first = export_dbc(load(path).map, tmp_path / "first")
    for dbc in first:
        text, warnings = import_dbc(dbc)
        res = loads(text, "imported.yaml")
        report = check(res)
        assert res.map is not None and not report.errors, [d.format() for d in report.diagnostics]
        assert not warnings
        (again,) = export_dbc(res.map, tmp_path / "again" / dbc.name)
        a, b = cantools.database.load_file(str(dbc)), cantools.database.load_file(str(again))
        assert _messages(b) == _messages(a)


DBC = '''VERSION ""

NS_ :

BS_:

BU_: ECU TESTER

BO_ 256 Status: 4 ECU
 SG_ Mode : 0|8@1+ (1,0) [0|0] "" TESTER
 SG_ Ready : 8|1@1+ (1,0) [0|0] "" TESTER
 SG_ Speed : 23|16@0+ (0.5,0) [0|1000] "km/h" TESTER

BO_ 2566844672 Command: 8 TESTER
 SG_ Value : 0|32@1- (1,0) [0|0] "" ECU

BO_ 512 Unknown: 1 OTHER
 SG_ Byte0 : 0|8@1+ (1,0) [0|0] "" ECU

CM_ BU_ ECU "Engine unit";
CM_ SG_ 256 Mode "Operating mode";
BA_DEF_ BO_ "GenMsgSendType" ENUM "Cyclic","Spontaneous","OnRequest","NoMsgSendType";
BA_DEF_DEF_ "GenMsgSendType" "NoMsgSendType";
BA_ "GenMsgSendType" BO_ 2566844672 1;
VAL_ 256 Mode 0 "Off" 1 "Not available" 2 "3rd state";
'''


def test_import_details(tmp_path):
    p = tmp_path / "car.dbc"
    p.write_text(DBC, encoding="utf-8")
    text, warnings = import_dbc(p, title="Car")
    res = loads(text, "car.yaml")
    assert res.map is not None and not check(res).errors, text
    bus = res.map.buses[0]
    assert (bus.name, bus.protocol) == ("car", "can")
    ecu, tester = bus.devices
    assert ecu.title == "Engine unit" and tester.name == "TESTER"
    status = ecu.frames[0]
    assert (status.can_id, status.dlc, status.receivers) == (0x100, 4, ["TESTER"])
    sig = {s.name: s for s in status.signals}
    assert sig["Mode"].encoding == "enum" and sig["Mode"].description == "Operating mode"
    # Имена значений — идентификаторы; исходный текст — в описании
    names = {k: (v if isinstance(v, str) else v.name) for k, v in sig["Mode"].values.items()}
    assert names == {0: "OFF", 1: "NOT_AVAILABLE", 2: "V_3RD_STATE"}
    assert sig["Mode"].values[1].description == "Not available"
    assert sig["Ready"].encoding == "flag" and sig["Ready"].bit_length == 1
    speed = sig["Speed"]
    assert (speed.encoding, speed.byte_order, speed.factor, speed.unit) == ("scaled", "big_endian", 0.5, "km/h")
    assert (speed.start_bit, speed.bit_length) == (24, 16)      # MSB в бите 23, байты 2..3
    command = tester.frames[0]
    assert command.extended and command.can_id == 0x18FEF100 and command.trigger == "event"
    assert command.signals[0].signed
    # Кадр без известного отправителя — на шине, с предупреждением
    assert [f.name for f in bus.frames] == ["Unknown"] and any("OTHER" in w for w in warnings)


def test_import_cli(tmp_path):
    p = tmp_path / "car.dbc"
    p.write_text(DBC, encoding="utf-8")
    out = tmp_path / "car.yaml"
    run = CliRunner().invoke
    r = run(app, ["import", "dbc", str(p), "-o", str(out)])
    assert r.exit_code == 0 and out.is_file() and "errors: 0" in r.stdout
    assert run(app, ["import", "dbc", str(p), "-o", str(out)]).exit_code == 1      # не перезаписывает
    assert run(app, ["import", "dbc", str(p), "-o", str(out), "--force", "--lang", "de"]).exit_code == 0
    assert "language: de" in out.read_text(encoding="utf-8")
