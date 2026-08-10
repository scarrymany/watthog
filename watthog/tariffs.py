"""Справочник тарифов на электроэнергию.

Цены собраны из открытых источников и приведены с датами вступления в силу,
поэтому программа сама переходит на новое значение, когда оно начинает
действовать, без обновления сборки.

Справочник - это удобная отправная точка, а не истина. Тарифы зависят от
региона, типа счётчика, объёма потребления и категории жилья, поэтому любое
значение можно заменить своим в настройках.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

CURRENCY_HRYVNIA = "₴"
CURRENCY_RUBLE = "₽"


@dataclass(frozen=True)
class TariffRate:
    """Цена киловатт-часа и дата, с которой она действует."""

    price: float
    effective_from: date


@dataclass(frozen=True)
class TariffPreset:
    """Готовый тариф из справочника."""

    key: str
    region: str
    description: str
    currency: str
    rates: tuple[TariffRate, ...]
    source: str

    def price_on(self, today: date) -> float:
        """Цена, действующая на указанную дату.

        Если все известные ставки ещё не вступили в силу, возвращается самая
        ранняя из них: это ближайшее к истине значение из того, что есть.
        """
        applicable = [rate for rate in self.rates if rate.effective_from <= today]
        return applicable[-1].price if applicable else self.rates[0].price

    def upcoming_change(self, today: date) -> TariffRate | None:
        """Ближайшее известное изменение цены после указанной даты."""
        future = [rate for rate in self.rates if rate.effective_from > today]
        return future[0] if future else None

    @property
    def title(self) -> str:
        return f"{self.region} - {self.description}"


# Данные проверены 10 августа 2026 года.
TARIFF_PRESETS: tuple[TariffPreset, ...] = (
    TariffPreset(
        key="ua",
        region="Украина",
        description="единый тариф для населения",
        currency=CURRENCY_HRYVNIA,
        rates=(TariffRate(4.32, date(2024, 6, 1)),),
        source="постановление КМУ №632 от 31.05.2024, действует по всей стране",
    ),
    TariffPreset(
        key="ua-night",
        region="Украина, ночь",
        description="двухзонный счётчик, 23:00-07:00",
        currency=CURRENCY_HRYVNIA,
        rates=(TariffRate(2.16, date(2024, 6, 1)),),
        source="половина дневного тарифа при двухзонном учёте",
    ),
    TariffPreset(
        key="ru-msk-gas",
        region="Москва, газовая плита",
        description="одноставочный, с НДС",
        currency=CURRENCY_RUBLE,
        rates=(TariffRate(8.00, date(2026, 1, 1)), TariffRate(8.90, date(2026, 10, 1))),
        source="Департамент экономической политики и развития Москвы",
    ),
    TariffPreset(
        key="ru-msk-electric",
        region="Москва, электроплита",
        description="одноставочный, с НДС",
        currency=CURRENCY_RUBLE,
        rates=(TariffRate(7.28, date(2026, 1, 1)), TariffRate(8.46, date(2026, 10, 1))),
        source="Департамент экономической политики и развития Москвы",
    ),
)

DEFAULT_PRESET_KEY = "ua"
CUSTOM_PRESET_TITLE = "Своё значение"


def find_preset(key: str) -> TariffPreset | None:
    for preset in TARIFF_PRESETS:
        if preset.key == key:
            return preset
    return None


def default_preset() -> TariffPreset:
    preset = find_preset(DEFAULT_PRESET_KEY)
    if preset is None:  # pragma: no cover - защита от правки справочника
        return TARIFF_PRESETS[0]
    return preset


def preset_keys() -> tuple[str, ...]:
    return tuple(preset.key for preset in TARIFF_PRESETS)


def match_preset(price: float, currency: str, today: date | None = None) -> TariffPreset | None:
    """Справочный тариф, совпадающий с заданными ценой и валютой."""
    moment = today or date.today()
    for preset in TARIFF_PRESETS:
        if preset.currency == currency and abs(preset.price_on(moment) - price) < 0.005:
            return preset
    return None


DEFAULT_CURRENCY = default_preset().currency
DEFAULT_TARIFF_PER_KWH = default_preset().price_on(date.today())
