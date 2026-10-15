"""Command line of mapcan."""

from __future__ import annotations

import json
import shutil
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .diagnostics import Report
from .i18n import _
from .loader import LoadResult
from .validate import RULES, validate_file

app = typer.Typer(
    help=_("mapcan — CAN signal map in YAML → validation, documentation, code."),
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)
export_app = typer.Typer(help=_("Export documents and files for third-party tools."), no_args_is_help=True)
gen_app = typer.Typer(help=_("Code generation."), no_args_is_help=True)
import_app = typer.Typer(help=_("Import a map from other tools' formats."), no_args_is_help=True)
app.add_typer(export_app, name="export")
app.add_typer(gen_app, name="gen")
app.add_typer(import_app, name="import")

COLORS = {"error": typer.colors.RED, "warning": typer.colors.YELLOW, "info": typer.colors.BLUE}

MapArg = typer.Argument(..., exists=True, dir_okay=False, readable=True, help=_("Map YAML file."))
LangOpt = typer.Option(None, "--lang", help=_("Document language (ISO 639-1 code: ru, en, de…); defaults to the map's "
                                              "language."))
ForceOpt = typer.Option(False, "--force", help=_("Generate even if validation reports errors."))


class OutFormat(str, Enum):
    text = "text"
    json = "json"


def _print_report(report: Report, show_info: bool = False, stream=None) -> None:
    for d in report.sorted():
        if d.level == "info" and not show_info:
            continue
        typer.secho(d.format(), fg=COLORS[d.level], err=stream is None)


def _summary(report: Report) -> str:
    return _("errors: {errors}, warnings: {warnings}, notes: {infos}",
             errors=report.errors, warnings=report.warnings, infos=report.count("info"))


