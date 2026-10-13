"""PDF templates (mapcan, ESKD; draft ESPD and GOST 7.32), company logo, requisites."""

from __future__ import annotations

import io
import re
import shutil

import openpyxl
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mapcan.cli import app as cli
from mapcan.export.pdf import DRAFT_PDF_TEMPLATES, PDF_TEMPLATES, PdfError, export_pdf, resolve_template
from mapcan.export.text import render
from mapcan.export.xlsx import export_xlsx
from mapcan.loader import load, loads
from mapcan.model import Person, Signatures
from mapcan.validate import check
from mapcan.web.app import create_app
from mapcan.web.session import EditorSession

from .conftest import DATA, REFERENCE

LOGO_PNG = DATA / "logo.png"          # neutral test logo
LOGO_SVG = DATA / "logo.svg"


def pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


def with_requisites(logo=LOGO_PNG):
    m = load(REFERENCE).map
    m.document.organization = "ООО «Пример»"
    d = m.document.print
    d.logo = str(logo) if logo else None
    d.designation = "АБВГ.468332.001 Д1"
    d.litera = "О1"
    d.city = "Москва"
    d.signatures = Signatures(developed="Иванов", checked="Петров", norm_control="Кузнецова", approved="Смирнов")
    d.approve = Person(position="Главный конструктор", name="А. А. Смирнов")
    d.agree = [Person(position="Начальник отдела", name="Б. Б. Орлов")]
    return m


def template_arg(name):
    """A built-in template by name, a draft one only by the path to the .typ."""
    return DRAFT_PDF_TEMPLATES[name].path if name in DRAFT_PDF_TEMPLATES else name


ALL_TEMPLATES = sorted([*PDF_TEMPLATES, *DRAFT_PDF_TEMPLATES])


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_template_with_requisites_and_logo(name, tmp_path):
    out = export_pdf(with_requisites(), tmp_path / f"{name}.pdf", template=template_arg(name))
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert pages(data) >= 10
    assert b"/Subtype /Image" in data or b"/Subtype/Image" in data, "логотип не попал в PDF"


@pytest.mark.parametrize("name", ALL_TEMPLATES)
def test_template_without_requisites(name, tmp_path):
    """GOST templates build also for a map without requisites and logo."""
    m = load(REFERENCE).map
    assert export_pdf(m, tmp_path / "x.pdf", template=template_arg(name)).read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize("name", ["mapcan", "gost-2.105"])
def test_svg_logo(name, tmp_path):
    data = export_pdf(with_requisites(LOGO_SVG), tmp_path / "x.pdf", template=name).read_bytes()
    assert data.startswith(b"%PDF")


def test_eskd_svg_pages_match_pdf(tmp_path):
    """Export page by page (svg) gives as many sheets as the PDF."""
    m = with_requisites()
    n = pages(export_pdf(m, tmp_path / "x.pdf", template="gost-2.105").read_bytes())
    export_pdf(m, tmp_path / "p.svg", template="gost-2.105", fmt="svg")
    assert len(list(tmp_path.glob("p-*.svg"))) == n


def test_resolve_template(tmp_path):
    assert resolve_template(None).name == "mapcan.typ"
    assert resolve_template("gost-2.105").name == "gost-2.105.typ"
    with pytest.raises(PdfError):            # draft templates are not available by name
        resolve_template("gost-7.32")
    assert resolve_template("canmap").name == "mapcan.typ"   # the name before the rename
    custom = tmp_path / "my.typ"
    custom.write_text("x", encoding="utf-8")
    assert resolve_template(custom) == custom
    with pytest.raises(PdfError):
        resolve_template("gost-9999")


def test_logo_validation(tmp_path):
    text = REFERENCE.read_text(encoding="utf-8").replace("  language: ru\n", "  language: ru\n  logo: nope.png\n", 1)
    rep = check(loads(text, str(tmp_path / "m.yaml")))
    assert "logo-missing" in rep.codes()
    text = text.replace("logo: nope.png", "logo: logo.bmp")
    assert "logo-format" in check(loads(text, str(tmp_path / "m.yaml"))).codes()


def test_logo_relative_to_map(tmp_path):
    shutil.copyfile(LOGO_PNG, tmp_path / "logo.png")
    text = REFERENCE.read_text(encoding="utf-8").replace("  language: ru\n", "  language: ru\n  logo: logo.png\n", 1)
    (tmp_path / "m.yaml").write_text(text, encoding="utf-8")
    res = load(tmp_path / "m.yaml")
    assert res.map.logo_path == tmp_path / "logo.png"
    assert "logo-missing" not in check(res).codes()


def test_logo_in_html_and_xlsx(tmp_path):
    m = with_requisites()
    assert 'class="logo" src="data:image/png;base64,' in render(m, "html")
    wb = openpyxl.load_workbook(export_xlsx(m, tmp_path / "x.xlsx"))
    assert len(wb["Сводка"]._images) == 1


def test_requisites_schema_roundtrip():
    text = REFERENCE.read_text(encoding="utf-8").replace("  language: ru\n", """  language: ru
  print:
    designation: АБВГ.468332.001 Д1
    litera: О1
    signatures: {developed: Иванов, norm_control: Кузнецова}
    approve: {position: Главный конструктор, name: А. А. Смирнов}
    agree:
      - {position: Начальник отдела, name: Б. Б. Орлов}
""", 1)
    res = loads(text, "t.yaml")
    assert res.map is not None, [d.format() for d in res.report.diagnostics]
    assert res.map.document.print.signatures.developed == "Иванов"


# --------------------------------------------------------------------------- CLI

runner = CliRunner()


