"""Живая панель измерения, которая обновляется на каждой выборке."""

from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from watthog import AUTHOR_TELEGRAM, __version__
from watthog.config import Settings
from watthog.formatting import shorten_hardware_name
from watthog.inventory import HardwareProfile
from watthog.meter import Accuracy, PowerBreakdown
from watthog.projections import consumption_tier
from watthog.session import Sample
from watthog.ui.theme import gradient_color
from watthog.ui.widgets import (
    area_chart,
    big_number,
    chart_bounds,
    format_watts,
    gauge,
    progress_bar,
)

_HEADER_HEIGHT = 3
_FOOTER_HEIGHT = 3
_BODY_HEIGHT = 11
_MIN_CHART_HEIGHT = 4
_MAX_CHART_HEIGHT = 10
# Панель графика: сам график, строка подписи шкалы и две линии рамки.
_CHART_PANEL_EXTRA = 3
_MIN_CONSOLE_HEIGHT = (
    _HEADER_HEIGHT + _FOOTER_HEIGHT + _BODY_HEIGHT + _MIN_CHART_HEIGHT + _CHART_PANEL_EXTRA
)
# Шкала всегда с запасом над максимумом, иначе пик упирается в край панели.
_SCALE_HEADROOM = 1.15
_MIN_SCALE_WATTS = 50.0
_PANEL_PADDING = 4
_COMPONENT_LABEL_WIDTH = 10
# Подпись, ватты, доля, отступы и рамка панели - всё, что не отдано под шкалу.
_BREAKDOWN_FIXED_WIDTH = 30


