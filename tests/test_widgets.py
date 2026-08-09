from watthog.ui.widgets import (
    area_chart,
    big_number,
    chart_bounds,
    format_kwh,
    format_watts,
    gauge,
    progress_bar,
)

CHART_WIDTH = 40
CHART_HEIGHT = 6


def test_format_watts_scales_precision_with_magnitude():
    assert format_watts(312.4) == "312"
    assert format_watts(42.37) == "42.4"
    assert format_watts(3.216) == "3.22"


def test_format_kwh_scales_precision_with_magnitude():
    assert format_kwh(221.84) == "221.8"
    assert format_kwh(3.0812) == "3.08"
    assert format_kwh(0.3081) == "0.308"


def test_big_number_has_fixed_height():
    assert len(big_number("308", "white").plain.split("\n")) == 5
    assert len(big_number("7.5", "white").plain.split("\n")) == 5


def test_big_number_skips_unsupported_characters():
    assert big_number("1x2", "white").plain == big_number("12", "white").plain


def test_gauge_fills_proportionally():
    assert len(gauge(0.5, 1.0, 10).plain) == 10
    assert gauge(1.0, 1.0, 10).plain == "█" * 10
    assert gauge(0.0, 1.0, 10).plain == "░" * 10
    assert gauge(2.0, 1.0, 10).plain == "█" * 10


def test_gauge_with_zero_maximum_stays_empty():
    assert gauge(50.0, 0.0, 8).plain == "░" * 8


def test_progress_bar_fills_proportionally():
    assert progress_bar(0.0, 10).plain == "▱" * 10
    assert progress_bar(1.0, 10).plain == "▰" * 10
    assert len(progress_bar(0.37, 10).plain) == 10


def test_chart_bounds_start_at_zero_for_wide_spread():
    floor, ceiling = chart_bounds([10.0, 100.0])
    assert floor == 0.0
    assert ceiling > 100.0


def test_chart_bounds_zoom_in_for_narrow_spread():
    floor, ceiling = chart_bounds([300.0, 305.0, 302.0])
    assert floor > 0.0
    assert floor < 300.0
    assert ceiling > 305.0


def test_chart_bounds_handle_constant_series():
    floor, ceiling = chart_bounds([250.0] * 10)
    assert floor < 250.0 < ceiling


def test_chart_bounds_of_empty_series_are_safe():
    assert chart_bounds([]) == (0.0, 1.0)


def test_area_chart_matches_requested_size():
    rows = area_chart([1.0, 5.0, 3.0], CHART_WIDTH, CHART_HEIGHT, 5.0).plain.split("\n")
    assert len(rows) == CHART_HEIGHT
    assert all(len(row) == CHART_WIDTH for row in rows)


def test_area_chart_compresses_long_history():
    values = [float(index % 17) for index in range(500)]
    rows = area_chart(values, CHART_WIDTH, CHART_HEIGHT, 16.0).plain.split("\n")
    assert all(len(row) == CHART_WIDTH for row in rows)


def test_area_chart_of_empty_history_is_blank():
    rows = area_chart([], CHART_WIDTH, CHART_HEIGHT, 100.0).plain.split("\n")
    assert rows == [" " * CHART_WIDTH] * CHART_HEIGHT


def test_area_chart_top_row_is_filled_at_ceiling():
    rows = area_chart([10.0], 1, 4, 10.0).plain.split("\n")
    assert rows[0] == "█"


def test_area_chart_respects_floor():
    # Значение на уровне пола не должно рисовать ни одного блока.
    rows = area_chart([100.0], 1, 4, 200.0, floor=100.0).plain.split("\n")
    assert set("".join(rows)) == {" "}
