"""Источники телеметрии Linux через sysfs.

В Linux доступно заметно больше настоящих датчиков, чем в Windows:

* RAPL (`/sys/class/powercap`) - счётчик энергии пакета процессора. Даёт
  реальную мощность CPU в ваттах. На большинстве дистрибутивов файл счётчика
  закрыт от обычного пользователя, поэтому источник считается опциональным.
* hwmon видеокарт (`/sys/class/drm/card*/device/hwmon`) - реальная мощность
  плат AMD и Intel. Видеокарты NVIDIA читаются через NVML.
* `/sys/class/power_supply` - состояние батареи и мгновенная мощность разряда.

Все функции молча возвращают ``None`` при отсутствии доступа или файла.
"""

from __future__ import annotations

import glob
import os
import re
import sys
import time
from dataclasses import dataclass

from watthog.hwtypes import BatteryState

IS_LINUX = sys.platform.startswith("linux")

_POWERCAP_ROOT = "/sys/class/powercap"
_DRM_ROOT = "/sys/class/drm"
_POWER_SUPPLY_ROOT = "/sys/class/power_supply"
_CPUINFO_PATH = "/proc/cpuinfo"
_CHASSIS_TYPE_PATH = "/sys/class/dmi/id/chassis_type"

_MICRO = 1_000_000.0
# `current_now` и `voltage_now` даны в микроамперах и микровольтах, их
# произведение приходится делить на 10^12, чтобы получить ватты.
_MICRO_SQUARED = 1_000_000_000_000.0

_PCI_VENDOR_NVIDIA = "0x10de"
_PCI_VENDOR_AMD = "0x1002"
_PCI_VENDOR_INTEL = "0x8086"
_VENDOR_NAMES = {
    _PCI_VENDOR_NVIDIA: "NVIDIA",
    _PCI_VENDOR_AMD: "AMD",
    _PCI_VENDOR_INTEL: "Intel",
}

# Типы корпусов по стандарту SMBIOS, соответствующие переносным устройствам.
_PORTABLE_CHASSIS_TYPES = frozenset({8, 9, 10, 11, 12, 14, 30, 31, 32})

_CARD_PATTERN = re.compile(r"^card\d+$")
_MODEL_NAME_PATTERN = re.compile(r"^model name\s*:\s*(.+)$", re.MULTILINE)


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except (OSError, ValueError):
        return None


def _read_int(path: str) -> int | None:
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# RAPL - реальная мощность пакета процессора
# --------------------------------------------------------------------------


@dataclass
class _EnergyCounter:
    name: str
    path: str
    wrap_at_uj: int
    previous_uj: int
    previous_at: float


class RaplReader:
    """Мощность процессора по приросту счётчика энергии RAPL.

    Счётчик монотонно растёт и переполняется, поэтому отрицательный прирост
    интерпретируется как один оборот через ``max_energy_range_uj``.
    """

    def __init__(self) -> None:
        self._counters: list[_EnergyCounter] = []
        self._permission_denied = False

    @property
    def available(self) -> bool:
        return bool(self._counters)

    @property
    def permission_denied(self) -> bool:
        return self._permission_denied

    def open(self) -> bool:
        if not IS_LINUX or not os.path.isdir(_POWERCAP_ROOT):
            return False

        now = time.monotonic()
        for domain in sorted(glob.glob(os.path.join(_POWERCAP_ROOT, "intel-rapl:*"))):
            # Вложенные домены (ядра, встроенная графика) входят в пакет и
            # привели бы к двойному учёту.
            if os.path.basename(domain).count(":") != 1:
                continue
            name = _read_text(os.path.join(domain, "name")) or ""
            if not name.startswith("package") and name != "psys":
                continue

            energy_path = os.path.join(domain, "energy_uj")
            try:
                with open(energy_path, encoding="utf-8") as handle:
                    energy = int(handle.read().strip())
            except PermissionError:
                self._permission_denied = True
                continue
            except (OSError, ValueError):
                continue

            wrap_at = _read_int(os.path.join(domain, "max_energy_range_uj")) or 0
            self._counters.append(_EnergyCounter(name, energy_path, wrap_at, energy, now))

        # Домен psys покрывает питание всей платформы и уже включает в себя
        # пакеты процессора, поэтому при его наличии остальные домены лишние.
        psys = [counter for counter in self._counters if counter.name == "psys"]
        if psys:
            self._counters = psys
        return bool(self._counters)

    @property
    def covers_whole_platform(self) -> bool:
        """Домен psys измеряет всю платформу, а не только процессор."""
        return any(counter.name == "psys" for counter in self._counters)

    def sample_watts(self) -> float | None:
        """Средняя мощность с момента предыдущего вызова."""
        if not self._counters:
            return None
        now = time.monotonic()
        total = 0.0
        measured = False
        for counter in self._counters:
            energy = _read_int(counter.path)
            if energy is None:
                continue
            elapsed = now - counter.previous_at
            delta = energy - counter.previous_uj
            if delta < 0 and counter.wrap_at_uj:
                delta += counter.wrap_at_uj
            counter.previous_uj = energy
            counter.previous_at = now
            if elapsed <= 0.0 or delta < 0:
                continue
            total += delta / _MICRO / elapsed
            measured = True
        return total if measured else None