def test_cli_template_list_and_copy(tmp_path):
    r = runner.invoke(cli, ["template", "--list"])
    assert r.exit_code == 0 and all(n in r.output for n in PDF_TEMPLATES)
    r = runner.invoke(cli, ["template", "pdf", "--name", "gost-2.105", "-o", str(tmp_path / "corp.typ")])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "corp.typ").is_file() and (tmp_path / "lib.typ").is_file()
    # a copied template builds as your own
    out = tmp_path / "x.pdf"
    r = runner.invoke(cli, ["export", "pdf", str(REFERENCE), "-o", str(out), "--template", str(tmp_path / "corp.typ")])
    assert r.exit_code == 0, r.output
    assert out.read_bytes().startswith(b"%PDF")


def test_cli_export_pdf_by_name(tmp_path):
    out = tmp_path / "x.pdf"
    r = runner.invoke(cli, ["export", "pdf", str(REFERENCE), "-o", str(out), "--template", "gost-2.105"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(cli, ["export", "pdf", str(REFERENCE), "-o", str(out), "--template", "gost-19"])
    assert r.exit_code == 2
    r = runner.invoke(cli, ["export", "pdf", str(REFERENCE), "-o", str(out), "--template", "nope"])
    assert r.exit_code == 2


def test_cli_build_several_templates(tmp_path):
    r = runner.invoke(cli, ["build", str(REFERENCE), "-o", str(tmp_path), "--formats", "pdf",
                            "--pdf-template", "mapcan", "--pdf-template", "gost-2.105"])
    assert r.exit_code == 0, r.output
    stem = REFERENCE.stem
    assert (tmp_path / f"{stem}-mapcan.pdf").is_file() and (tmp_path / f"{stem}-gost-2.105.pdf").is_file()


# --------------------------------------------------------------------------- web

@pytest.fixture
def client(tmp_path):
    p = tmp_path / "mapcan.yaml"
    shutil.copyfile(REFERENCE, p)
    with TestClient(create_app(EditorSession(p))) as c:
        yield c


def test_web_templates_and_export(client):
    t = client.get("/api/templates").json()
    assert [x["name"] for x in t["pdf"]] == list(PDF_TEMPLATES) and t["default"] == "mapcan"
    r = client.get("/api/export/pdf", params={"template": "gost-2.105", "download": "true"})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert 'filename="mapcan-gost-2.105.pdf"' in r.headers["content-disposition"]
    assert client.get("/api/export/pdf", params={"template": "nope"}).status_code == 400
    assert client.get("/api/export/pdf", params={"template": "gost-7.32"}).status_code == 400


def test_web_logo_upload(client, tmp_path):
    assert client.get("/api/logo").status_code == 404
    r = client.post("/api/logo", files={"file": ("logo.png", LOGO_PNG.read_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["data"]["document"]["print"]["logo"] == "mapcan-logo.png"
    assert (tmp_path / "mapcan-logo.png").read_bytes() == LOGO_PNG.read_bytes()
    assert "logo: mapcan-logo.png" in st["text"]
    img = client.get("/api/logo")
    assert img.status_code == 200 and img.content == LOGO_PNG.read_bytes()
    pdf = client.get("/api/export/pdf", params={"template": "gost-2.105"}).content
    assert b"/Subtype /Image" in pdf or b"/Subtype/Image" in pdf
    bad = client.post("/api/logo", files={"file": ("x.bmp", io.BytesIO(b"BM").getvalue(), "image/bmp")})
    assert bad.status_code == 400 and bad.json()["code"] == "logo-format"


def test_web_requisites_ops(client):
    r = client.post("/api/ops", json={"ops": [
        {"op": "set", "path": ["document", "print", "designation"], "value": "АБВГ.468332.001 Д1"},
        {"op": "set", "path": ["document", "print", "signatures", "developed"], "value": "Иванов"},
        {"op": "set", "path": ["document", "print", "approve", "position"], "value": "Главный конструктор"},
        {"op": "insert", "path": ["document", "print", "agree"], "value": {"position": "Нач. отдела", "name": "Орлов"}},
    ]})
    assert r.status_code == 200, r.text
    st = r.json()
    assert not [d for d in st["diagnostics"] if d["level"] == "error"]
    assert "  print:\n    designation: АБВГ.468332.001 Д1\n    signatures:\n      developed: Иванов" in st["text"]


# Maps of the examples; files the maps include are not maps
EXAMPLES = sorted(p for p in (REFERENCE.parent.parent.parent / "examples").rglob("*.yaml")
                  if re.search(r"^mapcan\s*:", p.read_text(encoding="utf-8"), re.MULTILINE)
                  and not re.search(r"^part_of\s*:", p.read_text(encoding="utf-8"), re.MULTILINE))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem if p.parent.name == "examples" else p.parent.name)
def test_build_every_example(path, tmp_path):
    """Every example builds in all formats and with all PDF templates."""
    r = runner.invoke(cli, ["build", str(path), "-o", str(tmp_path), *sum(
        (["--pdf-template", t] for t in PDF_TEMPLATES), [])])
    assert r.exit_code == 0, r.output
    for t in PDF_TEMPLATES:
        assert (tmp_path / f"{path.stem}-{t}.pdf").read_bytes().startswith(b"%PDF")
    for ext in ("xlsx", "md", "html"):
        assert (tmp_path / f"{path.stem}.{ext}").is_file()
    assert list((tmp_path / "c").glob("*.h")) and list((tmp_path / "dbc").glob("*.dbc"))


def test_generator_version_in_view():
    from mapcan import __version__
    from mapcan.docmodel import build_view

    m = load(REFERENCE).map
    assert build_view(m, "en")["document"]["generated_by"] == f"Generated by mapcan {__version__}"
    assert build_view(m, "ru")["document"]["generated_by"] == f"Сформировано mapcan {__version__}"
