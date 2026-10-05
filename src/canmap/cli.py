"""Командная строка canmap."""

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
from .loader import LoadResult
from .validate import RULES, validate_file

app = typer.Typer(
    help="canmap — карта сигналов CAN в YAML → проверка, документация, код.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)
export_app = typer.Typer(help="Экспорт документов и файлов для сторонних инструментов.", no_args_is_help=True)
gen_app = typer.Typer(help="Генерация кода.", no_args_is_help=True)
app.add_typer(export_app, name="export")
app.add_typer(gen_app, name="gen")

COLORS = {"error": typer.colors.RED, "warning": typer.colors.YELLOW, "info": typer.colors.BLUE}

MapArg = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="YAML-файл карты.")
LangOpt = typer.Option(None, "--lang", help="Язык документа (ru/en); по умолчанию из карты.")
ForceOpt = typer.Option(False, "--force", help="Генерировать, даже если есть ошибки проверки.")


class OutFormat(str, Enum):
    text = "text"
    json = "json"


def _print_report(report: Report, show_info: bool = False, stream=None) -> None:
    for d in report.sorted():
        if d.level == "info" and not show_info:
            continue
        typer.secho(d.format(), fg=COLORS[d.level], err=stream is None)


def _summary(report: Report) -> str:
    return (f"ошибок: {report.errors}, предупреждений: {report.warnings}, "
            f"замечаний: {report.count('info')}")