# --------------------------------------------------------------------------
# Видеокарты через sysfs
# --------------------------------------------------------------------------


@dataclass
class LinuxGpu:
    """Видеоадаптер, найденный в sysfs, вместе с доступными датчиками."""

    name: str
    vendor_id: str
    power_average_path: str | None
    energy_path: str | None
    busy_path: str | None
    _previous_energy_uj: int | None = None
    _previous_at: float = 0.0

    @property
    def is_nvidia(self) -> bool:
        return self.vendor_id == _PCI_VENDOR_NVIDIA

    @property
    def has_power_sensor(self) -> bool:
        return self.power_average_path is not None or self.energy_path is not None

    def read_power_watts(self) -> float | None:
        if self.power_average_path is not None:
            microwatts = _read_int(self.power_average_path)
            if microwatts is not None and microwatts > 0:
                return microwatts / _MICRO
        if self.energy_path is None:
            return None

        energy = _read_int(self.energy_path)
        now = time.monotonic()
        if energy is None:
            return None
        previous, previous_at = self._previous_energy_uj, self._previous_at
        self._previous_energy_uj, self._previous_at = energy, now
        if previous is None or now <= previous_at or energy < previous:
            return None
        return (energy - previous) / _MICRO / (now - previous_at)

    def read_utilization(self) -> float | None:
        if self.busy_path is None:
            return None
        busy = _read_int(self.busy_path)
        if busy is None:
            return None
        return min(1.0, max(0.0, busy / 100.0))


def discover_gpus() -> tuple[LinuxGpu, ...]:
    if not IS_LINUX or not os.path.isdir(_DRM_ROOT):
        return ()

    pci_names = _lspci_names()
    gpus: list[LinuxGpu] = []
    for entry in sorted(os.listdir(_DRM_ROOT)):
        if not _CARD_PATTERN.match(entry):
            continue
        device_dir = os.path.join(_DRM_ROOT, entry, "device")
        vendor = (_read_text(os.path.join(device_dir, "vendor")) or "").lower()
        if vendor not in _VENDOR_NAMES:
            continue

        slot = os.path.basename(os.path.realpath(device_dir))
        name = pci_names.get(slot) or f"{_VENDOR_NAMES[vendor]} GPU"
        power_average_path, energy_path = _find_hwmon_power(device_dir)
        busy_path = os.path.join(device_dir, "gpu_busy_percent")
        gpus.append(
            LinuxGpu(
                name=name,
                vendor_id=vendor,
                power_average_path=power_average_path,
                energy_path=energy_path,
                busy_path=busy_path if os.path.exists(busy_path) else None,
            )
        )
    return tuple(gpus)


