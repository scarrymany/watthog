"""Пересчёт средней мощности в расход энергии и деньги."""

from __future__ import annotations

from dataclasses import dataclass

from watthog import constants as const

_HOURS_IN_DAY = 24.0
_DAY_FORMS = ("день", "дня", "дней")
_HOUR_FORMS = ("час", "часа", "часов")
_SPECIAL_LABELS = {
    24.0: "24 часа (сутки)",
    168.0: "7 дней (неделя)",
    720.0: "30 дней (месяц)",
}


@dataclass(frozen=True)
class Projection:
    """Сколько энергии и денег уйдёт за указанный срок при той же нагрузке."""

    hours: float
    label: str
    kwh: float
    cost: float | None


def energy_kwh(average_watts: float, hours: float) -> float:
    return average_watts * hours / const.WATTS_PER_KILOWATT


def build_projections(
    average_watts: float,
    tariff_per_kwh: float = 0.0,
    hours: tuple[float, ...] = const.PROJECTION_HOURS,
) -> tuple[Projection, ...]:
    projections = []
    for span in hours:
        kwh = energy_kwh(average_watts, span)
        cost = kwh * tariff_per_kwh if tariff_per_kwh > 0.0 else None
        projections.append(Projection(hours=span, label=format_span(span), kwh=kwh, cost=cost))
    return tuple(projections)


def format_span(hours: float) -> str:
    """Человекочитаемое название интервала: "10 часов", "7 дней (неделя)"."""
    special = _SPECIAL_LABELS.get(hours)
    if special is not None:
        return special
    if hours >= _HOURS_IN_DAY and hours % _HOURS_IN_DAY == 0:
        days = int(hours // _HOURS_IN_DAY)
        return f"{days} {plural_ru(days, _DAY_FORMS)}"
    if hours == int(hours):
        whole = int(hours)
        return f"{whole} {plural_ru(whole, _HOUR_FORMS)}"
    return f"{hours:.1f} ч"


def plural_ru(count: int, forms: tuple[str, str, str]) -> str:
    """Форма слова для числа: 1 час, 2 часа, 5 часов."""
    remainder_100 = abs(count) % 100
    if 11 <= remainder_100 <= 14:
        return forms[2]
    remainder_10 = remainder_100 % 10
    if remainder_10 == 1:
        return forms[0]
    if 2 <= remainder_10 <= 4:
        return forms[1]
    return forms[2]


def consumption_tier(watts: float) -> tuple[str, str]:
    """Словесная оценка прожорливости и цвет для неё."""
    for threshold, label, style in const.CONSUMPTION_TIERS:
        if watts < threshold:
            return label, style
    return const.CONSUMPTION_TIERS[-1][1], const.CONSUMPTION_TIERS[-1][2]