def _load_checked(path: Path, force: bool) -> LoadResult:
    res, report = validate_file(path)
    _print_report(report)
    if res.map is None or (report.errors and not force):
        typer.secho(_("Generation aborted: {summary}. Fix the errors (mapcan validate) or use --force.",
                      summary=_summary(report)), fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    return res


def _done(paths) -> None:
    for p in paths if isinstance(paths, (list, tuple)) else [paths]:
        typer.echo(f"→ {p}")


def _warn(message: str) -> None:
    typer.secho(message, fg=typer.colors.YELLOW, err=True)


def _default_out(path: Path, ext: str, out: Optional[Path]) -> Path:
    return out if out else Path(path.stem + ext)


@app.callback(invoke_without_command=True)
def _main(version: bool = typer.Option(False, "--version", help=_("Show the version."))) -> None:
    if version:
        typer.echo(f"mapcan {__version__}")
        raise typer.Exit()


# --------------------------------------------------------------------------- #


@app.command(help=_("Validate the map. Exit code 1 on errors (and on warnings with --strict)."))
def validate(
    path: Path = MapArg,
    strict: bool = typer.Option(False, "--strict", help=_("Treat warnings as errors.")),
    fmt: OutFormat = typer.Option(OutFormat.text, "--format", help=_("Output format.")),
    show_info: bool = typer.Option(False, "--info", help=_("Show info-level notes.")),
    disable: list[str] = typer.Option([], "--disable", help=_("Disable a rule (may be repeated).")),
) -> None:
    res, report = validate_file(path, disable)
    if fmt == OutFormat.json:
        typer.echo(report.to_json())
    else:
        _print_report(report, show_info, stream=sys.stdout)
        ok = report.errors == 0 and not (strict and report.warnings)
        typer.secho(("OK: " if ok else "FAIL: ") + _summary(report),
                    fg=typer.colors.GREEN if ok else typer.colors.RED)
    if report.errors or (strict and report.warnings):
        raise typer.Exit(1)


@app.command(help=_(
    "Browser-based editor (for servers and development; on a desktop, `mapcan app` is more convenient)."))
def serve(
    path: Optional[Path] = typer.Argument(
        None, exists=True, dir_okay=True, readable=True,
        help=_("Map to open, or a working folder. Without an argument, the start screen is shown.")),
    host: str = typer.Option("127.0.0.1", "--host", help=_("Address to listen on.")),
    port: Optional[int] = typer.Option(None, "--port", help=_("Port; defaults to 8765 or any free port.")),
    readonly: bool = typer.Option(False, "--readonly", help=_("View only, no saving.")),
    no_browser: bool = typer.Option(False, "--no-browser", help=_("Do not open a browser.")),
    token: Optional[str] = typer.Option(
        None, "--token", envvar="MAPCAN_TOKEN",
        help=_("Access token on a network address; a random one is generated if not given.")),
    no_auth: bool = typer.Option(
        False, "--no-auth", help=_("No token on a network address (behind a proxy that authenticates users).")),
) -> None:
    import secrets
    import webbrowser

    _need("web")
    from .launcher import DEFAULT_PORT, LOCAL_HOSTS, ServerThread, browser_url, pick_port
    from .web.app import create_app
    from .web.session import EditorSession

    local = host in LOCAL_HOSTS
    auth_token = None
    if not local and no_auth:
        typer.secho(_("Warning: the editor is reachable over the network ({host}) without authentication. Anyone who "
                      "opens the address can open and change files.", host=host),
                    fg=typer.colors.YELLOW, err=True)
    elif not local:
        auth_token = token or secrets.token_urlsafe(24)
    session, cwd = None, Path.cwd()
    if path is not None and path.is_dir():
        cwd = path
    elif path is not None:
        session = EditorSession(path, readonly=readonly)
    if port is None:
        port = pick_port(host, DEFAULT_PORT) if local else DEFAULT_PORT
    url = browser_url(host, port)
    if auth_token:
        from urllib.parse import quote

        url += f"?token={quote(auth_token)}"
    server = ServerThread(create_app(session, cwd=cwd.resolve(), readonly=readonly, check_updates=local,
                                     allowed_hosts=LOCAL_HOSTS if local else None, auth_token=auth_token),
                          host, port)
    try:
        server.start()
    except RuntimeError as e:
        typer.secho(_("Error: {error}", error=e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    typer.echo(_("mapcan {version}: {path} → {url}  (Ctrl+C to stop)",
                 version=__version__, path=path or cwd, url=url))
    if not no_browser:
        webbrowser.open(url)
    server.wait()


@app.command("app", help=_("Editor in its own window (pywebview); running it again opens the file in the existing "
                           "window."))
def app_cmd(
    path: Optional[Path] = typer.Argument(
        None, exists=True, dir_okay=True, readable=True,
        help=_("Map to open, or a working folder. Without an argument, the start screen is shown.")),
    browser: bool = typer.Option(False, "--browser", help=_("Open in a browser instead of the app window.")),
    readonly: bool = typer.Option(False, "--readonly", help=_("View only, no saving.")),
) -> None:
    _need("web")
    from .launcher import run

    raise typer.Exit(run(path, window=not browser, readonly=readonly))


@app.command(help=_("Language server (LSP) over stdio: validation and hints in VS Code and other editors."))
def lsp() -> None:
    _need("lsp")
    from .lsp.server import main as lsp_main

    lsp_main()


def _need(*extras: str) -> None:
    """Stop with a clear message when an optional part of mapcan is not installed (see extras.py)."""
    from .extras import MissingExtra, require

    try:
        require(*extras)
    except MissingExtra as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e


class DiffFormat(str, Enum):
    text = "text"
    md = "md"
    json = "json"


@app.command(help=_("Compare two versions of a map (frames, signals, values) and print a changelog."))
def diff(
    old: Path = typer.Argument(..., exists=True, dir_okay=False, help=_("Old version of the map.")),
    new: Path = typer.Argument(..., exists=True, dir_okay=False, help=_("New version of the map.")),
    fmt: DiffFormat = typer.Option(DiffFormat.text, "--format", help="text | md | json"),
    lang: Optional[str] = LangOpt,
) -> None:
    from .diff import diff_maps, render_diff
    from .loader import load

    maps = []
    for p in (old, new):
        res = load(p)
        if res.map is None:
            _print_report(res.report)
            typer.secho(_("{path}: the map could not be loaded", path=p), fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        maps.append(res.map)
    d = diff_maps(maps[0], maps[1], lang)
    typer.echo(render_diff(d, fmt.value, lang or maps[1].lang))


@app.command(help=_("Rewrite the former names of fields (deprecated-key) to the current ones, keeping comments and "
                    "layout. Included files are rewritten too."))
def migrate(
    paths: list[Path] = typer.Argument(..., exists=True, dir_okay=False, help=_("Map files.")),
    check: bool = typer.Option(False, "--check", help=_("Do not write; exit code 1 if a file has former names.")),
) -> None:
    from .web.yamlops import migrate_text

    outdated = []
    for f in _with_included(paths):
        raw, text = _read_map(f)
        new = migrate_text(text)
        if new == text:
            continue
        outdated.append(f)
        if check:
            typer.echo(_("{file}: former field names, run mapcan migrate", file=f))
        else:
            _write_map(f, raw, new)
    if not outdated:
        typer.echo(_("No former field names found."))
    elif check:
        raise typer.Exit(1)


@app.command(help=_("Write the keys of every node in one order (that of docs/format.md), keeping comments, "
                    "layout and number notation. Included files are formatted too."))
def fmt(
    paths: list[Path] = typer.Argument(..., exists=True, dir_okay=False, help=_("Map files.")),
    check: bool = typer.Option(False, "--check", help=_("Do not write; exit code 1 if a file is not formatted.")),
) -> None:
    from .fmt import FmtError, format_text

    unformatted, failed = [], False
    for f in _with_included(paths):
        raw, text = _read_map(f)
        try:
            new = format_text(text)
        except FmtError as e:
            typer.secho(f"{f}: {e}", fg=typer.colors.RED, err=True)
            failed = True
            continue
        if new == text:
            continue
        unformatted.append(f)
        if check:
            typer.echo(_("{file}: not formatted, run mapcan fmt", file=f))
        else:
            _write_map(f, raw, new)
    if failed or (check and unformatted):
        raise typer.Exit(1)
    if not unformatted:
        typer.echo(_("All files are formatted."))


def _with_included(paths: list[Path]) -> list[Path]:
    """The maps and the files they include."""
    from ruamel.yaml import YAML

    files: list[Path] = []
    for p in paths:
        if p not in files:
            files.append(p)
        try:
            data = YAML(typ="safe").load(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a broken file is reported by validate
            data = None
        for inc in data.get("include") or [] if isinstance(data, dict) else []:
            q = p.parent / str(inc)
            if q.is_file() and q not in files:
                files.append(q)
    return files


def _read_map(f: Path) -> tuple[str, str]:
    """The file's text as it is and with \\n line endings."""
    raw = f.read_bytes().decode("utf-8")
    return raw, raw.replace("\r\n", "\n")


def _write_map(f: Path, raw: str, new: str) -> None:
    # The file keeps its line endings
    f.write_bytes((new.replace("\n", "\r\n") if "\r\n" in raw else new).encode("utf-8"))
    _done(f)


@app.command(help=_("List validation rules."))
def rules() -> None:
    for code, (level, desc) in RULES.items():
        typer.echo(f"{code:24} {level:8} {_(desc)}")


@app.command(help=_("Print the format's JSON Schema (for IDE hints)."))
def schema(
    out: Optional[Path] = typer.Option(None, "-o", "--output", help=_("JSON Schema file.")),
    part: bool = typer.Option(False, "--part", help=_("Schema of a file included by a map (part_of).")),
) -> None:
    from .schema import json_schema

    text = json.dumps(json_schema(part), ensure_ascii=False, indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        _done(out)
    else:
        typer.echo(text)


class TemplateKind(str, Enum):
    pdf = "pdf"
    md = "md"
    html = "html"
    xlsx_style = "xlsx-style"


@app.command(help=_("List PDF templates or copy a built-in template to customize the layout."))
def template(
    kind: Optional[TemplateKind] = typer.Argument(None, help="pdf | md | html | xlsx-style"),
    out: Optional[Path] = typer.Option(None, "-o", "--output", help=_("Where to save the template copy.")),
    name: str = typer.Option("mapcan", "--name", help=_("Built-in PDF template (see --list).")),
    list_: bool = typer.Option(False, "--list", help=_("Show built-in PDF templates.")),
) -> None:
    from .export.pdf import PDF_TEMPLATE_ALIASES, PDF_TEMPLATES, TEMPLATES_DIR

    name = PDF_TEMPLATE_ALIASES.get(name, name)
    if list_ or kind is None:
        for t in PDF_TEMPLATES.values():
            typer.echo(f"{t.name:12} {_(t.title)}")
            typer.echo(f"{'':12} {_(t.description)}")
        return
    if out is None:
        raise typer.BadParameter(_("specify -o/--output"))
    base = Path(__file__).parent / "templates"
    out.parent.mkdir(parents=True, exist_ok=True)
    if kind == TemplateKind.pdf:
        if name not in PDF_TEMPLATES:
            raise typer.BadParameter(_("no template {name!r}; available: {known}", name=name,
                                       known=", ".join(PDF_TEMPLATES)))
        shutil.copyfile(PDF_TEMPLATES[name].path, out)
        lib = out.parent / "lib.typ"
        shutil.copyfile(TEMPLATES_DIR / "lib.typ", lib)    # shared elements, imported by the template
        _done([out, lib])
        return
    src = {"md": base / "document.md.j2", "html": base / "document.html.j2",
           "xlsx-style": base / "xlsx_style.yaml"}[kind.value]
    shutil.copyfile(src, out)
    _done(out)


# --------------------------------------------------------------------------- #


@export_app.command("xlsx", help=_("Excel: addressing, contents, bit maps, changes."))
def export_xlsx_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output"),
    style: Optional[Path] = typer.Option(None, "--style", exists=True, help=_("YAML file with styling.")),
    lang: Optional[str] = LangOpt,
    force: bool = ForceOpt,
) -> None:
    _need("xlsx")
    from .export.xlsx import XlsxStyle, export_xlsx

    res = _load_checked(path, force)
    _done(export_xlsx(res.map, _default_out(path, ".xlsx", out), XlsxStyle.load(style), lang))


@export_app.command("pdf", help=_("PDF via Typst: title page, contents, bit diagrams, tables; ESKD template."))
def export_pdf_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output"),
    template: Optional[str] = typer.Option(
        None, "--template",
        help=_("Built-in template (mapcan, gost-2.105) or a path to your own .typ.")),
    font_path: list[Path] = typer.Option([], "--font-path", help=_("Folder with additional fonts.")),
    lang: Optional[str] = LangOpt,
    force: bool = ForceOpt,
) -> None:
    _need("pdf")
    from .export.pdf import PdfError, export_pdf

    res = _load_checked(path, force)
    try:
        _done(export_pdf(res.map, _default_out(path, ".pdf", out), template, font_path, lang))
    except PdfError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from e


@export_app.command("md", help=_("Markdown for a README or wiki."))
def export_md_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output"),
    template: Optional[Path] = typer.Option(None, "--template", exists=True, help=_("Custom Jinja2 template.")),
    lang: Optional[str] = LangOpt,
    force: bool = ForceOpt,
) -> None:
    from .export.text import export_text

    res = _load_checked(path, force)
    _done(export_text(res.map, _default_out(path, ".md", out), "md", template, lang))


@export_app.command("html", help=_("Self-contained HTML page with search."))
def export_html_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output"),
    template: Optional[Path] = typer.Option(None, "--template", exists=True, help=_("Custom Jinja2 template.")),
    lang: Optional[str] = LangOpt,
    force: bool = ForceOpt,
) -> None:
    from .export.text import export_text

    res = _load_checked(path, force)
    _done(export_text(res.map, _default_out(path, ".html", out), "html", template, lang))


@export_app.command("dbc", help=_("DBC (one file per bus)."))
def export_dbc_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output",
                                       help=_(".dbc file (single bus) or a folder.")),
    bus: Optional[str] = typer.Option(None, "--bus", help=_("Only the given bus.")),
    force: bool = ForceOpt,
) -> None:
    from .export.dbc import export_dbc

    res = _load_checked(path, force)
    _done(export_dbc(res.map, out or Path("."), bus, warn=_warn))