def _load_checked(path: Path, force: bool) -> LoadResult:
    res, report = validate_file(path)
    _print_report(report)
    if res.map is None or (report.errors and not force):
        typer.secho(f"Генерация прервана: {_summary(report)}. "
                    "Исправьте ошибки (canmap validate) или используйте --force.",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    return res


def _done(paths) -> None:
    for p in paths if isinstance(paths, (list, tuple)) else [paths]:
        typer.echo(f"→ {p}")


def _default_out(path: Path, ext: str, out: Optional[Path]) -> Path:
    return out if out else Path(path.stem + ext)


@app.callback(invoke_without_command=True)
def _main(version: bool = typer.Option(False, "--version", help="Показать версию.")) -> None:
    if version:
        typer.echo(f"canmap {__version__}")
        raise typer.Exit()


# --------------------------------------------------------------------------- #


@app.command()
def validate(
    path: Path = MapArg,
    strict: bool = typer.Option(False, "--strict", help="Считать предупреждения ошибками."),
    fmt: OutFormat = typer.Option(OutFormat.text, "--format", help="Формат вывода."),
    show_info: bool = typer.Option(False, "--info", help="Показывать замечания уровня info."),
    disable: list[str] = typer.Option([], "--disable", help="Отключить правило (можно несколько раз)."),
) -> None:
    """Проверить карту. Код возврата 1 при ошибках (и предупреждениях с --strict)."""
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


@app.command()
def serve(
    path: Optional[Path] = typer.Argument(
        None, exists=True, dir_okay=True, readable=True,
        help="Карта для открытия или рабочая папка. Без аргумента — стартовый экран."),
    host: str = typer.Option("127.0.0.1", "--host", help="Адрес для прослушивания."),
    port: Optional[int] = typer.Option(None, "--port", help="Порт; по умолчанию 8765 или свободный."),
    readonly: bool = typer.Option(False, "--readonly", help="Только просмотр, без сохранения."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Не открывать браузер."),
) -> None:
    """Веб-редактор в браузере (для сервера и разработки; на рабочем месте удобнее `canmap app`)."""
    import webbrowser

    from .launcher import DEFAULT_PORT, LOCAL_HOSTS, ServerThread, browser_url, pick_port
    from .web.app import create_app
    from .web.session import EditorSession

    local = host in LOCAL_HOSTS
    if not local:
        typer.secho(f"Внимание: редактор доступен по сети ({host}) без аутентификации. "
                    "Любой, кто откроет адрес, сможет открывать и менять файлы.",
                    fg=typer.colors.YELLOW, err=True)
    session, cwd = None, Path.cwd()
    if path is not None and path.is_dir():
        cwd = path
    elif path is not None:
        session = EditorSession(path, readonly=readonly)
    if port is None:
        port = pick_port(host, DEFAULT_PORT) if local else DEFAULT_PORT
    url = browser_url(host, port)
    server = ServerThread(create_app(session, cwd=cwd.resolve(), readonly=readonly, check_updates=local),
                          host, port)
    try:
        server.start()
    except RuntimeError as e:
        typer.secho(f"Ошибка: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    typer.echo(f"canmap {__version__}: {path or cwd} → {url}  (Ctrl+C — остановить)")
    if not no_browser:
        webbrowser.open(url)
    server.wait()


@app.command("app")
def app_cmd(
    path: Optional[Path] = typer.Argument(
        None, exists=True, dir_okay=True, readable=True,
        help="Карта для открытия или рабочая папка. Без аргумента — стартовый экран."),
    browser: bool = typer.Option(False, "--browser", help="Открыть в браузере вместо окна приложения."),
    readonly: bool = typer.Option(False, "--readonly", help="Только просмотр, без сохранения."),
) -> None:
    """Редактор в отдельном окне (pywebview); повторный запуск открывает файл в уже запущенном окне."""
    from .launcher import run

    raise typer.Exit(run(path, window=not browser, readonly=readonly))


class DiffFormat(str, Enum):
    text = "text"
    md = "md"
    json = "json"


@app.command()
def diff(
    old: Path = typer.Argument(..., exists=True, dir_okay=False, help="Старая версия карты."),
    new: Path = typer.Argument(..., exists=True, dir_okay=False, help="Новая версия карты."),
    fmt: DiffFormat = typer.Option(DiffFormat.text, "--format", help="text | md | json"),
    lang: Optional[str] = LangOpt,
) -> None:
    """Сравнить две версии карты (кадры, сигналы, значения) и вывести changelog."""
    from .diff import diff_maps, render_diff
    from .loader import load

    maps = []
    for p in (old, new):
        res = load(p)
        if res.map is None:
            _print_report(res.report)
            typer.secho(f"{p}: карта не загружена", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        maps.append(res.map)
    d = diff_maps(maps[0], maps[1], lang)
    typer.echo(render_diff(d, fmt.value, lang or maps[1].lang))


@app.command()
def rules() -> None:
    """Список правил проверки."""
    for code, (level, desc) in RULES.items():
        typer.echo(f"{code:24} {level:8} {desc}")


@app.command()
def schema(out: Optional[Path] = typer.Option(None, "-o", "--output", help="Файл JSON Schema.")) -> None:
    """Вывести JSON Schema формата (для подсказок в IDE)."""
    from .schema import json_schema

    text = json.dumps(json_schema(), ensure_ascii=False, indent=2)
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


@app.command()
def template(
    kind: Optional[TemplateKind] = typer.Argument(None, help="pdf | md | html | xlsx-style"),
    out: Optional[Path] = typer.Option(None, "-o", "--output", help="Куда сохранить копию шаблона."),
    name: str = typer.Option("canmap", "--name", help="Встроенный PDF-шаблон (см. --list)."),
    list_: bool = typer.Option(False, "--list", help="Показать встроенные шаблоны PDF."),
) -> None:
    """Список шаблонов PDF или копия встроенного шаблона для правки (своё оформление)."""
    from .export.pdf import PDF_TEMPLATES, TEMPLATES_DIR

    if list_ or kind is None:
        for t in PDF_TEMPLATES.values():
            typer.echo(f"{t.name:12} {t.title}")
            typer.echo(f"{'':12} {t.description}")
        return
    if out is None:
        raise typer.BadParameter("укажите -o/--output")
    base = Path(__file__).parent / "templates"
    out.parent.mkdir(parents=True, exist_ok=True)
    if kind == TemplateKind.pdf:
        if name not in PDF_TEMPLATES:
            raise typer.BadParameter(f"нет шаблона {name!r}; доступны: {', '.join(PDF_TEMPLATES)}")
        shutil.copyfile(PDF_TEMPLATES[name].path, out)
        lib = out.parent / "lib.typ"
        shutil.copyfile(TEMPLATES_DIR / "lib.typ", lib)    # общие элементы, импортируются шаблоном
        _done([out, lib])
        return
    src = {"md": base / "document.md.j2", "html": base / "document.html.j2",
           "xlsx-style": base / "xlsx_style.yaml"}[kind.value]
    shutil.copyfile(src, out)
    _done(out)


# --------------------------------------------------------------------------- #


@export_app.command("xlsx")
def export_xlsx_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output"),
    style: Optional[Path] = typer.Option(None, "--style", exists=True, help="YAML с оформлением."),
    lang: Optional[str] = LangOpt,
    force: bool = ForceOpt,
) -> None:
    """Excel: адресация, содержание, битовые карты, изменения."""
    from .export.xlsx import XlsxStyle, export_xlsx

    res = _load_checked(path, force)
    _done(export_xlsx(res.map, _default_out(path, ".xlsx", out), XlsxStyle.load(style), lang))


@export_app.command("pdf")
def export_pdf_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output"),
    template: Optional[str] = typer.Option(
        None, "--template",
        help="Встроенный шаблон (canmap, gost-2.105, gost-19, gost-7.32) или путь к своему .typ."),
    font_path: list[Path] = typer.Option([], "--font-path", help="Каталог с дополнительными шрифтами."),
    lang: Optional[str] = LangOpt,
    force: bool = ForceOpt,
) -> None:
    """PDF через Typst: титул, оглавление, битовые диаграммы, таблицы; шаблоны ГОСТ."""
    from .export.pdf import PdfError, export_pdf

    res = _load_checked(path, force)
    try:
        _done(export_pdf(res.map, _default_out(path, ".pdf", out), template, font_path, lang))
    except PdfError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from e


@export_app.command("md")
def export_md_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output"),
    template: Optional[Path] = typer.Option(None, "--template", exists=True, help="Свой Jinja2-шаблон."),
    lang: Optional[str] = LangOpt,
    force: bool = ForceOpt,
) -> None:
    """Markdown для README/вики."""
    from .export.text import export_text

    res = _load_checked(path, force)
    _done(export_text(res.map, _default_out(path, ".md", out), "md", template, lang))


@export_app.command("html")
def export_html_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output"),
    template: Optional[Path] = typer.Option(None, "--template", exists=True, help="Свой Jinja2-шаблон."),
    lang: Optional[str] = LangOpt,
    force: bool = ForceOpt,
) -> None:
    """Самодостаточная HTML-страница с поиском."""
    from .export.text import export_text

    res = _load_checked(path, force)
    _done(export_text(res.map, _default_out(path, ".html", out), "html", template, lang))


