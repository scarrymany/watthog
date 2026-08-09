import pytest

from watthog.meter import Accuracy, PowerBreakdown
from watthog.session import Sample, _dominant_accuracy, _integrate_energy_wh, percentile
from watthog.telemetry import Telemetry


def make_sample(elapsed: float, watts: float, accuracy: Accuracy = Accuracy.MODELED) -> Sample:
    telemetry = Telemetry(
        cpu_load=0.0,
        cpu_freq_ratio=None,
        cpu_power_watts=None,
        platform_power_watts=None,
        gpus=(),
        disk_bytes_per_second=0.0,
        battery=None,
    )
    return Sample(
        elapsed=elapsed,
        watts=watts,
        breakdown=PowerBreakdown(cpu=watts),
        accuracy=accuracy,
        telemetry=telemetry,
    )


def test_percentile_of_empty_list_is_zero():
    assert percentile([], 50.0) == 0.0


def test_percentile_of_single_value_returns_it():
    assert percentile([42.0], 95.0) == 42.0


def test_percentile_interpolates_between_neighbours():
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 0.0) == 10.0
    assert percentile(values, 50.0) == 25.0
    assert percentile(values, 100.0) == 40.0


def test_percentile_ignores_input_order():
    assert percentile([40.0, 10.0, 30.0, 20.0], 50.0) == 25.0


def test_energy_integration_of_constant_power():
    samples = [make_sample(index * 0.5, 100.0) for index in range(1, 121)]
    # Сто ватт ровно шестьдесят секунд - это 100 * 60 / 3600 ватт-часов.
    assert _integrate_energy_wh(samples) == pytest.approx(100.0 * 60.0 / 3600.0)


def test_energy_integration_uses_trapezoid_rule():
    samples = [make_sample(1.0, 0.0), make_sample(2.0, 100.0)]
    # Первый отрезок держит начальное значение, второй усредняет 0 и 100.
    assert _integrate_energy_wh(samples) == pytest.approx(50.0 / 3600.0)


def test_energy_of_single_sample_covers_the_first_segment():
    assert _integrate_energy_wh([make_sample(0.5, 200.0)]) == pytest.approx(200.0 * 0.5 / 3600.0)


def test_dominant_accuracy_returns_the_weakest_link():
    samples = [
        make_sample(0.5, 10.0, Accuracy.MEASURED),
        make_sample(1.0, 10.0, Accuracy.MODELED),
        make_sample(1.5, 10.0, Accuracy.HIGH),
    ]
    assert _dominant_accuracy(samples) is Accuracy.MODELED


def test_dominant_accuracy_keeps_best_when_uniform():
    samples = [make_sample(0.5, 10.0, Accuracy.MEASURED), make_sample(1.0, 10.0, Accuracy.MEASURED)]
    assert _dominant_accuracy(samples) is Accuracy.MEASURED
