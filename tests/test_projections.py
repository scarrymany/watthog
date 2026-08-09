from watthog.projections import (
    build_projections,
    consumption_tier,
    energy_kwh,
    format_span,
    plural_ru,
)

_HOUR_FORMS = ("час", "часа", "часов")


def test_energy_kwh_converts_watt_hours_to_kilowatt_hours():
    assert energy_kwh(1000.0, 1.0) == 1.0
    assert energy_kwh(250.0, 4.0) == 1.0
    assert energy_kwh(0.0, 24.0) == 0.0


def test_build_projections_covers_requested_horizons():
    projections = build_projections(300.0, hours=(1.0, 10.0, 12.0, 24.0))
    assert [projection.hours for projection in projections] == [1.0, 10.0, 12.0, 24.0]
    assert projections[0].kwh == 0.3
    assert projections[1].kwh == 3.0
    assert projections[3].kwh == 7.2


def test_build_projections_without_tariff_has_no_cost():
    assert all(projection.cost is None for projection in build_projections(120.0))


def test_build_projections_with_tariff_multiplies_energy():
    projections = build_projections(500.0, tariff_per_kwh=6.0, hours=(10.0,))
    assert projections[0].cost == 30.0


def test_plural_ru_picks_correct_form():
    assert plural_ru(1, _HOUR_FORMS) == "час"
    assert plural_ru(2, _HOUR_FORMS) == "часа"
    assert plural_ru(5, _HOUR_FORMS) == "часов"
    assert plural_ru(11, _HOUR_FORMS) == "часов"
    assert plural_ru(21, _HOUR_FORMS) == "час"
    assert plural_ru(112, _HOUR_FORMS) == "часов"


def test_format_span_uses_special_labels_and_plurals():
    assert format_span(1.0) == "1 час"
    assert format_span(10.0) == "10 часов"
    assert format_span(12.0) == "12 часов"
    assert format_span(24.0) == "24 часа (сутки)"
    assert format_span(168.0) == "7 дней (неделя)"
    assert format_span(720.0) == "30 дней (месяц)"
    assert format_span(48.0) == "2 дня"


def test_consumption_tier_grows_with_power():
    assert consumption_tier(20.0)[0] == "Экономный"
    assert consumption_tier(200.0)[0] == "Заметный"
    assert consumption_tier(5000.0)[0] == "Ненасытный"