@export_app.command("dbc")
def export_dbc_cmd(
    path: Path = MapArg,
    out: Optional[Path] = typer.Option(None, "-o", "--output",
                                       help="Файл .dbc (одна шина) или каталог."),
    bus: Optional[str] = typer.Option(None, "--bus", help="Только указанная шина."),
    force: bool = ForceOpt,
) -> None:
    """DBC (по файлу на шину)."""
    from .export.dbc import export_dbc

    res = _load_checked(path, force)
    _done(export_dbc(res.map, out or Path("."), bus))


@gen_app.command("c")
def gen_c_cmd(
    path: Path = MapArg,
    out: Path = typer.Option(Path("."), "-o", "--output", help="Каталог для .h/.c."),
    prefix: str = typer.Option("", "--prefix", help="Префикс имён (напр. ne_)."),
    bus: list[str] = typer.Option([], "--bus", help="Только указанные шины."),
    force: bool = ForceOpt,
) -> None:
    """C: #define ID, enum, маски, структуры, pack/unpack."""
    from .codegen.c import generate_c

    res = _load_checked(path, force)
    _done(generate_c(res.map, out, prefix, bus or None))


@gen_app.command("py")
def gen_py_cmd(
    path: Path = MapArg,
    out: Path = typer.Option(Path("."), "-o", "--output", help="Каталог для модулей."),
    bus: list[str] = typer.Option([], "--bus", help="Только указанные шины."),
    force: bool = ForceOpt,
) -> None:
    """Python-модуль с теми же структурами (для тестов и стендов)."""
    from .codegen.py import generate_py

    res = _load_checked(path, force)
    _done(generate_py(res.map, out, bus or None))


ALL_FORMATS = ["xlsx", "pdf", "md", "html", "dbc", "c", "py"]


@app.command()
def build(
    path: Path = MapArg,
    out: Path = typer.Option(Path("build"), "-o", "--output", help="Каталог результатов."),
    formats: str = typer.Option(",".join(ALL_FORMATS), "--formats", help="Через запятую: " + ",".join(ALL_FORMATS)),
    pdf_template: list[str] = typer.Option(
        [], "--pdf-template", help="Шаблон PDF (можно несколько раз; по умолчанию canmap)."),
    force: bool = ForceOpt,
) -> None:
    """Проверить карту и собрать все артефакты (для CI)."""
    from .codegen.c import generate_c
    from .codegen.py import generate_py
    from .export.dbc import export_dbc
    from .export.pdf import export_pdf
    from .export.text import export_text
    from .export.xlsx import export_xlsx

    wanted = [f.strip() for f in formats.split(",") if f.strip()]
    unknown = set(wanted) - set(ALL_FORMATS)
    if unknown:
        raise typer.BadParameter(f"неизвестные форматы: {', '.join(sorted(unknown))}")
    res = _load_checked(path, force)
    m, stem = res.map, path.stem
    out.mkdir(parents=True, exist_ok=True)
    steps = {
        "xlsx": lambda: export_xlsx(m, out / f"{stem}.xlsx"),
        "pdf": lambda: [export_pdf(m, out / (f"{stem}.pdf" if len(pdf_template) <= 1 else f"{stem}-{t}.pdf"), t)
                        for t in (pdf_template or ["canmap"])],
        "md": lambda: export_text(m, out / f"{stem}.md", "md"),
        "html": lambda: export_text(m, out / f"{stem}.html", "html"),
        "dbc": lambda: export_dbc(m, out / "dbc"),
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
