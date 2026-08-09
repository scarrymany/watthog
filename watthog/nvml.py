"""Чтение мощности видеокарт NVIDIA через NVML.

NVML поставляется вместе с драйвером и одинаково работает в Windows и Linux,
поэтому модуль общий для обеих платформ. Библиотека отдаёт настоящую мощность
платы в ваттах, а не оценку по загрузке.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
from dataclasses import dataclass

_NVML_SUCCESS = 0
_NVML_NAME_BUFFER_SIZE = 96
_NVML_TEMPERATURE_GPU = 0
_MILLIWATTS_PER_WATT = 1000.0

_WINDOWS_LIBRARIES = (
    "nvml.dll",
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvml.dll",
)
_LINUX_LIBRARIES = (
    "libnvidia-ml.so.1",
    "libnvidia-ml.so",
)


class _Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


@dataclass(frozen=True)
class NvidiaDevice:
    index: int
    name: str
    power_limit_watts: float | None


@dataclass(frozen=True)
class NvidiaSample:
    index: int
    power_watts: float
    utilization: float
    temperature_c: float | None


class NvidiaTelemetry:
    """Пул открытых устройств NVML. Открывается один раз на всю сессию."""

    def __init__(self) -> None:
        self._nvml: ctypes.CDLL | None = None
        self._handles: list[ctypes.c_void_p] = []
        self._devices: tuple[NvidiaDevice, ...] = ()

    @property
    def devices(self) -> tuple[NvidiaDevice, ...]:
        return self._devices

    @property
    def available(self) -> bool:
        return bool(self._handles)

    def open(self) -> bool:
        nvml = _load_library()
        if nvml is None:
            return False
        try:
            if nvml.nvmlInit_v2() != _NVML_SUCCESS:
                return False
        except (AttributeError, OSError):
            return False

        self._nvml = nvml
        count = ctypes.c_uint()
        if nvml.nvmlDeviceGetCount_v2(ctypes.byref(count)) != _NVML_SUCCESS:
            self.close()
            return False

        devices: list[NvidiaDevice] = []
        for index in range(count.value):
            handle = ctypes.c_void_p()
            if nvml.nvmlDeviceGetHandleByIndex_v2(index, ctypes.byref(handle)) != _NVML_SUCCESS:
                continue
            self._handles.append(handle)
            devices.append(NvidiaDevice(index, self._read_name(handle), self._read_power_limit(handle)))

        self._devices = tuple(devices)
        if not self._handles:
            self.close()
            return False
        return True

    def _read_name(self, handle: ctypes.c_void_p) -> str:
        buffer = ctypes.create_string_buffer(_NVML_NAME_BUFFER_SIZE)
        if self._nvml.nvmlDeviceGetName(handle, buffer, _NVML_NAME_BUFFER_SIZE) != _NVML_SUCCESS:
            return "NVIDIA GPU"
        return buffer.value.decode("utf-8", errors="replace")

    def _read_power_limit(self, handle: ctypes.c_void_p) -> float | None:
        milliwatts = ctypes.c_uint()
        if self._nvml.nvmlDeviceGetEnforcedPowerLimit(handle, ctypes.byref(milliwatts)) != _NVML_SUCCESS:
            return None
        return milliwatts.value / _MILLIWATTS_PER_WATT

    def sample(self) -> tuple[NvidiaSample, ...]:
        if self._nvml is None:
            return ()
        samples: list[NvidiaSample] = []
        for index, handle in enumerate(self._handles):
            milliwatts = ctypes.c_uint()
            if self._nvml.nvmlDeviceGetPowerUsage(handle, ctypes.byref(milliwatts)) != _NVML_SUCCESS:
                continue

            utilization = _Utilization()
            busy = 0.0
            if self._nvml.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(utilization)) == _NVML_SUCCESS:
                busy = utilization.gpu / 100.0

            temperature = ctypes.c_uint()
            temperature_c: float | None = None
            if (
                self._nvml.nvmlDeviceGetTemperature(handle, _NVML_TEMPERATURE_GPU, ctypes.byref(temperature))
                == _NVML_SUCCESS
            ):
                temperature_c = float(temperature.value)

            samples.append(
                NvidiaSample(
                    index=index,
                    power_watts=milliwatts.value / _MILLIWATTS_PER_WATT,
                    utilization=busy,
                    temperature_c=temperature_c,
                )
            )
        return tuple(samples)

    def close(self) -> None:
        if self._nvml is not None:
            with contextlib.suppress(OSError):
                self._nvml.nvmlShutdown()
        self._nvml = None
        self._handles.clear()
        self._devices = ()


def _load_library() -> ctypes.CDLL | None:
    candidates = _WINDOWS_LIBRARIES if sys.platform == "win32" else _LINUX_LIBRARIES
    for candidate in candidates:
        try:
            return ctypes.CDLL(candidate)
        except OSError:
            continue
    return None