@export_app.command("eds", help=_(
    "EDS (CiA 306) for every device of the CANopen buses: PDO objects and their mapping."))
def export_eds_cmd(
    path: Path = MapArg,
    out: Path = typer.Option(Path("."), "-o", "--output", help=_("Directory for the .eds files.")),
    bus: Optional[str] = typer.Option(None, "--bus", help=_("Only the given bus.")),
    force: bool = ForceOpt,
) -> None:
    from .export.eds import export_eds

    res = _load_checked(path, force)
    _done(export_eds(res.map, out, bus, warn=_warn))


@gen_app.command("c", help=_("C: #define IDs, enums, masks, structs, pack/unpack."))
def gen_c_cmd(
    path: Path = MapArg,
    out: Path = typer.Option(Path("."), "-o", "--output", help=_("Folder for .h/.c files.")),
    prefix: str = typer.Option("", "--prefix", help=_("Name prefix (e.g. ne_).")),
    bus: list[str] = typer.Option([], "--bus", help=_("Only the given buses.")),
    phys_type: str = typer.Option("float", "--phys-type", help=_(
        "Type of physical values: float (double only for fields longer than 24 bits), double, or int (integers "
        "in units of the factor's decimals, for MCUs without an FPU).")),
    device: list[str] = typer.Option([], "--device", help=_(
        "Code of one device instead of the buses: its frames, TX schedule, RX filters and dispatch "
        "(repeatable).")),
    devices: bool = typer.Option(False, "--devices", help=_("Code of every device instead of the buses.")),
    target: str = typer.Option("c", "--target", help=_(
        "c: the driver-independent code; zephyr: also an adapter to the Zephyr RTOS CAN API (struct can_frame, "
        "filters, TX schedule).")),
    force: bool = ForceOpt,
) -> None:
    from .codegen.c import PHYS_TYPES, TARGETS, generate_c, generate_c_devices

    for name, value, allowed in (("--phys-type", phys_type, PHYS_TYPES), ("--target", target, TARGETS)):
        if value not in allowed:
            raise typer.BadParameter(_("expected one of: {values}", values=", ".join(allowed)), param_hint=name)
    res = _load_checked(path, force)
    if device or devices:
        try:
            _done(generate_c_devices(res.map, out, device or None, prefix, bus or None, phys_type, target))
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint="--device") from e
        return
    _done(generate_c(res.map, out, prefix, bus or None, phys_type, target))


