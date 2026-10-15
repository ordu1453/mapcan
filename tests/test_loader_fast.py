"""The fast reading of maps through libyaml (loader._fast_load): the same values, positions and messages as
ruamel's loader, and ruamel's loader for what it does not read the same way."""

from __future__ import annotations

import time

import pytest

import mapcan.loader as L

from .conftest import DATA, ROOT

MAPS = sorted([*ROOT.glob("examples/**/*.yaml"), *DATA.glob("*.yaml")])

# Variants of each map: values whose reading differs between YAML 1.1 and 1.2, other alphabets, block scalars,
# soft fixes, line ends, a byte order mark, and what goes to ruamel's loader (aliases, merge keys, a duplicate
# key, a tag, a syntax error, a complex key).
VARIANTS = {
    "as is": lambda t: t,
    "scalars": lambda t: t + "\nextra: [1, 0x10, OFF, yes, '2', 1_000, 010, 2026-10-14, ~, .inf, 1:30]\n",
    "cyrillic": lambda t: t.replace("title:", "title: Тест —", 3),
    "literal": lambda t: t + "\nnotes: |\n  multi\n  line\n",
    "folded": lambda t: t + "\nnotes: >\n  folded\n  text\n",
    "fixes": lambda t: t.replace("factor: 0.", "factor: 0,", 1).replace("id: 0x", "id: 0х", 1),
    "crlf": lambda t: t.replace("\n", "\r\n"),
    "bom": lambda t: "﻿" + t,
    "alias": lambda t: t + "\na: &x 1\nb: *x\n",
    "merge": lambda t: t + "\nmerge: {<<: {k: 1}}\n",
    "duplicate": lambda t: t + "\nmapcan: 2\n",
    "tag": lambda t: t + "\ntagged: !!str 12\n",
    "syntax": lambda t: t + "\n  bad: [indent\n",
    "complex key": lambda t: t + "\n? [complex]\n: 1\n",
}


def _plain(x):
    if isinstance(x, dict):
        return {L._plain_scalar(k): _plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_plain(v) for v in x]
    v = L._plain_scalar(x)
    return str(v) if type(v).__name__ == "TaggedScalar" else v


def _read(text: str, name: str, fast: bool, monkeypatch) -> dict:
    with monkeypatch.context() as m:
        if not fast:
            m.setattr(L, "_fast_load", lambda t: None)
        r = L.loads(text, name)
    return {
        "raw": _plain(r.raw),
        "positions": dict(r.source.positions),
        "files": dict(r.source.files),
        "messages": [(d.level, d.code, d.message, d.line, d.column) for d in r.report.sorted()],
        "map": r.map.model_dump() if r.map is not None else None,
    }


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("path", MAPS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_same_as_ruamel(path, variant, monkeypatch):
    text = VARIANTS[variant](path.read_text(encoding="utf-8"))
    assert _read(text, str(path), True, monkeypatch) == _read(text, str(path), False, monkeypatch)


def test_yaml_1_2_values():
    raw, _marks = L._fast_load("a: [OFF, yes, on, 0x1F, 0o17, 1_000, 1.5, .nan, null, true, '7', 2026-10-14]\n")
    a = raw["a"]
    assert a[:3] == ["OFF", "yes", "on"]
    assert a[3:7] == [31, 15, 1000, 1.5]
    assert a[7] != a[7] and a[8:11] == [None, True, "7"]
    assert str(a[11]) == "2026-10-14"


@pytest.mark.parametrize("text", [
    "a: &x 1\nb: *x\n", "a: {<<: {k: 1}}\n", "a: 1\na: 2\n", "a: !!str 1\n", "a: [b\n", "? [k]\n: 1\n",
    "a: 1\n---\nb: 2\n",
])
def test_ruamel_reads_the_rest(text):
    assert L._fast_load(text) is None


def test_exclamation_inside_a_word_stays_fast():
    raw, _marks = L._fast_load("description: Warning! Hot\n")
    assert raw == {"description": "Warning! Hot"}


def test_positions_of_unknown_fields_do_not_depend_on_earlier_maps():
    # The known keys of a map were cached by id() of its source map, which a later map could reuse: an unknown
    # field then lost its position (1:1)
    text = (ROOT / "examples" / "minimal.yaml").read_text(encoding="utf-8") + "\nextra: 1\n"
    for other in MAPS:
        L.loads(other.read_text(encoding="utf-8"), str(other))
        d = next(d for d in L.loads(text, "m.yaml").report.sorted() if "'extra'" in d.message)
        assert (d.line, d.column) != (1, 1)


def test_a_large_map_is_read_fast():
    text = _large_map()
    assert L._fast_load(text) is not None
    start = time.perf_counter()
    result = L.loads(text, "big.yaml")
    elapsed = time.perf_counter() - start
    assert result.map is not None, [d.message for d in result.report.sorted()][:3]
    # ruamel's loader takes several times this budget; the fast one a fraction of it
    assert elapsed < 1.5, elapsed


def _large_map(frames: int = 300) -> str:
    lines = ["mapcan: 1", "document: {title: Big, language: en}", "buses:", "  - name: can1", "    protocol: can",
             "    devices:", "      - name: dev", "        frames:"]
    for f in range(frames):
        lines += [f"          - name: frame_{f}", f"            id: 0x{0x100 + f:X}", "            length: 8",
                  "            signals:"]
        for s in range(8):
            lines += [f"              - name: s_{f}_{s}", "                encoding: scaled",
                      f"                byte: {s}", "                byte_length: 1", "                factor: 0.5"]
    return "\n".join(lines) + "\n"


def test_a_large_map_is_analysed_fast():
    """The whole analysis of the language server (load, validation, node ranges), with a budget."""
    from mapcan.lsp import analysis as A

    text = _large_map()
    A.analyze(text, "big.yaml")
    start = time.perf_counter()
    a = A.analyze(text, "big.yaml")
    elapsed = time.perf_counter() - start
    assert a.map is not None and len(a.nodes) > 10000
    assert elapsed < 3, elapsed


def test_plain_scalars_share_one_loader(monkeypatch):
    """Reading a number does not make a new ruamel loader each time (it looks for plug-ins on disk)."""
    made = []
    make = L._make_yaml
    monkeypatch.setattr(L, "_make_yaml", lambda: made.append(1) or make())
    monkeypatch.setattr(L._SCALAR_YAML, "yaml", None, raising=False)
    L._plain_value.cache_clear()
    assert [L._plain_value(f"0x{v:X}") for v in range(0x500, 0x540)] == list(range(0x500, 0x540))
    assert len(made) <= 1


def test_gc_is_paused_while_reading_and_restored():
    import gc
    import threading

    seen = []
    with L.paused_gc():
        seen.append(gc.isenabled())
        with L.paused_gc():                       # nested, and in another thread at the same time
            t = threading.Thread(target=lambda: L.loads("mapcan: 1\n", "m.yaml"))
            t.start()
            t.join()
        seen.append(gc.isenabled())
    assert seen == [False, False] and gc.isenabled()
    gc.disable()
    try:
        with L.paused_gc():
            pass
        assert not gc.isenabled()                 # disabled before: left disabled
    finally:
        gc.enable()