def _find_hwmon_power(device_dir: str) -> tuple[str | None, str | None]:
    hwmon_root = os.path.join(device_dir, "hwmon")
    if not os.path.isdir(hwmon_root):
        return None, None
    for hwmon in sorted(glob.glob(os.path.join(hwmon_root, "hwmon*"))):
        for filename in ("power1_average", "power1_input"):
            candidate = os.path.join(hwmon, filename)
            if os.path.exists(candidate):
                return candidate, None
        energy = os.path.join(hwmon, "energy1_input")
        if os.path.exists(energy):
            return None, energy
    return None, None


def _lspci_names() -> dict[str, str]:
    """Человекочитаемые имена видеокарт из lspci, если он установлен."""
    import shutil
    import subprocess

    executable = shutil.which("lspci")
    if executable is None:
        return {}
    try:
        output = subprocess.run(
            [executable, "-mm", "-D"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}

    names: dict[str, str] = {}
    for line in output.splitlines():
        fields = re.findall(r'"([^"]*)"|(\S+)', line)
        parts = [quoted or bare for quoted, bare in fields]
        if len(parts) < 4:
            continue
        slot, device_class, vendor, device = parts[0], parts[1], parts[2], parts[3]
        if "VGA" not in device_class and "3D" not in device_class and "Display" not in device_class:
            continue
        names[slot] = f"{vendor} {device}".strip()
    return names


# --------------------------------------------------------------------------
# Батарея и характеристики системы
# --------------------------------------------------------------------------


def read_battery_state() -> BatteryState | None:
    if not IS_LINUX or not os.path.isdir(_POWER_SUPPLY_ROOT):
        return None

    on_ac_power = _read_ac_online()
    for entry in sorted(os.listdir(_POWER_SUPPLY_ROOT)):
        supply_dir = os.path.join(_POWER_SUPPLY_ROOT, entry)
        if (_read_text(os.path.join(supply_dir, "type")) or "") != "Battery":
            continue

        status = (_read_text(os.path.join(supply_dir, "status")) or "").lower()
        discharging = status == "discharging"
        capacity = _read_int(os.path.join(supply_dir, "capacity"))

        watts: float | None = None
        microwatts = _read_int(os.path.join(supply_dir, "power_now"))
        if microwatts:
            watts = abs(microwatts) / _MICRO
        else:
            microamps = _read_int(os.path.join(supply_dir, "current_now"))
            microvolts = _read_int(os.path.join(supply_dir, "voltage_now"))
            if microamps and microvolts:
                watts = abs(microamps) * abs(microvolts) / _MICRO_SQUARED

        return BatteryState(
            present=True,
            on_ac_power=on_ac_power if on_ac_power is not None else not discharging,
            discharging=discharging,
            charge_percent=float(capacity) if capacity is not None else None,
            discharge_watts=watts if discharging else None,
        )

    return BatteryState(
        present=False,
        on_ac_power=True if on_ac_power is None else on_ac_power,
        discharging=False,
        charge_percent=None,
        discharge_watts=None,
    )


def _read_ac_online() -> bool | None:
    try:
        entries = sorted(os.listdir(_POWER_SUPPLY_ROOT))
    except OSError:
        return None
    for entry in entries:
        supply_dir = os.path.join(_POWER_SUPPLY_ROOT, entry)
        if (_read_text(os.path.join(supply_dir, "type")) or "") != "Mains":
            continue
        online = _read_int(os.path.join(supply_dir, "online"))
        if online is not None:
            return bool(online)
    return None


def read_cpu_name() -> str | None:
    if not IS_LINUX:
        return None
    content = _read_text(_CPUINFO_PATH)
    if content is None:
        return None
    match = _MODEL_NAME_PATTERN.search(content)
    return match.group(1).strip() if match else None


def is_portable_chassis() -> bool | None:
    chassis_type = _read_int(_CHASSIS_TYPE_PATH)
    if chassis_type is None:
        return None
    return chassis_type in _PORTABLE_CHASSIS_TYPES
