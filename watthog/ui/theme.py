"""Оформление интерфейса: палитра и общая тема rich."""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

ACCENT = "#ffd23f"
MUTED = "#7d8590"
BORDER = "#30363d"
SURFACE = "#161b22"

# Опорные цвета шкалы нагрузки: от экономного к прожорливому.
GRADIENT_STOPS = ((0x43, 0xD6, 0x75), (0xFF, 0xD2, 0x3F), (0xFF, 0x4D, 0x4D))

WATTHOG_THEME = Theme(
    {
        "app.title": f"bold {ACCENT}",
        "app.accent": ACCENT,
        "app.muted": MUTED,
        "app.label": "bold #c9d1d9",
        "app.value": "bold #ffffff",
        "app.unit": MUTED,
        "app.ok": "#43d675",
        "app.warn": "#ffd23f",
        "app.bad": "#ff4d4d",
        "app.border": BORDER,
        "app.hint": f"italic {MUTED}",
    }
)


def build_console(
    force_terminal: bool | None = None,
    record: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> Console:
    return Console(
        theme=WATTHOG_THEME,
        highlight=False,
        force_terminal=force_terminal,
        record=record,
        width=width,
        height=height,
    )


def gradient_color(fraction: float) -> str:
    """Цвет шкалы для доли от нуля до единицы."""
    position = min(1.0, max(0.0, fraction)) * (len(GRADIENT_STOPS) - 1)
    index = min(int(position), len(GRADIENT_STOPS) - 2)
    weight = position - index
    start, end = GRADIENT_STOPS[index], GRADIENT_STOPS[index + 1]
    channels = tuple(round(start[i] + (end[i] - start[i]) * weight) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*channels)
