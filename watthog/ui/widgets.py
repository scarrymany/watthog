"""Элементы интерфейса: крупные цифры, шкалы и график мощности."""

from __future__ import annotations

from rich.text import Text

from watthog.formatting import chart_bounds, format_kwh, format_watts
from watthog.ui.theme import gradient_color

_BAR_FULL = "█"
_BAR_EMPTY = "░"
_PARTIAL_BLOCKS = " ▁▂▃▄▅▆▇█"

__all__ = [
    "area_chart",
    "big_number",
    "chart_bounds",
    "format_kwh",
    "format_watts",
    "gauge",
    "progress_bar",
]

# Шрифт для крупного вывода текущей мощности: пять строк на символ.
_BIG_GLYPHS: dict[str, tuple[str, ...]] = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": ("  █", "  █", "  █", "  █", "  █"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", "███", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
    ".": ("  ", "  ", "  ", "  ", " █"),
    ",": ("  ", "  ", "  ", "  ", " █"),
    "-": ("   ", "   ", "███", "   ", "   "),
    " ": ("  ", "  ", "  ", "  ", "  "),
}
_BIG_GLYPH_HEIGHT = 5


def big_number(value: str, style: str) -> Text:
    """Строка, набранная блочным шрифтом высотой в пять строк."""
    rows = ["" for _ in range(_BIG_GLYPH_HEIGHT)]
    for character in value:
        glyph = _BIG_GLYPHS.get(character)
        if glyph is None:
            continue
        for index in range(_BIG_GLYPH_HEIGHT):
            rows[index] += glyph[index] + " "
    return Text("\n".join(row.rstrip() for row in rows), style=style)


def gauge(value: float, maximum: float, width: int) -> Text:
    """Горизонтальная шкала с градиентной заливкой по величине значения."""
    width = max(1, width)
    ratio = 0.0 if maximum <= 0 else min(1.0, max(0.0, value / maximum))
    filled = int(round(ratio * width))

    bar = Text()
    for position in range(filled):
        bar.append(_BAR_FULL, style=gradient_color(position / max(1, width - 1)))
    if filled < width:
        bar.append(_BAR_EMPTY * (width - filled), style="app.border")
    return bar


def area_chart(
    values: list[float],
    width: int,
    height: int,
    ceiling: float,
    floor: float = 0.0,
    color_scale: float | None = None,
) -> Text:
    """График мощности блочными символами, новые значения справа.

    ``ceiling`` и ``floor`` задают вертикальное окно, а ``color_scale`` -
    независимую от него шкалу цвета, чтобы оттенок отражал абсолютную мощность,
    а не положение внутри окна.
    """
    width = max(1, width)
    height = max(1, height)
    chart = Text()
    if not values:
        for row in range(height):
            chart.append(" " * width)
            if row < height - 1:
                chart.append("\n")
        return chart

    columns = _fit_to_width(values, width)
    window = ceiling - floor
    if window <= 0:
        window = 1.0
    tint_scale = color_scale if color_scale and color_scale > 0 else ceiling or 1.0

    padding = width - len(columns)
    for row in range(height):
        # Строки рисуются сверху вниз, поэтому верхняя соответствует последнему уровню.
        level_from_bottom = height - row
        if padding > 0:
            chart.append(" " * padding)
        for value in columns:
            filled_levels = min(1.0, max(0.0, (value - floor) / window)) * height
            chart.append(_cell(filled_levels, level_from_bottom), style=gradient_color(value / tint_scale))
        if row < height - 1:
            chart.append("\n")
    return chart


def _cell(filled_levels: float, level_from_bottom: int) -> str:
    remaining = filled_levels - (level_from_bottom - 1)
    if remaining >= 1.0:
        return _BAR_FULL
    if remaining <= 0.0:
        return " "
    return _PARTIAL_BLOCKS[max(1, int(remaining * (len(_PARTIAL_BLOCKS) - 1)))]


def _fit_to_width(values: list[float], width: int) -> list[float]:
    """Сжимает историю до ширины графика, сохраняя пики."""
    if len(values) <= width:
        return list(values)
    bucket_size = len(values) / width
    compressed = []
    for index in range(width):
        start = int(index * bucket_size)
        end = max(start + 1, int((index + 1) * bucket_size))
        compressed.append(max(values[start:end]))
    return compressed


def progress_bar(fraction: float, width: int) -> Text:
    width = max(1, width)
    filled = int(round(min(1.0, max(0.0, fraction)) * width))
    bar = Text()
    bar.append("▰" * filled, style="app.accent")
    bar.append("▱" * (width - filled), style="app.border")
    return bar
