import json

from watthog import constants as const
from watthog.config import MAX_COMPONENT_WATTS, Settings, load_settings, save_settings


def test_defaults_survive_normalization():
    settings = Settings()
    assert settings.normalized() == settings


def test_normalization_clamps_out_of_range_values():
    settings = Settings(
        duration_seconds=10 ** 9,
        sample_interval=0.001,
        tariff_per_kwh=-5.0,
        psu_peak_efficiency=5.0,
        psu_rated_watts=1,
        extra_devices_watts=-10.0,
    ).normalized()

    assert settings.duration_seconds == const.MAX_DURATION_SECONDS
    assert settings.sample_interval == const.MIN_SAMPLE_INTERVAL
    assert settings.tariff_per_kwh == 0.0
    assert settings.psu_peak_efficiency == const.MAX_PSU_EFFICIENCY
    assert settings.psu_rated_watts == const.MIN_PSU_RATED_WATTS
    assert settings.extra_devices_watts == 0.0


def test_zero_component_override_means_automatic():
    settings = Settings(cpu_peak_watts=0.0, gpu_peak_watts=5000.0).normalized()
    assert settings.cpu_peak_watts is None
    assert settings.gpu_peak_watts == MAX_COMPONENT_WATTS


def test_empty_currency_falls_back_to_default():
    assert Settings(currency="").normalized().currency == const.DEFAULT_CURRENCY


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "config.json"
    original = Settings(duration_seconds=90, tariff_per_kwh=6.5, currency="₴", cpu_peak_watts=142.0)

    assert save_settings(original, path) == path
    assert load_settings(path) == original.normalized()


def test_missing_file_yields_defaults(tmp_path):
    assert load_settings(tmp_path / "absent.json") == Settings()


def test_corrupt_file_yields_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert load_settings(path) == Settings()


def test_non_object_json_yields_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_settings(path) == Settings()


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"duration_seconds": 45, "unknown_option": "нет такого"}),
        encoding="utf-8",
    )
    assert load_settings(path).duration_seconds == 45


def test_partial_file_keeps_defaults_for_missing_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"tariff_per_kwh": 4.2}), encoding="utf-8")

    settings = load_settings(path)
    assert settings.tariff_per_kwh == 4.2
    assert settings.duration_seconds == const.DEFAULT_DURATION_SECONDS
