"""Форматирование величин и вычисление шкал, общие для обоих интерфейсов."""

from __future__ import annotations

import re

_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
THOUSANDS_SEPARATOR = " "
_HARDWARE_NOISE_PATTERN = re.compile(
    r"\(R\)|\(TM\)|\bCPU\b|\bProcessor\b|\d+-Core|@.*$", re.IGNORECASE
)
_WHITESPACE_PATTERN = re.compile(r"\s+")

# Ниже этой доли разброса график переключается на суженную шкалу.
CHART_ZOOM_THRESHOLD = 0.25
CHART_HEADROOM = 1.15
CHART_MIN_MARGIN_RATIO = 0.02


def format_watts(watts: float) -> str:
    """Ватты с разумным числом знаков: сотни без дробной части, единицы с двумя."""
    if watts >= 100.0:
        return f"{watts:.0f}"
    if watts >= 10.0:
        return f"{watts:.1f}"
    return f"{watts:.2f}"


def format_kwh(kwh: float) -> str:
    if kwh >= 100.0:
        return f"{kwh:.1f}"
    if kwh >= 1.0:
        return f"{kwh:.2f}"
    return f"{kwh:.3f}"


def format_money(amount: float) -> str:
    """Сумма с неразрывным пробелом между разрядами.

    Пробел именно неразрывный, чтобы число не разорвалось переносом строки.
    """
    return f"{amount:,.2f}".replace(",", THOUSANDS_SEPARATOR)


def format_price(price: float) -> str:
    """Цена киловатт-часа с уместным числом знаков.

    Тарифы разных стран отличаются на три порядка: десятки тенге и доли
    доллара. Двух знаков хватает для первых, но округлило бы вторые до
    неразличимости.
    """
    if price >= 1.0:
        return f"{price:.2f}"
    return f"{price:.4f}".rstrip("0").rstrip(".")


def parse_number(text: str) -> float | None:
    """Первое число из строки или ``None``.

    Пользователь часто повторяет подсказанную единицу измерения ("650 Вт"),
    поэтому всё, кроме самого числа, отбрасывается.
    """
    match = _NUMBER_PATTERN.search(text.replace(",", "."))
    return float(match.group()) if match else None


def shorten_hardware_name(name: str) -> str:
    """Имя железа без маркетингового мусора, но с сохранением регистра.

    "AMD Ryzen 7 7800X3D 8-Core Processor" превращается в "AMD Ryzen 7 7800X3D".
    Нужно там, где место ограничено: в шапке окна и в строке состояния.
    """
    cleaned = _HARDWARE_NOISE_PATTERN.sub(" ", name)
    return _WHITESPACE_PATTERN.sub(" ", cleaned).strip() or name.strip()


def chart_bounds(values: list[float]) -> tuple[float, float]:
    """Границы вертикальной шкалы графика.

    При заметном разбросе шкала начинается с нуля - так виден абсолютный
    уровень. Если же мощность почти не меняется, нулевая шкала превратила бы
    график в сплошную заливку, поэтому окно сужается вокруг данных, а его
    границы подписываются рядом с графиком.
    """
    if not values:
        return 0.0, 1.0
    low, high = min(values), max(values)
    if high <= 0.0:
        return 0.0, 1.0

    span = high - low
    if span / high >= CHART_ZOOM_THRESHOLD:
        return 0.0, high * CHART_HEADROOM

    margin = max(span, high * CHART_MIN_MARGIN_RATIO)
    return max(0.0, low - margin * 0.8), high + margin * 0.4
