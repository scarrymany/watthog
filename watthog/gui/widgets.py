"""Виджеты, нарисованные вручную на Canvas.

Готовых элементов с нужным видом нет ни в tkinter, ни в customtkinter, поэтому
шкала, график и разбивка рисуются самостоятельно. Так оконный интерфейс
повторяет вид консольного, а не выглядит набором стандартных контролов.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

from watthog.formatting import format_watts
from watthog.gui.theme import BORDER, SURFACE, SURFACE_RAISED, TEXT, TEXT_MUTED, Fonts
from watthog.palette import gradient_color, mix

_GRADIENT_SLICE_WIDTH = 2
_CHART_GRID_LINES = 4
_CHART_PADDING_LEFT = 46
_CHART_PADDING_RIGHT = 14
_CHART_PADDING_TOP = 12
_CHART_PADDING_BOTTOM = 20
_CHART_AREA_BLEND = 0.20
_CHART_LINE_WIDTH = 2

_ROW_HEIGHT = 26
_ROW_LABEL_X = 4
_ROW_VALUE_WIDTH = 62
_ROW_PERCENT_WIDTH = 44
_ROW_BAR_HEIGHT = 8
_ROW_LABEL_WIDTH = 108
_MIN_BAR_WIDTH = 40


@dataclass(frozen=True)
class BreakdownRow:
    label: str
    watts: float
    share: float


class _CanvasWidget(tk.Canvas):
    """Общая основа: прозрачный фон панели и перерисовка при изменении размера."""

    def __init__(self, parent: tk.Misc, fonts: Fonts, height: int, background: str = SURFACE) -> None:
        super().__init__(
            parent,
            height=height,
            background=background,
            highlightthickness=0,
            borderwidth=0,
        )
        self._fonts = fonts
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, _event: tk.Event) -> None:
        self.redraw()

    def redraw(self) -> None:
        raise NotImplementedError


def draw_gradient_stadium(
    canvas: tk.Canvas,
    left: float,
    top: float,
    right: float,
    bottom: float,
    color_at: Callable[[float], str],
) -> None:
    """Полоса со скруглёнными концами, залитая градиентом слева направо."""
    if right <= left:
        return
    radius = (bottom - top) / 2
    if right - left <= radius * 2:
        color = color_at(0.0)
        canvas.create_oval(left, top, left + radius * 2, bottom, fill=color, outline=color)
        return

    span = right - left
    left_color = color_at(0.0)
    right_color = color_at(1.0)
    canvas.create_oval(left, top, left + radius * 2, bottom, fill=left_color, outline=left_color)
    canvas.create_oval(right - radius * 2, top, right, bottom, fill=right_color, outline=right_color)

    position = left + radius
    while position < right - radius:
        width = min(_GRADIENT_SLICE_WIDTH, right - radius - position)
        color = color_at((position - left) / span)
        canvas.create_rectangle(position, top, position + width, bottom, fill=color, outline=color)
        position += width


def draw_stadium(canvas: tk.Canvas, left: float, top: float, right: float, bottom: float, color: str) -> None:
    draw_gradient_stadium(canvas, left, top, right, bottom, lambda _position: color)


class PowerGauge(_CanvasWidget):
    """Горизонтальная шкала текущей мощности."""

    def __init__(self, parent: tk.Misc, fonts: Fonts, height: int = 18) -> None:
        super().__init__(parent, fonts, height)
        self._value = 0.0
        self._maximum = 1.0

    def set_value(self, value: float, maximum: float) -> None:
        self._value = max(0.0, value)
        self._maximum = maximum if maximum > 0 else 1.0
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            return

        top = (height - _ROW_BAR_HEIGHT * 1.6) / 2
        bottom = height - top
        draw_stadium(self, 0, top, width, bottom, SURFACE_RAISED)

        filled = min(1.0, self._value / self._maximum) * width
        if filled <= 0:
            return
        draw_gradient_stadium(self, 0, top, filled, bottom, lambda position: gradient_color(position * filled / width))


class PowerChart(_CanvasWidget):
    """График мощности за всё время замера."""

    def __init__(self, parent: tk.Misc, fonts: Fonts, height: int = 190) -> None:
        super().__init__(parent, fonts, height)
        self._values: list[float] = []
        self._floor = 0.0
        self._ceiling = 1.0
        self._color_scale = 1.0

    def set_history(self, values: list[float], floor: float, ceiling: float, color_scale: float) -> None:
        self._values = values
        self._floor = floor
        self._ceiling = ceiling if ceiling > floor else floor + 1.0
        self._color_scale = color_scale if color_scale > 0 else 1.0
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            return

        plot_left = _CHART_PADDING_LEFT
        plot_right = width - _CHART_PADDING_RIGHT
        plot_top = _CHART_PADDING_TOP
        plot_bottom = height - _CHART_PADDING_BOTTOM
        if plot_right <= plot_left or plot_bottom <= plot_top:
            return

        has_data = len(self._values) >= 2
        self._draw_grid(plot_left, plot_top, plot_right, plot_bottom, with_labels=has_data)
        if not has_data:
            self._draw_placeholder(plot_left, plot_top, plot_right, plot_bottom)
            return

        points = self._plot_points(plot_left, plot_top, plot_right, plot_bottom)
        average = sum(self._values) / len(self._values)
        area_color = mix(SURFACE, gradient_color(average / self._color_scale), _CHART_AREA_BLEND)

        polygon = [*points, (plot_right, plot_bottom), (plot_left, plot_bottom)]
        self.create_polygon(
            [coordinate for point in polygon for coordinate in point],
            fill=area_color,
            outline="",
        )

        self._draw_line(points)

    def _draw_line(self, points: list[tuple[float, float]]) -> None:
        for index in range(len(points) - 1):
            x1, y1 = points[index]
            x2, y2 = points[index + 1]
            value = self._values[min(index, len(self._values) - 1)]
            self.create_line(
                x1,
                y1,
                x2,
                y2,
                fill=gradient_color(value / self._color_scale),
                width=_CHART_LINE_WIDTH,
                capstyle="round",
            )

    def _plot_points(
        self, left: float, top: float, right: float, bottom: float
    ) -> list[tuple[float, float]]:
        window = self._ceiling - self._floor
        span = right - left
        step = span / (len(self._values) - 1)
        points = []
        for index, value in enumerate(self._values):
            normalized = min(1.0, max(0.0, (value - self._floor) / window))
            points.append((left + index * step, bottom - normalized * (bottom - top)))
        return points

    def _draw_grid(
        self, left: float, top: float, right: float, bottom: float, with_labels: bool
    ) -> None:
        font = self._fonts.canvas(10)
        for index in range(_CHART_GRID_LINES + 1):
            fraction = index / _CHART_GRID_LINES
            y = bottom - fraction * (bottom - top)
            self.create_line(left, y, right, y, fill=BORDER, dash=(2, 4))
            if not with_labels:
                continue
            value = self._floor + fraction * (self._ceiling - self._floor)
            self.create_text(left - 8, y, text=f"{value:.0f}", anchor="e", fill=TEXT_MUTED, font=font)

        if with_labels:
            self.create_text(right, bottom + 10, text="Вт", anchor="e", fill=TEXT_MUTED, font=font)

    def _draw_placeholder(self, left: float, top: float, right: float, bottom: float) -> None:
        self.create_text(
            (left + right) / 2,
            (top + bottom) / 2,
            text="График появится после запуска замера",
            fill=TEXT_MUTED,
            font=self._fonts.canvas(12),
        )


class BreakdownChart(_CanvasWidget):
    """Разбивка мощности по компонентам."""

    def __init__(self, parent: tk.Misc, fonts: Fonts, rows: int = 7) -> None:
        super().__init__(parent, fonts, _ROW_HEIGHT * rows)
        self._rows: list[BreakdownRow] = []

    def set_rows(self, rows: list[BreakdownRow]) -> None:
        self._rows = rows
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        if width <= 1:
            return
        if not self._rows:
            self.create_text(
                width / 2,
                _ROW_HEIGHT,
                text="Разбивка появится после запуска замера",
                fill=TEXT_MUTED,
                font=self._fonts.canvas(12),
            )
            return

        label_font = self._fonts.canvas(12)
        value_font = self._fonts.canvas_mono(12, bold=True)
        percent_font = self._fonts.canvas(11)

        bar_left = _ROW_LABEL_X + _ROW_LABEL_WIDTH + _ROW_VALUE_WIDTH + _ROW_PERCENT_WIDTH
        bar_right = width - 4
        draw_bars = bar_right - bar_left >= _MIN_BAR_WIDTH

        for index, row in enumerate(self._rows):
            center = index * _ROW_HEIGHT + _ROW_HEIGHT / 2
            self.create_text(
                _ROW_LABEL_X, center, text=row.label, anchor="w", fill=TEXT, font=label_font
            )
            self.create_text(
                _ROW_LABEL_X + _ROW_LABEL_WIDTH + _ROW_VALUE_WIDTH - 8,
                center,
                text=format_watts(row.watts),
                anchor="e",
                fill=TEXT,
                font=value_font,
            )
            self.create_text(
                bar_left - 8,
                center,
                text=f"{row.share * 100:.0f}%",
                anchor="e",
                fill=TEXT_MUTED,
                font=percent_font,
            )
            if not draw_bars:
                continue

            top = center - _ROW_BAR_HEIGHT / 2
            bottom = center + _ROW_BAR_HEIGHT / 2
            draw_stadium(self, bar_left, top, bar_right, bottom, SURFACE_RAISED)
            filled = bar_left + min(1.0, max(0.0, row.share)) * (bar_right - bar_left)
            if filled > bar_left:
                draw_gradient_stadium(
                    self,
                    bar_left,
                    top,
                    filled,
                    bottom,
                    lambda position, share=row.share: gradient_color(position * share),
                )
