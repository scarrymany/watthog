"""Сквозной прогон на реальном железе текущей машины."""

import json

from watthog.cli import main
from watthog.config import Settings
from watthog.meter import PowerMeter
from watthog.session import MeasurementSession
from watthog.telemetry import TelemetryReader
from watthog.ui.report import result_to_dict, save_report

SHORT_DURATION_SECONDS = 1.0
SHORT_INTERVAL_SECONDS = 0.25
EXPECTED_SAMPLES = int(SHORT_DURATION_SECONDS / SHORT_INTERVAL_SECONDS)


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
    assert result.minimum_watts <= result.average_watts <= result.maximum_watts
    assert result.energy_wh > 0.0
    assert result.average_breakdown.total_ac > result.average_breakdown.total_dc


def test_breakdown_sums_to_the_reported_total():
    result = run_short_session()
    breakdown = result.average_breakdown
    components = sum(watts for label, watts in breakdown.components() if label != "Потери БП")
    assert components == breakdown.total_dc


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
