"""Разбор аргументов командной строки и сценарии работы приложения."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt
from rich.rule import Rule
from rich.text import Text

from watthog import APP_NAME, APP_TAGLINE, REPO_URL, __version__, winapi
from watthog import constants as const
from watthog.config import Settings, load_settings, save_settings
from watthog.meter import PowerMeter
from watthog.session import MeasurementSession, Sample, SessionResult
from watthog.telemetry import TelemetryReader
from watthog.ui import menu as menu_ui
from watthog.ui.dashboard import LiveDashboard, console_is_tall_enough
from watthog.ui.report import hardware_panel, render_result, save_report
from watthog.ui.theme import build_console
from watthog.ui.widgets import format_watts

COMMAND_RUN = "run"
COMMAND_INFO = "info"
COMMAND_CONFIG = "config"
COMMAND_MENU = "menu"

_PLAIN_REPORT_EVERY_SECONDS = 5.0
_UNSUPPORTED_PLATFORM_EXIT_CODE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watthog",
        description=f"{APP_NAME} - {APP_TAGLINE}. Измеряет потребление системы в ваттах "
        "и считает расход за час, 10 часов, сутки и месяц.",
        epilog=f"Документация и релизы: {REPO_URL}",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=[COMMAND_RUN, COMMAND_INFO, COMMAND_CONFIG, COMMAND_MENU],
        default=None,
        help="run - сразу запустить замер, info - показать железо и источники, "
        "config - открыть настройки. Без команды запускается меню.",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        metavar="СЕК",
        help=f"длительность замера в секундах (по умолчанию {const.DEFAULT_DURATION_SECONDS})",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        metavar="СЕК",
        help=f"интервал между выборками (по умолчанию {const.DEFAULT_SAMPLE_INTERVAL})",
    )
    parser.add_argument("--tariff", type=float, metavar="ЦЕНА", help="цена киловатт-часа для расчёта затрат")
    parser.add_argument("--currency", metavar="ЗНАК", help="обозначение валюты в отчёте")
    parser.add_argument("--json", dest="json_path", type=Path, metavar="ФАЙЛ", help="сохранить отчёт в JSON")
    parser.add_argument("--no-save", action="store_true", help="не сохранять отчёт в каталог отчётов")
    parser.add_argument("--plain", action="store_true", help="без живой панели: только текстовый вывод")
    parser.add_argument("--save-config", action="store_true", help="записать переданные параметры в настройки")
    parser.add_argument("-V", "--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    winapi.enable_utf8_console()
    args = build_parser().parse_args(argv)

    console = build_console()
    if sys.platform == "darwin":
        console.print(
            Text(
                f"{APP_NAME} не поддерживает macOS: там нет ни RAPL, ни счётчиков PDH, "
                "и честно измерить систему нечем.",
                style="app.bad",
            )
        )
        return _UNSUPPORTED_PLATFORM_EXIT_CODE

    settings = _apply_overrides(load_settings(), args)
    if args.save_config:
        save_settings(settings)

    command = args.command or COMMAND_MENU
    if command == COMMAND_RUN:
        return _command_run(console, settings, args)
    if command == COMMAND_INFO:
        return _command_info(console, settings)
    if command == COMMAND_CONFIG:
        menu_ui.edit_settings(console, settings)
        return 0
    return _command_menu(console, settings, args)


def _apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    if args.duration is not None:
        settings = replace(settings, duration_seconds=int(args.duration))
    if args.interval is not None:
        settings = replace(settings, sample_interval=args.interval)
    if args.tariff is not None:
        settings = replace(settings, tariff_per_kwh=args.tariff)
    if args.currency:
        settings = replace(settings, currency=args.currency)
    if args.no_save:
        settings = replace(settings, save_reports=False)
    return settings.normalized()


def _command_run(console: Console, settings: Settings, args: argparse.Namespace) -> int:
    result = _measure(console, settings, plain=args.plain)
    if result is None:
        return 1
    render_result(console, result)
    _store_report(console, result, args.json_path)
    return 0


def _command_info(console: Console, settings: Settings) -> int:
    with TelemetryReader(settings) as reader:
        console.print(hardware_panel(reader.profile, reader.sources))
    return 0


def _command_menu(console: Console, settings: Settings, args: argparse.Namespace) -> int:
    console.print(menu_ui.banner(console))
    while True:
        try:
            choice = menu_ui.render_menu(console, settings)
        except (KeyboardInterrupt, EOFError):
            console.print()
            return 0

        if choice == menu_ui.MENU_EXIT:
            console.print(Text("До встречи.", style="app.muted"))
            return 0

        if choice in (menu_ui.MENU_RUN, menu_ui.MENU_RUN_CUSTOM):
            run_settings = settings
            if choice == menu_ui.MENU_RUN_CUSTOM:
                run_settings = replace(
                    settings, duration_seconds=menu_ui.ask_duration(console, settings.duration_seconds)
                )
            result = _measure(console, run_settings, plain=args.plain)
            if result is not None:
                render_result(console, result)
                _store_report(console, result, args.json_path)
        elif choice == menu_ui.MENU_SETTINGS:
            settings = menu_ui.edit_settings(console, settings)
        elif choice == menu_ui.MENU_HARDWARE:
            _command_info(console, settings)
        elif choice == menu_ui.MENU_ABOUT:
            console.print(menu_ui.about_panel())

        if not _pause(console):
            return 0


def _measure(console: Console, settings: Settings, plain: bool) -> SessionResult | None:
    duration = float(settings.duration_seconds)
    try:
        reader = TelemetryReader(settings)
        reader.open()
    except Exception as error:  # noqa: BLE001 - источники телеметрии разнородны
        console.print(Text(f"Не удалось открыть источники телеметрии: {error}", style="app.bad"))
        return None

    try:
        session = MeasurementSession(reader, PowerMeter(reader.profile, settings), settings)
        console.print(_run_header(reader, settings))

        use_live = not plain and console.is_terminal
        if use_live and not console_is_tall_enough(console):
            console.print(
                Text(
                    "Окно терминала низковато для живой панели, показываю текстовый вывод.",
                    style="app.warn",
                )
            )
            use_live = False

        if use_live:
            with LiveDashboard(console, reader.profile, settings, duration) as dashboard:
                return session.run(duration, dashboard.update)
        return session.run(duration, _plain_reporter(console))
    finally:
        reader.close()


def _run_header(reader: TelemetryReader, settings: Settings) -> Text:
    active = [source.name for source in reader.sources if source.active]
    return Text.assemble(
        ("Замер ", "app.muted"),
        (f"{settings.duration_seconds} с", "app.value"),
        (", шаг ", "app.muted"),
        (f"{settings.sample_interval:g} с", "app.value"),
        ("   ·   источники: ", "app.muted"),
        (", ".join(active) or "нет", "app.accent"),
    )


def _plain_reporter(console: Console):
    state = {"next_report": 0.0}

    def report(sample: Sample, duration: float) -> None:
        if sample.elapsed < state["next_report"] and sample.elapsed < duration:
            return
        state["next_report"] = sample.elapsed + _PLAIN_REPORT_EVERY_SECONDS
        console.print(
            Text.assemble(
                (f"{sample.elapsed:5.1f} с", "app.muted"),
                ("   ", ""),
                (f"{format_watts(sample.watts):>6} Вт", "app.value"),
                ("   ", ""),
                (f"ЦП {sample.telemetry.cpu_load * 100:3.0f}%", "app.muted"),
            )
        )

    return report


def _store_report(console: Console, result: SessionResult, json_path: Path | None) -> None:
    if json_path is not None:
        saved = save_report(result, json_path)
        _print_save_status(console, saved, json_path)
        return
    if not result.settings.save_reports:
        return
    saved = save_report(result)
    if saved is not None:
        console.print(Text(f"Отчёт сохранён: {saved}", style="app.muted"))


def _print_save_status(console: Console, saved: Path | None, requested: Path) -> None:
    if saved is None:
        console.print(Text(f"Не удалось записать отчёт в {requested}", style="app.bad"))
    else:
        console.print(Text(f"Отчёт сохранён: {saved}", style="app.ok"))


def _pause(console: Console) -> bool:
    console.print(Rule(style="app.border"))
    try:
        Prompt.ask("[app.muted]Enter - вернуться в меню[/app.muted]", default="", console=console, show_default=False)
    except (KeyboardInterrupt, EOFError):
        console.print()
        return False
    return True
