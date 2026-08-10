"""Оформление интерфейса: палитра и общая тема rich."""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

from watthog.palette import ACCENT, BORDER, DANGER, OK, TEXT_MUTED, WARNING, gradient_color

MUTED = TEXT_MUTED

WATTHOG_THEME = Theme(
    {
        "app.title": f"bold {ACCENT}",
        "app.accent": ACCENT,
        "app.muted": MUTED,
        "app.label": "bold #c9d1d9",
        "app.value": "bold #ffffff",
        "app.unit": MUTED,
        "app.ok": OK,
        "app.warn": ACCENT,
        "app.bad": DANGER,
        "app.border": BORDER,
        "app.hint": f"italic {MUTED}",
    }
)

__all__ = ["MUTED", "WATTHOG_THEME", "WARNING", "build_console", "gradient_color"]


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
