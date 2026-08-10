from watthog.formatting import (
    THOUSANDS_SEPARATOR,
    format_kwh,
    format_money,
    format_price,
    format_watts,
    parse_number,
    shorten_hardware_name,
)


def test_format_price_keeps_two_decimals_for_large_tariffs():
    assert format_price(29.34) == "29.34"
    assert format_price(8.0) == "8.00"
    assert format_price(4.32) == "4.32"
    assert format_price(1.0) == "1.00"


def test_format_price_keeps_precision_for_small_tariffs():
    # Доллар за киловатт-час - это доли единицы: два знака округлили бы разные
    # тарифы до одного и того же числа.
    assert format_price(0.1791) == "0.1791"
    assert format_price(0.18) == "0.18"
    assert format_price(0.5) == "0.5"
    assert format_price(0.0) == "0"


def test_format_money_groups_digits_with_a_non_breaking_space():
    assert format_money(1211.71) == f"1{THOUSANDS_SEPARATOR}211.71"
    assert format_money(7.5) == "7.50"
    assert " " not in format_money(1211.71), "обычный пробел позволил бы разорвать число переносом"


def test_format_watts_scales_precision():
    assert format_watts(312.4) == "312"
    assert format_watts(42.37) == "42.4"
    assert format_watts(3.216) == "3.22"


def test_format_kwh_scales_precision():
    assert format_kwh(221.84) == "221.8"
    assert format_kwh(3.0812) == "3.08"
    assert format_kwh(0.3081) == "0.308"


def test_parse_number_ignores_units_and_accepts_a_comma():
    assert parse_number("650 Вт") == 650.0
    assert parse_number("0,5 с") == 0.5
    assert parse_number("29.34 ₸") == 29.34
    assert parse_number("-3") == -3.0
    assert parse_number("без числа") is None


def test_shorten_hardware_name_drops_marketing_noise():
    assert shorten_hardware_name("AMD Ryzen 7 7800X3D 8-Core Processor") == "AMD Ryzen 7 7800X3D"
    assert shorten_hardware_name("Intel(R) Core(TM) i9-14900K CPU @ 3.20GHz") == "Intel Core i9-14900K"
    assert shorten_hardware_name("NVIDIA GeForce RTX 5070") == "NVIDIA GeForce RTX 5070"


def test_shorten_hardware_name_never_returns_an_empty_string():
    assert shorten_hardware_name("Processor") == "Processor"
