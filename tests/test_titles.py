"""Названия сигналов (title) в документах и сгенерированных файлах; DLC служебных кадров CANopen."""

from __future__ import annotations

import ast
import subprocess

import cantools
import pytest

from mapcan.codegen.c import generate_c
from mapcan.codegen.py import generate_py
from mapcan.docmodel import build_view
from mapcan.export.dbc import export_dbc
from mapcan.loader import loads

from .conftest import codes, one_bus
from .test_codegen import GCC

# Кириллица и символы, которые могли бы сломать комментарий C, строку Python или DBC
TRICKY = 'Напряжение */ "x" \\ """'

TITLED = one_bus(f"""
    - name: f
      id: 0x100
      dlc: 2
      signals:
        - name: volts
          title: '{TRICKY}'
          byte: 0
          factor: 0.5
          unit: V
        - name: state
          title: Состояние
          description: Режим работы
          byte: 1
          values: {{0: OFF, 1: ON}}
""", protocol="can")


@pytest.fixture(scope="module")
def cmap():
    res = loads(TITLED, "t.yaml")
    assert res.map is not None, res.report.diagnostics
    return res.map


def test_title_in_model(cmap):
    sig = cmap.buses[0].devices[0].frames[0].signals[0]
    assert sig.title == TRICKY


def test_documents_fall_back_to_title(cmap):
    view = build_view(cmap)
    frame = view["buses"][0]["devices"][0]["frames"][0]
    volts, state = frame["signals"]
    assert volts["description"] == TRICKY and volts["title"] == TRICKY
    assert state["description"] == "Режим работы" and state["title"] == "Состояние"


def test_python_module_compiles(cmap, tmp_path):
    [path] = generate_py(cmap, tmp_path)
    code = path.read_text(encoding="utf-8")
    tree = ast.parse(code)
    docs = [ast.get_docstring(n) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "volts_phys"]
    assert docs[0] == TRICKY + ", В"  # единица — на языке документа


@pytest.mark.skipif(GCC is None, reason="нет компилятора C")
def test_c_compiles(cmap, tmp_path):
    sources = [p for p in generate_c(cmap, tmp_path) if p.suffix == ".c"]
    header = sources[0].with_suffix(".h").read_text(encoding="utf-8")
    assert "Напряжение * /" in header
    for src in sources:
        r = subprocess.run([GCC, "-std=c99", "-Wall", "-Werror", "-fsyntax-only", str(src)],
                           cwd=tmp_path, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_dbc_keeps_cyrillic_title(cmap, tmp_path):
    warnings: list[str] = []
    [path] = export_dbc(cmap, tmp_path / "bus.dbc", warn=warnings.append)
    assert not warnings
    db = cantools.database.load_file(path, encoding="cp1251")
    msg = db.get_message_by_name("f")
    assert msg.get_signal_by_name("volts").comment == TRICKY
    # описание главнее названия
    assert msg.get_signal_by_name("state").comment == "Режим работы"


def test_canopen_service_frame_dlc_from_type():
    frames = """
        - name: hb
          type: heartbeat
        - name: sync_frame
          type: sync
    """
    res = loads(one_bus(frames), "t.yaml")
    hb, sync = res.map.buses[0].devices[0].frames
    assert (hb.dlc, sync.dlc) == (1, 0)
    assert "canopen-dlc" not in codes(one_bus(frames))
    # явно записанный dlc главнее и проверяется
    assert "canopen-dlc" in codes(one_bus("""
        - name: hb
          type: heartbeat
          dlc: 8
    """))
