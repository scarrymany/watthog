"""Определение состава железа и его энергетического профиля."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from enum import Enum

import psutil

from watthog import constants as const
from watthog import linuxapi, tdp_tables, winapi
from watthog.config import Settings
from watthog.nvml import NvidiaDevice
from watthog.tdp_tables import CpuClass


class FormFactor(Enum):
    DESKTOP = "десктоп"
    LAPTOP = "ноутбук"
    COMPACT = "мини-ПК"


class GpuKind(Enum):
    DISCRETE = "дискретная"
    INTEGRATED = "встроенная"
    VIRTUAL = "виртуальная"


@dataclass(frozen=True)
class CpuInfo:
    name: str
    physical_cores: int
    logical_cores: int
    cpu_class: CpuClass
    peak_watts: float
    idle_watts: float
    power_source: str


@dataclass(frozen=True)
class GpuInfo:
    """Видеоадаптер и способ узнать его мощность.

    ``nvml_index`` и ``sysfs_index`` указывают на источник телеметрии. Если оба
    пусты, мощность считается по загрузке и справочному пределу платы.
    """

    name: str
    kind: GpuKind
    peak_watts: float
    idle_watts: float
    power_source: str
    nvml_index: int | None = None
    sysfs_index: int | None = None

    @property
    def has_telemetry(self) -> bool:
        return self.nvml_index is not None or self.sysfs_index is not None

    @property
    def draws_own_power(self) -> bool:
        """Встроенная графика питается от пакета процессора, виртуальной питания не нужно."""
        return self.kind is GpuKind.DISCRETE


@dataclass(frozen=True)
class HardwareProfile:
    form_factor: FormFactor
    cpu: CpuInfo
    gpus: tuple[GpuInfo, ...]
    ram_gib: float
    disk_count: int
    has_battery: bool
    os_description: str

    @property
    def discrete_gpus(self) -> tuple[GpuInfo, ...]:
        return tuple(gpu for gpu in self.gpus if gpu.draws_own_power)

    @property
    def is_portable(self) -> bool:
        return self.form_factor is FormFactor.LAPTOP

    @property
    def platform_baseline_watts(self) -> float:
        if self.form_factor is FormFactor.LAPTOP:
            return const.PLATFORM_WATTS_LAPTOP
        if self.form_factor is FormFactor.COMPACT:
            return const.PLATFORM_WATTS_COMPACT
        return const.PLATFORM_WATTS_DESKTOP


def build_profile(
    settings: Settings,
    nvidia_devices: tuple[NvidiaDevice, ...] = (),
    linux_gpus: tuple[linuxapi.LinuxGpu, ...] = (),
) -> HardwareProfile:
    """Собирает профиль системы из доступных на текущей платформе источников."""
    cpu = _detect_cpu(settings)
    has_battery = _detect_battery()
    form_factor = _detect_form_factor(cpu.cpu_class, has_battery)
    gpus = _detect_gpus(settings, nvidia_devices, linux_gpus)

    return HardwareProfile(
        form_factor=form_factor,
        cpu=cpu,
        gpus=gpus,
        ram_gib=psutil.virtual_memory().total / const.BYTES_PER_GIB,
        disk_count=_count_disks(),
        has_battery=has_battery,
        os_description=_describe_os(),
    )


def _detect_cpu(settings: Settings) -> CpuInfo:
    name = winapi.read_cpu_name() or linuxapi.read_cpu_name() or platform.processor() or "Неизвестный процессор"
    physical = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
    logical = psutil.cpu_count(logical=True) or physical

    peak, idle, source = tdp_tables.lookup_cpu_power(name, physical)
    if settings.cpu_peak_watts is not None:
        # Простой масштабируется вместе с пиком: пользователь задаёт порядок
        # мощности процессора, а не отдельно каждую точку кривой.
        idle = idle * settings.cpu_peak_watts / peak if peak > 0 else idle
        peak = settings.cpu_peak_watts
        source = tdp_tables.MATCH_SOURCE_SETTINGS

    return CpuInfo(
        name=name,
        physical_cores=physical,
        logical_cores=logical,
        cpu_class=tdp_tables.classify_cpu(name),
        peak_watts=peak,
        idle_watts=min(idle, peak * 0.9),
        power_source=source,
    )


def _detect_battery() -> bool:
    state = winapi.read_battery_state() or linuxapi.read_battery_state()
    return state.present if state is not None else False


def _detect_form_factor(cpu_class: CpuClass, has_battery: bool) -> FormFactor:
    if has_battery or linuxapi.is_portable_chassis():
        return FormFactor.LAPTOP
    # Мобильный процессор без батареи - это мини-ПК или неттоп: платформа
    # экономичная, но собственного экрана у неё нет.
    if tdp_tables.is_mobile_cpu(cpu_class):
        return FormFactor.COMPACT
    return FormFactor.DESKTOP


def _detect_gpus(
    settings: Settings,
    nvidia_devices: tuple[NvidiaDevice, ...],
    linux_gpus: tuple[linuxapi.LinuxGpu, ...],
) -> tuple[GpuInfo, ...]:
    if linux_gpus:
        return _detect_gpus_linux(settings, nvidia_devices, linux_gpus)
    return _detect_gpus_windows(settings, nvidia_devices)


def _detect_gpus_windows(settings: Settings, nvidia_devices: tuple[NvidiaDevice, ...]) -> tuple[GpuInfo, ...]:
    names = list(winapi.read_gpu_names())
    unmatched_nvidia = list(nvidia_devices)

    gpus: list[GpuInfo] = []
    for name in names:
        nvml_index = _take_matching_nvml(name, unmatched_nvidia)
        gpus.append(_build_gpu(settings, name, nvml_index=nvml_index))

    # Карты, которые NVML видит, а реестр по какой-то причине нет.
    for device in unmatched_nvidia:
        gpus.append(_build_gpu(settings, device.name, nvml_index=device.index))

    if not gpus and nvidia_devices:
        gpus = [_build_gpu(settings, device.name, nvml_index=device.index) for device in nvidia_devices]
    return tuple(gpus)


def _detect_gpus_linux(
    settings: Settings,
    nvidia_devices: tuple[NvidiaDevice, ...],
    linux_gpus: tuple[linuxapi.LinuxGpu, ...],
) -> tuple[GpuInfo, ...]:
    unmatched_nvidia = list(nvidia_devices)
    gpus: list[GpuInfo] = []
    for index, gpu in enumerate(linux_gpus):
        nvml_index: int | None = None
        name = gpu.name
        if gpu.is_nvidia and unmatched_nvidia:
            device = unmatched_nvidia.pop(0)
            nvml_index = device.index
            name = device.name
        sysfs_index = index if (gpu.has_power_sensor and nvml_index is None) else None
        gpus.append(_build_gpu(settings, name, nvml_index=nvml_index, sysfs_index=sysfs_index))
    return tuple(gpus)


def _take_matching_nvml(name: str, candidates: list[NvidiaDevice]) -> int | None:
    normalized = tdp_tables.normalize_name(name)
    for position, device in enumerate(candidates):
        if tdp_tables.normalize_name(device.name) == normalized:
            return candidates.pop(position).index
    return None


def _build_gpu(
    settings: Settings,
    name: str,
    nvml_index: int | None = None,
    sysfs_index: int | None = None,
) -> GpuInfo:
    if tdp_tables.is_virtual_gpu(name):
        kind = GpuKind.VIRTUAL
    elif tdp_tables.is_integrated_gpu(name):
        kind = GpuKind.INTEGRATED
    else:
        kind = GpuKind.DISCRETE

    if kind is not GpuKind.DISCRETE:
        return GpuInfo(name=name, kind=kind, peak_watts=0.0, idle_watts=0.0, power_source="-")

    peak, idle, source = tdp_tables.lookup_gpu_power(name)
    if settings.gpu_peak_watts is not None:
        idle = idle * settings.gpu_peak_watts / peak if peak > 0 else idle
        peak = settings.gpu_peak_watts
        source = tdp_tables.MATCH_SOURCE_SETTINGS
    if nvml_index is not None or sysfs_index is not None:
        source = tdp_tables.MATCH_SOURCE_TELEMETRY

    return GpuInfo(
        name=name,
        kind=kind,
        peak_watts=peak,
        idle_watts=min(idle, peak * 0.9),
        power_source=source,
        nvml_index=nvml_index,
        sysfs_index=sysfs_index,
    )


def _count_disks() -> int:
    try:
        counters = psutil.disk_io_counters(perdisk=True)
    except (OSError, RuntimeError):
        return 1
    return max(1, len(counters or {}))


def _describe_os() -> str:
    if sys.platform == "win32":
        release = platform.release()
        version = platform.version()
        return f"Windows {release} ({version})"
    if sys.platform.startswith("linux"):
        pretty = _linux_pretty_name()
        return pretty or f"Linux {platform.release()}"
    return platform.platform()


def _linux_pretty_name() -> str | None:
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        return None
    return None