@gen_app.command("py", help=_("Python module with the same structures (for tests and test benches)."))
def gen_py_cmd(
    path: Path = MapArg,
    out: Path = typer.Option(Path("."), "-o", "--output", help=_("Folder for the modules.")),
    bus: list[str] = typer.Option([], "--bus", help=_("Only the given buses.")),
    device: list[str] = typer.Option([], "--device", help=_(
        "Module of one device instead of the buses, for a test bench standing in for it (repeatable).")),
    devices: bool = typer.Option(False, "--devices", help=_("Module of every device instead of the buses.")),
    force: bool = ForceOpt,
) -> None:
    from .codegen.py import generate_py, generate_py_devices

    res = _load_checked(path, force)
    if device or devices:
        try:
            _done(generate_py_devices(res.map, out, device or None, bus or None))
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint="--device") from e
        return
    _done(generate_py(res.map, out, bus or None))


@import_app.command("dbc", help=_("DBC → YAML map: nodes, frames, signals, value tables, transmission modes."))
def import_dbc_cmd(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help=_("DBC file.")),
    out: Optional[Path] = typer.Option(None, "-o", "--output", help=_("YAML map file; <name>.yaml by default.")),
    title: Optional[str] = typer.Option(None, "--title", help=_("Document title; the file name by default.")),
    lang: str = typer.Option("en", "--lang", help=_("Document language (ISO 639-1 code).")),
    force: bool = typer.Option(False, "--force", help=_("Overwrite an existing file.")),
) -> None:
    from .i18n import normalize_language
    from .importers.dbc import import_dbc

    target = _default_out(path, ".yaml", out)
    if target.exists() and not force:
        typer.secho(_("{path} already exists; give another -o or --force", path=target),
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    doc_lang = normalize_language(lang)
    if doc_lang is None:
        raise typer.BadParameter(_("unknown language: {language}", language=lang))
    text, warnings = import_dbc(path, title, doc_lang)
    for w in warnings:
        _warn(w)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _done(target)
    _res, report = validate_file(target)
    _print_report(report)
    typer.echo(_summary(report))


ALL_FORMATS = ["xlsx", "pdf", "md", "html", "dbc", "eds", "c", "py"]


@app.command(help=_("Validate the map and build all artifacts (for CI)."))
def build(
    path: Path = MapArg,
    out: Path = typer.Option(Path("build"), "-o", "--output", help=_("Output folder.")),
    formats: str = typer.Option(",".join(ALL_FORMATS), "--formats", help=_(
        "Comma-separated: ") + ",".join(ALL_FORMATS)),
    pdf_template: list[str] = typer.Option(
        [], "--pdf-template", help=_("PDF template (may be repeated; mapcan by default).")),
    force: bool = ForceOpt,
) -> None:
    from .codegen.c import generate_c
    from .codegen.py import generate_py
    from .export.dbc import export_dbc
    from .export.eds import export_eds
    from .export.text import export_text

    wanted = [f.strip() for f in formats.split(",") if f.strip()]
    unknown = set(wanted) - set(ALL_FORMATS)
    if unknown:
        raise typer.BadParameter(_("unknown formats: {formats}", formats=", ".join(sorted(unknown))))
    _need(*(f for f in ("xlsx", "pdf") if f in wanted))

    def export_xlsx(*a):
        from .export.xlsx import export_xlsx as x

        return x(*a)

    def export_pdf(*a):
        from .export.pdf import export_pdf as p

        return p(*a)

    res = _load_checked(path, force)
    m, stem = res.map, path.stem
    out.mkdir(parents=True, exist_ok=True)
    steps = {
        "xlsx": lambda: export_xlsx(m, out / f"{stem}.xlsx"),
        "pdf": lambda: [export_pdf(m, out / (f"{stem}.pdf" if len(pdf_template) <= 1 else f"{stem}-{t}.pdf"), t)
                        for t in (pdf_template or ["mapcan"])],
        "md": lambda: export_text(m, out / f"{stem}.md", "md"),
        "html": lambda: export_text(m, out / f"{stem}.html", "html"),
        "dbc": lambda: export_dbc(m, out / "dbc", warn=_warn),
        "eds": lambda: export_eds(m, out / "eds", warn=_warn),
        "c": lambda: generate_c(m, out / "c"),
        "py": lambda: generate_py(m, out / "py"),
    }
    for f in wanted:
        _done(steps[f]())


def main() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    app()


if __name__ == "__main__":
    main()
