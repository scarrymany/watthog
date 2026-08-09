"""Единый доступ к телеметрии железа поверх платформенных источников.

Читатель открывает все доступные источники один раз, а затем на каждом такте
измерения отдаёт срез :class:`Telemetry`. Всё, чего на конкретной машине нет,
приходит как ``None``, и расчёт мощности использует модель вместо датчика.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

import psutil

from watthog import linuxapi, winapi
from watthog.config import Settings
from watthog.hwtypes import BatteryState
from watthog.inventory import HardwareProfile, build_profile
from watthog.nvml import NvidiaTelemetry

_CPU_PERFORMANCE_COUNTER = "cpu_performance"
_GPU_ENGINE_COUNTER = "gpu_engine"
_BASE_FREQUENCY_PATH = "/sys/devices/system/cpu/cpu0/cpufreq/base_frequency"
_KHZ_PER_MHZ = 1000.0
# Если ядро не сообщает базовую частоту, она оценивается как доля от предельной
# турбо-частоты: типичный запас турбо у настольных процессоров около 30%.
_TURBO_TO_BASE_RATIO = 0.78


@dataclass(frozen=True)
class GpuTelemetry:
    """Срез по одной видеокарте. ``power_watts`` заполнен только при наличии датчика."""

    gpu_index: int
    power_watts: float | None
    utilization: float | None
    temperature_c: float | None = None


@dataclass(frozen=True)
class Telemetry:
    cpu_load: float
    cpu_freq_ratio: float | None
    cpu_power_watts: float | None
    platform_power_watts: float | None
    gpus: tuple[GpuTelemetry, ...]
    disk_bytes_per_second: float
    battery: BatteryState | None

    @property
    def measured_system_watts(self) -> float | None:
        """Прямое измерение мощности всей системы, если оно доступно."""
        if self.battery is not None and self.battery.discharge_watts:
            return self.battery.discharge_watts
        return self.platform_power_watts


@dataclass(frozen=True)
class SourceStatus:
    name: str
    active: bool
    detail: str


class TelemetryReader:
    """Владелец всех открытых источников телеметрии на время сессии."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._nvidia = NvidiaTelemetry()
        self._counters = winapi.PerformanceCounters()
        self._rapl = linuxapi.RaplReader()
        self._linux_gpus: tuple[linuxapi.LinuxGpu, ...] = ()
        self._profile: HardwareProfile | None = None
        self._sources: tuple[SourceStatus, ...] = ()
        self._needs_gpu_counter = False
        self._base_frequency_mhz: float | None = None
        self._previous_disk_bytes: int | None = None
        self._previous_disk_at = 0.0

    def __enter__(self) -> TelemetryReader:
        self.open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    @property
    def profile(self) -> HardwareProfile:
        if self._profile is None:
            raise RuntimeError("TelemetryReader.open() не был вызван")
        return self._profile

    @property
    def sources(self) -> tuple[SourceStatus, ...]:
        return self._sources

    def open(self) -> None:
        nvidia_ok = self._nvidia.open()
        self._linux_gpus = linuxapi.discover_gpus()
        rapl_ok = self._rapl.open()

        self._profile = build_profile(self._settings, self._nvidia.devices, self._linux_gpus)
        self._needs_gpu_counter = any(
            gpu.draws_own_power and not gpu.has_telemetry for gpu in self._profile.gpus
        )

        counters_ok = self._counters.open()
        cpu_counter_ok = False
        if counters_ok:
            cpu_counter_ok = self._counters.add_scalar(
                _CPU_PERFORMANCE_COUNTER, winapi.COUNTER_CPU_PERFORMANCE
            )
            if self._needs_gpu_counter:
                self._counters.add_group(_GPU_ENGINE_COUNTER, winapi.COUNTER_GPU_ENGINE)
            self._counters.collect()

        self._base_frequency_mhz = _detect_base_frequency_mhz()
        psutil.cpu_percent(interval=None)
        self._prime_disk_counters()
        self._sources = self._describe_sources(nvidia_ok, rapl_ok, cpu_counter_ok)

    def read(self) -> Telemetry:
        self._counters.collect()

        cpu_load = min(1.0, max(0.0, psutil.cpu_percent(interval=None) / 100.0))
        battery = winapi.read_battery_state() or linuxapi.read_battery_state()
        rapl_watts = self._rapl.sample_watts()
        platform_watts = rapl_watts if self._rapl.covers_whole_platform else None
        cpu_watts = None if self._rapl.covers_whole_platform else rapl_watts

        return Telemetry(
            cpu_load=cpu_load,
            cpu_freq_ratio=self._read_frequency_ratio(),
            cpu_power_watts=cpu_watts,
            platform_power_watts=platform_watts,
            gpus=self._read_gpus(),
            disk_bytes_per_second=self._read_disk_throughput(),
            battery=battery,
        )

    def close(self) -> None:
        self._nvidia.close()
        self._counters.close()

    # -- отдельные источники ------------------------------------------------

    def _read_frequency_ratio(self) -> float | None:
        counter_value = self._counters.scalar(_CPU_PERFORMANCE_COUNTER)
        if counter_value is not None and counter_value > 0.0:
            return counter_value / 100.0
        if self._base_frequency_mhz:
            try:
                current = psutil.cpu_freq()
            except (OSError, RuntimeError, NotImplementedError):
                return None
            if current is not None and current.current > 0.0:
                return current.current / self._base_frequency_mhz
        return None

    def _read_gpus(self) -> tuple[GpuTelemetry, ...]:
        nvidia_samples = {sample.index: sample for sample in self._nvidia.sample()}
        engine_utilization: float | None = None
        if self._needs_gpu_counter:
            engine_utilization = winapi.peak_gpu_utilization(self._counters.group(_GPU_ENGINE_COUNTER))

        readings: list[GpuTelemetry] = []
        for index, gpu in enumerate(self.profile.gpus):
            if not gpu.draws_own_power:
                continue

            if gpu.nvml_index is not None and gpu.nvml_index in nvidia_samples:
                sample = nvidia_samples[gpu.nvml_index]
                readings.append(
                    GpuTelemetry(index, sample.power_watts, sample.utilization, sample.temperature_c)
                )
                continue

            if gpu.sysfs_index is not None and gpu.sysfs_index < len(self._linux_gpus):
                device = self._linux_gpus[gpu.sysfs_index]
                readings.append(GpuTelemetry(index, device.read_power_watts(), device.read_utilization()))
                continue

            utilization = engine_utilization
            if utilization is None and self._linux_gpus:
                utilization = _first_linux_utilization(self._linux_gpus)
            readings.append(GpuTelemetry(index, None, utilization))
        return tuple(readings)

    def _prime_disk_counters(self) -> None:
        total = _total_disk_bytes()
        if total is not None:
            self._previous_disk_bytes = total
            self._previous_disk_at = time.monotonic()

    def _read_disk_throughput(self) -> float:
        total = _total_disk_bytes()
        now = time.monotonic()
        if total is None or self._previous_disk_bytes is None:
            return 0.0
        elapsed = now - self._previous_disk_at
        delta = total - self._previous_disk_bytes
        self._previous_disk_bytes = total
        self._previous_disk_at = now
        if elapsed <= 0.0 or delta < 0:
            return 0.0
        return delta / elapsed

    def _describe_sources(self, nvidia_ok: bool, rapl_ok: bool, cpu_counter_ok: bool) -> tuple[SourceStatus, ...]:
        statuses: list[SourceStatus] = []

        if nvidia_ok:
            names = ", ".join(device.name for device in self._nvidia.devices)
            statuses.append(SourceStatus("NVML (NVIDIA)", True, f"реальные ватты: {names}"))
        else:
            statuses.append(SourceStatus("NVML (NVIDIA)", False, "видеокарта NVIDIA не найдена"))

        sysfs_gpus = [gpu for gpu in self._linux_gpus if gpu.has_power_sensor and not gpu.is_nvidia]
        if sysfs_gpus:
            names = ", ".join(gpu.name for gpu in sysfs_gpus)
            statuses.append(SourceStatus("hwmon (AMD/Intel GPU)", True, f"реальные ватты: {names}"))

        if rapl_ok:
            scope = "вся платформа" if self._rapl.covers_whole_platform else "пакет процессора"
            statuses.append(SourceStatus("RAPL", True, f"реальные ватты, {scope}"))
        elif linuxapi.IS_LINUX:
            reason = "нет прав на чтение, запустите через sudo" if self._rapl.permission_denied else "недоступен"
            statuses.append(SourceStatus("RAPL", False, reason))

        if cpu_counter_ok:
            statuses.append(SourceStatus("PDH", True, "множитель частоты процессора и загрузка GPU"))

        battery = winapi.read_battery_state() or linuxapi.read_battery_state()
        if battery is not None and battery.present:
            detail = (
                "прямое измерение всей системы при работе от батареи"
                if battery.discharge_watts
                else "подключено питание, разряд не измеряется"
            )
            statuses.append(SourceStatus("Батарея", bool(battery.discharge_watts), detail))

        statuses.append(SourceStatus("psutil", True, "загрузка процессора, память, дисковый ввод-вывод"))
        return tuple(statuses)


def _total_disk_bytes() -> int | None:
    try:
        counters = psutil.disk_io_counters()
    except (OSError, RuntimeError):
        return None
    if counters is None:
        return None
    return counters.read_bytes + counters.write_bytes


def _first_linux_utilization(gpus: tuple[linuxapi.LinuxGpu, ...]) -> float | None:
    values = [value for value in (gpu.read_utilization() for gpu in gpus) if value is not None]
    return max(values) if values else None


def _detect_base_frequency_mhz() -> float | None:
    """Базовая частота процессора, относительно которой считается множитель.

    В Windows множитель приходит готовым из счётчика PDH, поэтому функция
    нужна только для Linux.
    """
    if sys.platform == "win32":
        return None
    try:
        with open(_BASE_FREQUENCY_PATH, encoding="utf-8") as handle:
            return int(handle.read().strip()) / _KHZ_PER_MHZ
    except (OSError, ValueError):
        pass
    try:
        frequency = psutil.cpu_freq()
    except (OSError, RuntimeError, NotImplementedError):
        return None
    if frequency is None or not frequency.max:
        return None
    return frequency.max * _TURBO_TO_BASE_RATIO
