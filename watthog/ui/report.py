"""Итоговый отчёт: таблицы результата, прогнозы и сохранение на диск."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from watthog import AUTHOR_TELEGRAM, REPO_URL, __version__
from watthog import constants as const
from watthog.config import reports_directory
from watthog.formatting import format_money
from watthog.inventory import HardwareProfile
from watthog.meter import ACCURACY_DETAILS
from watthog.projections import Projection, build_projections, consumption_tier
from watthog.session import SessionResult
from watthog.telemetry import SourceStatus
from watthog.ui.theme import gradient_color
from watthog.ui.widgets import big_number, format_kwh, format_watts, gauge

_HIGHLIGHT_SCALE_WATTS = 600.0
_STATISTICS_VALUE_WIDTH = 12
_COMPONENT_LABEL_WIDTH = 10
_REPORT_BAR_WIDTH = 10


def render_result(console: Console, result: SessionResult) -> None:
    """Печатает полный отчёт по завершённому замеру."""
    projections = build_projections(result.average_watts, result.settings.tariff_per_kwh)

    console.print()
    console.print(_headline(result))
    console.print()
    console.print(_highlights(result, projections))
    console.print()

    columns = Table.grid(expand=True, padding=(0, 1))
    columns.add_column(ratio=1)
    columns.add_column(ratio=1)
    columns.add_row(_statistics_panel(result), _breakdown_panel(result))
    console.print(columns)
    console.print()
    console.print(_projections_panel(result, projections))

    if result.settings.tariff_per_kwh <= 0.0:
        console.print(
            Text(
                "Подсказка: задайте тариф за кВт·ч в настройках, и отчёт покажет расход в деньгах.",
                style="app.hint",
            )
        )
    console.print(_footer())


def _headline(result: SessionResult) -> RenderableType:
    tier_label, tier_style = consumption_tier(result.average_watts)
    color = gradient_color(min(1.0, result.average_watts / _HIGHLIGHT_SCALE_WATTS))

    value = Table.grid(padding=(0, 1))
    value.add_column()
    value.add_column()
    value.add_row(big_number(format_watts(result.average_watts), color), Text("\n\n\nВт", style="app.unit"))

    caption = Text.assemble(
        ("средняя мощность из розетки за ", "app.muted"),
        (f"{result.duration_seconds:.0f} с", "app.value"),
        ("   ·   ", "app.muted"),
        (tier_label, tier_style),
    )
    title = "[app.label]Результат замера" + (
        "  [app.warn](замер прерван)" if result.interrupted else ""
    )
    return Panel(
        Group(Align.center(value), Align.center(caption)),
        title=title,
        border_style="app.border",
        padding=(1, 2),
    )


def _highlights(result: SessionResult, projections: tuple[Projection, ...]) -> RenderableType:
    by_hours = {projection.hours: projection for projection in projections}
    grid = Table.grid(expand=True, padding=(0, 2))
    cards = [
        _highlight_card(by_hours[hours], result.settings.currency)
        for hours in const.HIGHLIGHTED_PROJECTION_HOURS
        if hours in by_hours
    ]
    for _ in cards:
        grid.add_column(ratio=1)
    grid.add_row(*cards)
    return grid


def _highlight_card(projection: Projection, currency: str) -> Panel:
    lines = [
        Text.assemble(
            (format_kwh(projection.kwh), "app.title"),
            (" кВт·ч", "app.unit"),
        )
    ]
    if projection.cost is not None:
        lines.append(
            Text.assemble((f"{format_money(projection.cost)} ", "app.value"), (currency, "app.unit"))
        )
    return Panel(
        Group(*lines),
        title=f"[app.label]За {projection.label}",
        border_style="app.accent",
        padding=(0, 2),
    )


def _statistics_panel(result: SessionResult) -> Panel:
    table = Table.grid(expand=True, padding=(0, 1))
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="right", width=_STATISTICS_VALUE_WIDTH, no_wrap=True)

    rows = (
        ("Длительность", f"{result.duration_seconds:.1f} с"),
        ("Выборок", str(result.sample_count)),
        ("Средняя мощность", f"{format_watts(result.average_watts)} Вт"),
        ("Минимум", f"{format_watts(result.minimum_watts)} Вт"),
        ("Максимум", f"{format_watts(result.maximum_watts)} Вт"),
        ("Медиана", f"{format_watts(result.median_watts)} Вт"),
        ("95-й перцентиль", f"{format_watts(result.percentile95_watts)} Вт"),
        ("Энергия за замер", f"{result.energy_wh:.3f} Вт·ч"),
        ("Железо без потерь", f"{format_watts(result.average_dc_watts)} Вт"),
        ("Точность", result.accuracy.value),
    )
    for label, value in rows:
        table.add_row(Text(label, style="app.muted"), Text(value, style="app.value"))

    body = Group(table, Text(""), Text(ACCURACY_DETAILS[result.accuracy], style="app.hint"))
    return Panel(body, title="[app.label]Статистика", border_style="app.border", padding=(0, 1))


def _breakdown_panel(result: SessionResult) -> Panel:
    breakdown = result.average_breakdown
    total = breakdown.total_ac

    table = Table.grid(expand=True, padding=(0, 1))
    table.add_column(justify="left", width=_COMPONENT_LABEL_WIDTH, no_wrap=True)
    table.add_column(justify="right", width=6, no_wrap=True)
    table.add_column(justify="right", width=4, no_wrap=True)
    table.add_column(justify="left", ratio=1)

    for label, watts in breakdown.components():
        if watts <= 0.0:
            continue
        share = watts / total if total > 0 else 0.0
        table.add_row(
            Text(label, style="app.label"),
            Text(format_watts(watts), style="app.value"),
            Text(f"{share * 100:.0f}%", style="app.muted"),
            gauge(share, 1.0, _REPORT_BAR_WIDTH),
        )
    return Panel(table, title="[app.label]Средняя разбивка", border_style="app.border", padding=(0, 1))


def _projections_panel(result: SessionResult, projections: tuple[Projection, ...]) -> Panel:
    currency = result.settings.currency
    tariff = result.settings.tariff_per_kwh

    table = Table(expand=True, box=None, pad_edge=False, show_edge=False)
    table.add_column("Если работать так же", style="app.label")
    table.add_column("Энергия", justify="right", style="app.value")
    if tariff > 0.0:
        table.add_column(f"Стоимость, {currency}", justify="right", style="app.accent")

    for projection in projections:
        row = [projection.label, f"{format_kwh(projection.kwh)} кВт·ч"]
        if tariff > 0.0:
            row.append(format_money(projection.cost))
        table.add_row(*row)

    subtitle = Text.assemble(
        ("при средней мощности ", "app.muted"),
        (f"{format_watts(result.average_watts)} Вт", "app.value"),
        (" из розетки", "app.muted"),
    )
    return Panel(
        Group(table, Text(""), subtitle),
        title="[app.label]Прогноз расхода",
        border_style="app.border",
        padding=(0, 1),
    )


def _footer() -> RenderableType:
    return Group(
        Rule(style="app.border"),
        Text.assemble(
            ("WattHog ", "app.title"),
            (f"v{__version__}", "app.muted"),
            ("   ·   автор ", "app.muted"),
            (AUTHOR_TELEGRAM, "app.accent"),
            ("   ·   ", "app.muted"),
            (REPO_URL, "app.muted"),
        ),
    )


def hardware_panel(profile: HardwareProfile, sources: tuple[SourceStatus, ...]) -> RenderableType:
    """Панель с составом железа и списком доступных источников телеметрии."""
    hardware = Table.grid(expand=True, padding=(0, 1))
    hardware.add_column(justify="left", ratio=1)
    hardware.add_column(justify="left", ratio=2)

    rows = [
        ("Система", f"{profile.os_description}, {profile.form_factor.value}"),
        (
            "Процессор",
            f"{profile.cpu.name}  ({profile.cpu.physical_cores} ядер / "
            f"{profile.cpu.logical_cores} потоков, до {format_watts(profile.cpu.peak_watts)} Вт, "
            f"{profile.cpu.power_source})",
        ),
    ]
    for gpu in profile.gpus:
        detail = f"{gpu.kind.value}"
        if gpu.draws_own_power:
            detail += f", до {format_watts(gpu.peak_watts)} Вт, {gpu.power_source}"
        else:
            detail += ", питается от пакета процессора" if gpu.kind.value == "встроенная" else ", без питания"
        rows.append(("Видеокарта", f"{gpu.name}  ({detail})"))
    rows.append(("Память", f"{profile.ram_gib:.1f} ГБ"))
    rows.append(("Накопители", str(profile.disk_count)))

    for label, value in rows:
        hardware.add_row(Text(label, style="app.muted"), Text(value, style="app.value"))

    source_table = Table.grid(expand=True, padding=(0, 1))
    source_table.add_column(width=3)
    source_table.add_column(justify="left", ratio=1)
    source_table.add_column(justify="left", ratio=2)
    for source in sources:
        marker = Text("●", style="app.ok" if source.active else "app.border")
        source_table.add_row(
            marker,
            Text(source.name, style="app.label" if source.active else "app.muted"),
            Text(source.detail, style="app.muted"),
        )

    return Group(
        Panel(hardware, title="[app.label]Железо", border_style="app.border", padding=(0, 1)),
        Panel(source_table, title="[app.label]Источники данных", border_style="app.border", padding=(0, 1)),
    )


def result_to_dict(result: SessionResult) -> dict:
    """Полный результат замера в виде, пригодном для JSON."""
    projections = build_projections(result.average_watts, result.settings.tariff_per_kwh)
    profile = result.profile
    return {
        "app": "WattHog",
        "version": __version__,
        "started_at": result.started_at.isoformat(timespec="seconds"),
        "duration_seconds": round(result.duration_seconds, 3),
        "sample_count": result.sample_count,
        "interrupted": result.interrupted,
        "accuracy": result.accuracy.value,
        "power_watts": {
            "average_from_wall": round(result.average_watts, 2),
            "average_components": round(result.average_dc_watts, 2),
            "minimum": round(result.minimum_watts, 2),
            "maximum": round(result.maximum_watts, 2),
            "median": round(result.median_watts, 2),
            "percentile95": round(result.percentile95_watts, 2),
        },
        "energy_wh": round(result.energy_wh, 4),
        "breakdown_watts": {
            label: round(watts, 2) for label, watts in result.average_breakdown.components()
        },
        "projections": [
            {
                "hours": projection.hours,
                "label": projection.label,
                "kwh": round(projection.kwh, 4),
                "cost": round(projection.cost, 2) if projection.cost is not None else None,
            }
            for projection in projections
        ],
        "currency": result.settings.currency,
        "tariff_per_kwh": result.settings.tariff_per_kwh,
        "hardware": {
            "os": profile.os_description,
            "form_factor": profile.form_factor.value,
            "cpu": profile.cpu.name,
            "cpu_cores": profile.cpu.physical_cores,
            "cpu_threads": profile.cpu.logical_cores,
            "cpu_peak_watts": round(profile.cpu.peak_watts, 1),
            "gpus": [
                {"name": gpu.name, "kind": gpu.kind.value, "peak_watts": round(gpu.peak_watts, 1)}
                for gpu in profile.gpus
            ],
            "ram_gib": round(profile.ram_gib, 2),
            "disks": profile.disk_count,
        },
        "sources": [
            {"name": source.name, "active": source.active, "detail": source.detail}
            for source in result.sources
        ],
        "settings": asdict(result.settings),
    }


def save_report(result: SessionResult, path: Path | None = None) -> Path | None:
    """Сохраняет отчёт в JSON. Возвращает путь либо ``None`` при ошибке записи."""
    target = path or reports_directory() / f"{result.started_at.strftime(const.REPORT_FILENAME_FORMAT)}.json"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(result_to_dict(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return None
    return target
