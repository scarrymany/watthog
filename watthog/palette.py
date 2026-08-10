"""Палитра, общая для консольного и оконного интерфейсов.

Модуль намеренно не зависит ни от rich, ни от tkinter: цвета задаются
шестнадцатеричными строками, которые понимают оба тулкита.
"""

from __future__ import annotations

BACKGROUND = "#0d1117"
SURFACE = "#161b22"
SURFACE_RAISED = "#1c2230"
BORDER = "#30363d"
TEXT = "#e6edf3"
TEXT_MUTED = "#7d8590"
ACCENT = "#ffd23f"
OK = "#43d675"
WARNING = "#ff9f40"
DANGER = "#ff4d4d"

# Опорные цвета шкалы нагрузки: от экономного к прожорливому.
GRADIENT_STOPS = ((0x43, 0xD6, 0x75), (0xFF, 0xD2, 0x3F), (0xFF, 0x4D, 0x4D))


def gradient_color(fraction: float) -> str:
    """Цвет шкалы для доли от нуля до единицы."""
    position = min(1.0, max(0.0, fraction)) * (len(GRADIENT_STOPS) - 1)
    index = min(int(position), len(GRADIENT_STOPS) - 2)
    weight = position - index
    start, end = GRADIENT_STOPS[index], GRADIENT_STOPS[index + 1]
    channels = tuple(round(start[channel] + (end[channel] - start[channel]) * weight) for channel in range(3))
    return "#{:02x}{:02x}{:02x}".format(*channels)


def mix(first: str, second: str, weight: float) -> str:
    """Смешивает два цвета: ``weight`` равный нулю даёт первый, единица - второй."""
    weight = min(1.0, max(0.0, weight))
    left, right = _channels(first), _channels(second)
    blended = tuple(round(left[channel] + (right[channel] - left[channel]) * weight) for channel in range(3))
    return "#{:02x}{:02x}{:02x}".format(*blended)


def _channels(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