class LiveDashboard:
    """Панель замера: текущая мощность, разбивка, график и прогресс."""

    def __init__(
        self,
        console: Console,
        profile: HardwareProfile,
        settings: Settings,
        duration_seconds: float,
    ) -> None:
        self._console = console
        self._profile = profile
        self._settings = settings
        self._duration = duration_seconds
        self._history: list[float] = []
        self._minimum = float("inf")
        self._maximum = 0.0
        self._energy_wh = 0.0
        self._last_sample: Sample | None = None
        self._live: Live | None = None
        self._chart_height = _resolve_chart_height(console.size.height)

    def __enter__(self) -> LiveDashboard:
        self._live = Live(
            self.renderable(),
            console=self._console,
            refresh_per_second=8,
            transient=False,
            screen=False,
        )
        self._live.start()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def update(self, sample: Sample, _duration: float) -> None:
        self._last_sample = sample
        self._history.append(sample.watts)
        self._minimum = min(self._minimum, sample.watts)
        self._maximum = max(self._maximum, sample.watts)
        if self._live is not None:
            self._live.update(self.renderable())

    # -- отрисовка ----------------------------------------------------------

    def renderable(self) -> RenderableType:
        """Текущее состояние панели как отдельный объект для отрисовки."""
        layout = Layout(name="root")
        layout.split_column(
            Layout(self._header(), name="header", size=_HEADER_HEIGHT),
            Layout(name="body", size=_BODY_HEIGHT),
            Layout(self._chart(), name="chart", size=self._chart_height + _CHART_PANEL_EXTRA),
            Layout(self._footer(), name="footer", size=_FOOTER_HEIGHT),
        )
        layout["body"].split_row(
            Layout(self._current_power(), name="power", ratio=1),
            Layout(self._breakdown(), name="breakdown", ratio=1),
        )
        return layout

    def _header(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_column(justify="right")

        title = Text.assemble(("⚡ ", "app.accent"), ("WattHog ", "app.title"), (f"v{__version__}", "app.muted"))
        hardware = Text(" · ".join(self._hardware_summary()), style="app.muted")
        grid.add_row(title, hardware)
        return Panel(grid, border_style="app.border", padding=(0, 1))

    def _hardware_summary(self) -> list[str]:
        parts = [shorten_hardware_name(self._profile.cpu.name)]
        parts.extend(shorten_hardware_name(gpu.name) for gpu in self._profile.discrete_gpus)
        parts.append(f"{self._profile.ram_gib:.0f} ГБ")
        parts.append(self._profile.form_factor.value)
        return parts

    def _current_power(self) -> Panel:
        watts = self._last_sample.watts if self._last_sample else 0.0
        scale = self._scale()
        tier_label, tier_style = consumption_tier(watts)
        color = gradient_color(watts / scale if scale else 0.0)

        value = Table.grid(padding=(0, 1))
        value.add_column()
        value.add_column()
        value.add_row(big_number(format_watts(watts), color), Text("\n\n\nВт", style="app.unit"))

        inner_width = max(10, self._console.size.width // 2 - _PANEL_PADDING)
        statistics = Text.assemble(
            ("мин ", "app.muted"),
            (format_watts(self._minimum) if self._history else "-", "app.value"),
            ("   макс ", "app.muted"),
            (format_watts(self._maximum) if self._history else "-", "app.value"),
            ("   сред ", "app.muted"),
            (format_watts(self._running_average()) if self._history else "-", "app.value"),
        )

        body = Group(
            Align.center(value),
            Text(""),
            gauge(watts, scale, inner_width),
            statistics,
            Text.assemble((tier_label, tier_style), ("  ", ""), (self._sensor_line(), "app.muted")),
        )
        return Panel(body, title="[app.label]Текущая мощность из розетки", border_style="app.border", padding=(0, 1))

    def _breakdown(self) -> Panel:
        breakdown = self._last_sample.breakdown if self._last_sample else PowerBreakdown()
        total = breakdown.total_ac

        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(justify="left", width=_COMPONENT_LABEL_WIDTH, no_wrap=True)
        table.add_column(justify="right", width=6, no_wrap=True)
        table.add_column(justify="right", width=4, no_wrap=True)
        table.add_column(justify="left", ratio=1)

        bar_width = max(6, self._console.size.width // 2 - _BREAKDOWN_FIXED_WIDTH)
        for label, watts in breakdown.components():
            if watts <= 0.0:
                continue
            share = watts / total if total > 0 else 0.0
            table.add_row(
                Text(label, style="app.label"),
                Text(format_watts(watts), style="app.value"),
                Text(f"{share * 100:.0f}%", style="app.muted"),
                gauge(share, 1.0, bar_width),
            )

        totals = Text.assemble(
            ("Железо ", "app.muted"),
            (f"{format_watts(breakdown.total_dc)} Вт", "app.value"),
            ("   ·   из розетки ", "app.muted"),
            (f"{format_watts(total)} Вт", "app.value"),
        )
        body = Group(table, Text(""), totals)
        return Panel(body, title="[app.label]Разбивка по компонентам", border_style="app.border", padding=(0, 1))

    def _chart(self) -> Panel:
        width = max(10, self._console.size.width - _PANEL_PADDING)
        floor, ceiling = chart_bounds(self._history)
        chart = area_chart(
            self._history, width, self._chart_height, ceiling, floor, color_scale=self._scale()
        )

        axis = Table.grid(expand=True)
        axis.add_column(justify="left")
        axis.add_column(justify="right")
        axis.add_row(
            Text(f"шкала {floor:.0f} - {ceiling:.0f} Вт", style="app.muted"),
            Text(f"{len(self._history)} выборок", style="app.muted"),
        )
        return Panel(
            Group(chart, axis),
            title="[app.label]История мощности",
            border_style="app.border",
            padding=(0, 1),
        )

    def _footer(self) -> Panel:
        elapsed = self._last_sample.elapsed if self._last_sample else 0.0
        fraction = min(1.0, elapsed / self._duration) if self._duration > 0 else 0.0
        bar_width = max(10, self._console.size.width // 3)

        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="right")
        grid.add_row(
            Text.assemble(
                progress_bar(fraction, bar_width),
                ("  ", ""),
                (f"{elapsed:.0f} с / {self._duration:.0f} с", "app.value"),
            ),
            Text(self._accuracy_label(), style="app.muted"),
            Text.assemble(("Ctrl+C - прервать   ", "app.hint"), (AUTHOR_TELEGRAM, "app.accent")),
        )
        return Panel(grid, border_style="app.border", padding=(0, 1))

    # -- вспомогательные значения -------------------------------------------

    def _scale(self) -> float:
        return max(_MIN_SCALE_WATTS, self._maximum * _SCALE_HEADROOM)

    def _running_average(self) -> float:
        return sum(self._history) / len(self._history) if self._history else 0.0

    def _accuracy_label(self) -> str:
        if self._last_sample is None:
            return ""
        accuracy: Accuracy = self._last_sample.accuracy
        return f"точность: {accuracy.value}"

    def _sensor_line(self) -> str:
        if self._last_sample is None:
            return ""
        telemetry = self._last_sample.telemetry
        parts = [f"ЦП {telemetry.cpu_load * 100:.0f}%"]
        for reading in telemetry.gpus:
            if reading.utilization is not None:
                parts.append(f"GPU {reading.utilization * 100:.0f}%")
            if reading.temperature_c is not None:
                parts.append(f"{reading.temperature_c:.0f}°C")
        battery = telemetry.battery
        if battery is not None and battery.present and battery.charge_percent is not None:
            parts.append(f"батарея {battery.charge_percent:.0f}%")
        return " · ".join(parts)


def _resolve_chart_height(console_height: int) -> int:
    available = console_height - _HEADER_HEIGHT - _FOOTER_HEIGHT - _BODY_HEIGHT - _CHART_PANEL_EXTRA
    return max(_MIN_CHART_HEIGHT, min(_MAX_CHART_HEIGHT, available))


def console_is_tall_enough(console: Console) -> bool:
    return console.size.height >= _MIN_CONSOLE_HEIGHT
