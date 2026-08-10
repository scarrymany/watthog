"""Сквозной прогон на реальном железе текущей машины."""

import json

import pytest

from watthog.cli import main
from watthog.config import Settings
from watthog.meter import PowerMeter
from watthog.session import MeasurementSession
from watthog.telemetry import TelemetryReader
from watthog.ui.report import result_to_dict, save_report

SHORT_DURATION_SECONDS = 1.0
SHORT_INTERVAL_SECONDS = 0.25
EXPECTED_SAMPLES = int(SHORT_DURATION_SECONDS / SHORT_INTERVAL_SECONDS)
CONVERSION_LOSS_LABEL = "Потери БП"
_FLOAT_TOLERANCE = 1e-9


def run_short_session():
    settings = Settings(sample_interval=SHORT_INTERVAL_SECONDS, save_reports=False)
    with TelemetryReader(settings) as reader:
        session = MeasurementSession(reader, PowerMeter(reader.profile, settings), settings)
        return session.run(SHORT_DURATION_SECONDS)


def test_reader_detects_hardware_and_sources():
    with TelemetryReader(Settings()) as reader:
        profile = reader.profile
        assert profile.cpu.name
        assert profile.cpu.physical_cores >= 1
        assert profile.cpu.peak_watts > profile.cpu.idle_watts
        assert profile.ram_gib > 0.0
        assert profile.disk_count >= 1
        assert any(source.active for source in reader.sources)


def test_session_produces_plausible_power_readings():
    result = run_short_session()

    assert result.sample_count == EXPECTED_SAMPLES
    assert not result.interrupted
    assert result.duration_seconds > 0.0
    # Ни одна реальная система не потребляет меньше ватта и больше трёх киловатт.
    assert 1.0 < result.average_watts < 3000.0
    # Среднее получается интегрированием энергии, а границы берутся прямо из
    # выборок. При постоянной мощности эти два пути расходятся в последнем
    # разряде, поэтому сравнение идёт с допуском.
    assert result.minimum_watts - _FLOAT_TOLERANCE <= result.average_watts
    assert result.average_watts <= result.maximum_watts + _FLOAT_TOLERANCE
    assert result.energy_wh > 0.0
    assert result.average_breakdown.total_ac > result.average_breakdown.total_dc


def test_breakdown_sums_to_the_reported_total():
    result = run_short_session()
    breakdown = result.average_breakdown
    components = sum(watts for label, watts in breakdown.components() if label != CONVERSION_LOSS_LABEL)
    # Точное равенство здесь неуместно: начиная с Python 3.12 встроенный sum
    # складывает вещественные числа с компенсацией погрешности, а total_dc
    # суммирует поля напрямую, и результаты расходятся в последнем разряде.
    assert components == pytest.approx(breakdown.total_dc)
    assert breakdown.total_ac == pytest.approx(breakdown.total_dc + breakdown.conversion_loss)


def test_report_is_json_serializable(tmp_path):
    result = run_short_session()
    payload = result_to_dict(result)
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload

    path = save_report(result, tmp_path / "report.json")
    assert path is not None and path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["app"] == "WattHog"


def test_cli_run_command_completes(capsys):
    exit_code = main(
        ["run", "-d", str(SHORT_DURATION_SECONDS), "-i", str(SHORT_INTERVAL_SECONDS), "--plain", "--no-save"]
    )
    assert exit_code == 0
    assert "Результат замера" in capsys.readouterr().out


def test_cli_info_command_completes(capsys):
    assert main(["info"]) == 0
    assert "Источники данных" in capsys.readouterr().out
