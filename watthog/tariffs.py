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
from math import isclose

CURRENCY_HRYVNIA = "₴"
CURRENCY_RUBLE = "₽"
CURRENCY_DOLLAR = "$"
CURRENCY_TENGE = "₸"

# Валюты, для которых в справочнике есть готовые тарифы. Поле валюты остаётся
# свободным текстом: сюда можно вписать любой знак, справочник лишь избавляет
# от ручного ввода для самых частых случаев.
SUPPORTED_CURRENCIES = (CURRENCY_HRYVNIA, CURRENCY_RUBLE, CURRENCY_DOLLAR, CURRENCY_TENGE)


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
    TariffPreset(
        key="kz-almaty",
        region="Алматы, 1 уровень",
        description="в пределах нормы потребления",
        currency=CURRENCY_TENGE,
        rates=(TariffRate(29.34, date(2026, 1, 1)),),
        source="АО «Алатау Жарық Компаниясы», дифференцированный тариф для населения",
    ),
    TariffPreset(
        key="kz-almaty-2",
        region="Алматы, 2 уровень",
        description="сверх нормы потребления",
        currency=CURRENCY_TENGE,
        rates=(TariffRate(38.78, date(2026, 1, 1)),),
        source="АО «Алатау Жарық Компаниясы», дифференцированный тариф для населения",
    ),
    TariffPreset(
        key="us",
        region="США, в среднем",
        description="жилые домохозяйства",
        currency=CURRENCY_DOLLAR,
        rates=(TariffRate(0.1791, date(2026, 1, 1)),),
        source="EIA Electric Power Monthly, таблица 5.6.B",
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
    """Справочный тариф, совпадающий с заданными ценой и валютой.

    Сравнение относительное: цены отличаются на три порядка, от долей доллара
    до десятков тенге, и единый абсолютный допуск для них не подходит.
    """
    moment = today or date.today()
    for preset in TARIFF_PRESETS:
        if preset.currency != currency:
            continue
        if isclose(preset.price_on(moment), price, rel_tol=1e-4, abs_tol=1e-6):
            return preset
    return None


DEFAULT_CURRENCY = default_preset().currency
DEFAULT_TARIFF_PER_KWH = default_preset().price_on(date.today())
