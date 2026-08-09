"""Расчёт мощности системы по срезу телеметрии.

Логика одна и та же на всех платформах: там, где есть настоящий датчик, берётся
его показание, а всё остальное считается по модели. Если доступно прямое
измерение мощности всей системы (разряд батареи или домен RAPL psys), оценки
компонентов пропорционально подгоняются под это значение, чтобы разбивка
оставалась информативной, а сумма - точной.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from watthog import constants as const
from watthog.config import Settings
from watthog.inventory import FormFactor, GpuInfo, HardwareProfile
from watthog.telemetry import Telemetry


class Accuracy(Enum):
    """Насколько результат опирается на датчики, а не на модель."""

    MEASURED = "измерено"
    HIGH = "высокая"
    MEDIUM = "средняя"
    MODELED = "расчётная"


ACCURACY_DETAILS = {
    Accuracy.MEASURED: "прямое измерение мощности всей системы",
    Accuracy.HIGH: "реальные датчики процессора и видеокарты",
    Accuracy.MEDIUM: "реальный датчик видеокарты, процессор по модели",
    Accuracy.MODELED: "расчёт по загрузке и справочным пределам мощности",
}

COMPONENT_LABELS = (
    ("cpu", "Процессор"),
    ("gpu", "Видеокарта"),
    ("ram", "Память"),
    ("storage", "Накопители"),
    ("platform", "Плата"),
    ("extra_devices", "Периферия"),
    ("conversion_loss", "Потери БП"),
)


@dataclass(frozen=True)
class PowerBreakdown:
    """Мощность по компонентам в ваттах.

    Компоненты - это потребление по постоянному току, то есть то, что реально
    едят железки. ``conversion_loss`` - потери блока питания или адаптера,
    которые тоже оплачиваются по счётчику.
    """

    cpu: float = 0.0
    gpu: float = 0.0
    ram: float = 0.0
    storage: float = 0.0
    platform: float = 0.0
    extra_devices: float = 0.0
    conversion_loss: float = 0.0

    @property
    def total_dc(self) -> float:
        return self.cpu + self.gpu + self.ram + self.storage + self.platform + self.extra_devices

    @property
    def total_ac(self) -> float:
        return self.total_dc + self.conversion_loss

    def components(self) -> tuple[tuple[str, float], ...]:
        return tuple((label, getattr(self, field)) for field, label in COMPONENT_LABELS)

    def __add__(self, other: PowerBreakdown) -> PowerBreakdown:
        return PowerBreakdown(
            cpu=self.cpu + other.cpu,
            gpu=self.gpu + other.gpu,
            ram=self.ram + other.ram,
            storage=self.storage + other.storage,
            platform=self.platform + other.platform,
            extra_devices=self.extra_devices + other.extra_devices,
            conversion_loss=self.conversion_loss + other.conversion_loss,
        )

    def scaled(self, factor: float) -> PowerBreakdown:
        return PowerBreakdown(
            cpu=self.cpu * factor,
            gpu=self.gpu * factor,
            ram=self.ram * factor,
            storage=self.storage * factor,
            platform=self.platform * factor,
            extra_devices=self.extra_devices * factor,
            conversion_loss=self.conversion_loss * factor,
        )


def average_breakdown(samples: list[PowerBreakdown]) -> PowerBreakdown:
    if not samples:
        return PowerBreakdown()
    total = PowerBreakdown()
    for sample in samples:
        total = total + sample
    return total.scaled(1.0 / len(samples))


class PowerMeter:
    """Превращает срез телеметрии в разбивку мощности по компонентам."""

    def __init__(self, profile: HardwareProfile, settings: Settings) -> None:
        self._profile = profile
        self._settings = settings
        self._platform_watts = (
            settings.platform_watts if settings.platform_watts is not None else profile.platform_baseline_watts
        )
        self._portable_power = profile.form_factor in (FormFactor.LAPTOP, FormFactor.COMPACT)

    def measure(self, telemetry: Telemetry) -> PowerBreakdown:
        breakdown = PowerBreakdown(
            cpu=self._cpu_watts(telemetry),
            gpu=self._gpu_watts(telemetry),
            ram=self._ram_watts(telemetry),
            storage=self._storage_watts(telemetry),
            platform=self._platform_watts,
        )

        measured_total = telemetry.measured_system_watts
        if measured_total and breakdown.total_dc > 0.0:
            breakdown = breakdown.scaled(measured_total / breakdown.total_dc)

        breakdown = replace(breakdown, extra_devices=self._settings.extra_devices_watts)
        return replace(breakdown, conversion_loss=self._conversion_loss(breakdown.total_dc))

    def accuracy(self, telemetry: Telemetry) -> Accuracy:
        if telemetry.measured_system_watts:
            return Accuracy.MEASURED
        cpu_measured = telemetry.cpu_power_watts is not None
        gpu_measured = any(reading.power_watts is not None for reading in telemetry.gpus)
        if cpu_measured and (gpu_measured or not self._profile.discrete_gpus):
            return Accuracy.HIGH
        if gpu_measured:
            return Accuracy.MEDIUM
        return Accuracy.MODELED

    # -- компоненты ---------------------------------------------------------

    def _cpu_watts(self, telemetry: Telemetry) -> float:
        package = telemetry.cpu_power_watts
        if package is None:
            package = self._model_cpu_package(telemetry)
        # Пакет процессора питается через VRM платы, и эти потери в его
        # телеметрию не входят, хотя из розетки берутся.
        return package / const.VRM_EFFICIENCY

    def _model_cpu_package(self, telemetry: Telemetry) -> float:
        cpu = self._profile.cpu
        dynamic_range = max(0.0, cpu.peak_watts - cpu.idle_watts)
        load_factor = telemetry.cpu_load ** const.CPU_LOAD_EXPONENT

        frequency_factor = 1.0
        if telemetry.cpu_freq_ratio is not None:
            ratio = min(
                const.CPU_FREQ_RATIO_MAX, max(const.CPU_FREQ_RATIO_MIN, telemetry.cpu_freq_ratio)
            )
            frequency_factor = (ratio / const.CPU_REFERENCE_FREQ_RATIO) ** const.CPU_FREQ_EXPONENT

        return cpu.idle_watts + dynamic_range * load_factor * frequency_factor

    def _gpu_watts(self, telemetry: Telemetry) -> float:
        readings = {reading.gpu_index: reading for reading in telemetry.gpus}
        total = 0.0
        for index, gpu in enumerate(self._profile.gpus):
            if not gpu.draws_own_power:
                continue
            reading = readings.get(index)
            if reading is not None and reading.power_watts is not None:
                total += reading.power_watts
                continue
            utilization = reading.utilization if reading is not None else None
            total += _model_gpu_power(gpu, utilization)
        return total

    def _ram_watts(self, telemetry: Telemetry) -> float:
        gib = self._profile.ram_gib
        if self._portable_power:
            base = const.RAM_WATTS_PER_GIB_LAPTOP
            under_load = const.RAM_LOAD_WATTS_PER_GIB_LAPTOP
        else:
            base = const.RAM_WATTS_PER_GIB_DESKTOP
            under_load = const.RAM_LOAD_WATTS_PER_GIB_DESKTOP
        return gib * (base + under_load * telemetry.cpu_load)

    def _storage_watts(self, telemetry: Telemetry) -> float:
        if self._portable_power:
            idle = const.DISK_IDLE_WATTS_LAPTOP
            active = const.DISK_ACTIVE_WATTS_LAPTOP
        else:
            idle = const.DISK_IDLE_WATTS_DESKTOP
            active = const.DISK_ACTIVE_WATTS_DESKTOP
        saturation = min(1.0, telemetry.disk_bytes_per_second / const.DISK_SATURATION_BYTES_PER_SECOND)
        # Простой оплачивает каждый накопитель, а активная надбавка привязана к
        # общему потоку данных: одновременно нагружен обычно один диск.
        return self._profile.disk_count * idle + active * saturation

    def _conversion_loss(self, total_dc: float) -> float:
        efficiency = self._efficiency(total_dc)
        if efficiency <= 0.0:
            return 0.0
        return total_dc / efficiency - total_dc

    def _efficiency(self, total_dc: float) -> float:
        if self._portable_power:
            return const.LAPTOP_ADAPTER_EFFICIENCY
        rated = max(1, self._settings.psu_rated_watts)
        load_ratio = total_dc / rated
        return self._settings.psu_peak_efficiency * _interpolate(const.PSU_EFFICIENCY_CURVE, load_ratio)


def _model_gpu_power(gpu: GpuInfo, utilization: float | None) -> float:
    if utilization is None:
        return gpu.idle_watts
    busy = min(1.0, max(0.0, utilization))
    return gpu.idle_watts + max(0.0, gpu.peak_watts - gpu.idle_watts) * busy ** const.GPU_LOAD_EXPONENT


def _interpolate(curve: tuple[tuple[float, float], ...], x: float) -> float:
    """Кусочно-линейная интерполяция по возрастающей таблице точек."""
    if x <= curve[0][0]:
        return curve[0][1]
    if x >= curve[-1][0]:
        return curve[-1][1]
    for (left_x, left_y), (right_x, right_y) in zip(curve, curve[1:], strict=False):
        if left_x <= x <= right_x:
            span = right_x - left_x
            if span <= 0.0:
                return left_y
            return left_y + (right_y - left_y) * (x - left_x) / span
    return curve[-1][1]
