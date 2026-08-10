from datetime import date
from pathlib import Path

import pytest

from watthog.tariffs import (
    CURRENCY_DOLLAR,
    CURRENCY_HRYVNIA,
    CURRENCY_RUBLE,
    CURRENCY_TENGE,
    DEFAULT_CURRENCY,
    DEFAULT_PRESET_KEY,
    DEFAULT_TARIFF_PER_KWH,
    SUPPORTED_CURRENCIES,
    TARIFF_PRESETS,
    TariffPreset,
    TariffRate,
    default_preset,
    find_preset,
    match_preset,
    preset_keys,
)

ROOT = Path(__file__).resolve().parents[1]
UKRAINE_PRICE = 4.32
MOSCOW_GAS_PRICE_BEFORE_OCTOBER = 8.00
MOSCOW_GAS_PRICE_FROM_OCTOBER = 8.90


def two_step_preset() -> TariffPreset:
    return TariffPreset(
        key="test",
        region="Тест",
        description="проверочный",
        currency=CURRENCY_RUBLE,
        rates=(TariffRate(10.0, date(2026, 1, 1)), TariffRate(12.0, date(2026, 10, 1))),
        source="тест",
    )


def test_price_uses_the_rate_in_force():
    preset = two_step_preset()
    assert preset.price_on(date(2026, 1, 1)) == 10.0
    assert preset.price_on(date(2026, 9, 30)) == 10.0
    assert preset.price_on(date(2026, 10, 1)) == 12.0
    assert preset.price_on(date(2027, 5, 5)) == 12.0


def test_price_before_any_rate_falls_back_to_the_earliest():
    assert two_step_preset().price_on(date(2025, 1, 1)) == 10.0


def test_upcoming_change_reports_the_next_step_only():
    preset = two_step_preset()
    upcoming = preset.upcoming_change(date(2026, 5, 1))
    assert upcoming is not None
    assert upcoming.price == 12.0
    assert upcoming.effective_from == date(2026, 10, 1)
    assert preset.upcoming_change(date(2026, 10, 1)) is None
    assert preset.upcoming_change(date(2030, 1, 1)) is None


def test_default_preset_is_ukrainian_hryvnia():
    preset = default_preset()
    assert preset.key == DEFAULT_PRESET_KEY
    assert preset.currency == CURRENCY_HRYVNIA
    assert DEFAULT_CURRENCY == CURRENCY_HRYVNIA
    assert DEFAULT_TARIFF_PER_KWH == UKRAINE_PRICE


def test_ukraine_rate_matches_the_published_tariff():
    ukraine = find_preset("ua")
    assert ukraine is not None
    assert ukraine.price_on(date(2026, 8, 10)) == UKRAINE_PRICE


def test_moscow_rate_switches_in_october():
    moscow = find_preset("ru-msk-gas")
    assert moscow is not None
    assert moscow.currency == CURRENCY_RUBLE
    assert moscow.price_on(date(2026, 8, 10)) == MOSCOW_GAS_PRICE_BEFORE_OCTOBER
    assert moscow.price_on(date(2026, 10, 1)) == MOSCOW_GAS_PRICE_FROM_OCTOBER


def test_find_preset_returns_none_for_unknown_key():
    assert find_preset("нет такого") is None


def test_preset_keys_are_unique():
    keys = preset_keys()
    assert len(keys) == len(set(keys)) == len(TARIFF_PRESETS)


def test_reference_covers_exactly_four_currencies():
    assert len(SUPPORTED_CURRENCIES) == 4
    assert set(SUPPORTED_CURRENCIES) == {
        CURRENCY_HRYVNIA,
        CURRENCY_RUBLE,
        CURRENCY_DOLLAR,
        CURRENCY_TENGE,
    }
    covered = {preset.currency for preset in TARIFF_PRESETS}
    assert covered == set(SUPPORTED_CURRENCIES), "у каждой заявленной валюты должен быть тариф"


def test_dollar_and_tenge_tariffs_are_present():
    dollar = find_preset("us")
    tenge = find_preset("kz-almaty")
    assert dollar is not None and dollar.currency == CURRENCY_DOLLAR
    assert tenge is not None and tenge.currency == CURRENCY_TENGE
    assert 0.0 < dollar.price_on(date(2026, 8, 10)) < 1.0
    assert tenge.price_on(date(2026, 8, 10)) > 1.0


def test_almaty_second_tier_is_dearer_than_the_first():
    first, second = find_preset("kz-almaty"), find_preset("kz-almaty-2")
    assert first is not None and second is not None
    today = date(2026, 8, 10)
    assert second.price_on(today) > first.price_on(today)


@pytest.mark.parametrize("preset", TARIFF_PRESETS, ids=lambda preset: preset.key)
def test_preset_data_is_sane(preset):
    assert preset.key and preset.region and preset.description and preset.source
    assert preset.currency in SUPPORTED_CURRENCIES
    assert preset.rates, "у тарифа должна быть хотя бы одна ставка"
    assert all(rate.price > 0 for rate in preset.rates)

    dates = [rate.effective_from for rate in preset.rates]
    assert dates == sorted(dates), "ставки должны идти по возрастанию даты"
    assert len(dates) == len(set(dates))


def test_match_preset_recognises_a_known_price():
    today = date(2026, 8, 10)
    found = match_preset(UKRAINE_PRICE, CURRENCY_HRYVNIA, today)
    assert found is not None and found.key == "ua"

    found = match_preset(MOSCOW_GAS_PRICE_BEFORE_OCTOBER, CURRENCY_RUBLE, today)
    assert found is not None and found.key == "ru-msk-gas"


def test_match_preset_requires_matching_currency():
    assert match_preset(UKRAINE_PRICE, CURRENCY_RUBLE, date(2026, 8, 10)) is None


def test_match_preset_returns_none_for_custom_price():
    assert match_preset(99.5, CURRENCY_HRYVNIA, date(2026, 8, 10)) is None


def test_match_preset_is_precise_enough_for_small_prices():
    today = date(2026, 8, 10)
    dollar = find_preset("us")
    assert dollar is not None
    assert match_preset(dollar.price_on(today), CURRENCY_DOLLAR, today) is dollar
    # Округление до двух знаков превратило бы 0.1791 в 0.18 - это уже не тариф
    # из справочника, а собственное значение пользователя.
    assert match_preset(0.18, CURRENCY_DOLLAR, today) is None


@pytest.mark.parametrize("readme", ["README.md", "README.en.md"])
def test_readme_documents_every_preset_and_currency(readme):
    """Обещание про четыре валюты должно подтверждаться справочником."""
    text = (ROOT / readme).read_text(encoding="utf-8")

    for preset in TARIFF_PRESETS:
        assert f"`{preset.key}`" in text, f"{readme}: не описан ключ {preset.key}"
    for currency in SUPPORTED_CURRENCIES:
        assert currency in text, f"{readme}: не упомянута валюта {currency}"
    assert "4 валюты" in text or "4 currencies" in text


def test_night_tariff_is_cheaper_than_the_day_one():
    day, night = find_preset("ua"), find_preset("ua-night")
    assert day is not None and night is not None
    today = date(2026, 8, 10)
    assert night.price_on(today) < day.price_on(today)
