"""Пользовательские настройки: загрузка, проверка и сохранение."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from watthog import constants as const

_CONFIG_DIRECTORY_NAME = "WattHog"
_CONFIG_DIRECTORY_NAME_POSIX = "watthog"
_CONFIG_FILENAME = "config.json"
_REPORTS_DIRECTORY_NAME = "reports"

MAX_EXTRA_DEVICES_WATTS = 2000.0
MAX_COMPONENT_WATTS = 1000.0
MAX_TARIFF = 1_000_000.0


def config_directory() -> Path:
    """Каталог настроек по правилам конкретной операционной системы."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(base) / _CONFIG_DIRECTORY_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / _CONFIG_DIRECTORY_NAME_POSIX


def config_path() -> Path:
    return config_directory() / _CONFIG_FILENAME


def reports_directory() -> Path:
    return config_directory() / _REPORTS_DIRECTORY_NAME


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


@dataclass
class Settings:
    """Настройки измерения и калибровки модели.

    Значения ``None`` в полях мощности означают "определить автоматически по
    железу". Пользователь может задать их вручную, если знает точные цифры
    своей системы: это самый прямой способ повысить точность.
    """

    duration_seconds: int = const.DEFAULT_DURATION_SECONDS
    sample_interval: float = const.DEFAULT_SAMPLE_INTERVAL
    tariff_per_kwh: float = 0.0
    currency: str = const.DEFAULT_CURRENCY
    psu_peak_efficiency: float = const.DEFAULT_PSU_PEAK_EFFICIENCY
    psu_rated_watts: int = const.DEFAULT_PSU_RATED_WATTS
    extra_devices_watts: float = 0.0
    cpu_peak_watts: float | None = None
    gpu_peak_watts: float | None = None
    platform_watts: float | None = None
    save_reports: bool = True

    def normalized(self) -> Settings:
        """Копия с приведёнными к допустимому диапазону значениями."""
        return Settings(
            duration_seconds=int(
                _clamp(self.duration_seconds, const.MIN_DURATION_SECONDS, const.MAX_DURATION_SECONDS)
            ),
            sample_interval=_clamp(
                self.sample_interval, const.MIN_SAMPLE_INTERVAL, const.MAX_SAMPLE_INTERVAL
            ),
            tariff_per_kwh=_clamp(self.tariff_per_kwh, 0.0, MAX_TARIFF),
            currency=(self.currency or const.DEFAULT_CURRENCY)[:8],
            psu_peak_efficiency=_clamp(
                self.psu_peak_efficiency, const.MIN_PSU_EFFICIENCY, const.MAX_PSU_EFFICIENCY
            ),
            psu_rated_watts=int(
                _clamp(self.psu_rated_watts, const.MIN_PSU_RATED_WATTS, const.MAX_PSU_RATED_WATTS)
            ),
            extra_devices_watts=_clamp(self.extra_devices_watts, 0.0, MAX_EXTRA_DEVICES_WATTS),
            cpu_peak_watts=_optional_watts(self.cpu_peak_watts),
            gpu_peak_watts=_optional_watts(self.gpu_peak_watts),
            platform_watts=_optional_watts(self.platform_watts),
            save_reports=bool(self.save_reports),
        )


def _optional_watts(value: float | None) -> float | None:
    if value is None:
        return None
    clamped = _clamp(float(value), 0.0, MAX_COMPONENT_WATTS)
    return clamped if clamped > 0.0 else None


def load_settings(path: Path | None = None) -> Settings:
    """Читает настройки с диска. Повреждённый файл заменяется значениями по умолчанию."""
    target = path or config_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()

    known = {field.name for field in fields(Settings)}
    defaults = asdict(Settings())
    payload = {key: value for key, value in raw.items() if key in known}
    try:
        return Settings(**{**defaults, **payload}).normalized()
    except (TypeError, ValueError):
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> Path | None:
    """Сохраняет настройки. Возвращает путь либо ``None``, если запись не удалась."""
    target = path or config_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(asdict(settings.normalized()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return None
    return target
