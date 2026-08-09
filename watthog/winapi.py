"""Источники телеметрии Windows.

* PDH (`pdh.dll`) - счётчики производительности: реальный множитель частоты
  процессора и загрузка движков видеокарт любого вендора.
* Power management (`powrprof.dll`) - состояние батареи вместе с мгновенной
  скоростью разряда. Для ноутбука это прямое измерение потребления всей
  системы, а не оценка.

Ни одна функция модуля не выбрасывает исключений наружу: недоступный источник
возвращает ``None`` или пустой результат, чтобы вызывающий код мог мягко
деградировать до расчётной модели.
"""

from __future__ import annotations

import contextlib
import ctypes
import sys
from ctypes import wintypes

from watthog.hwtypes import BatteryState

IS_WINDOWS = sys.platform == "win32"

_ERROR_SUCCESS = 0
_PDH_MORE_DATA = 0x800007D2
_PDH_FMT_DOUBLE = 0x00000200
_PDH_FMT_NOCAP100 = 0x00008000

_MILLIWATTS_PER_WATT = 1000.0
_SYSTEM_BATTERY_STATE_LEVEL = 5
_BATTERY_RATE_UNKNOWN = 0x80000000
_UTF8_CODE_PAGE = 65001

COUNTER_CPU_PERFORMANCE = r"\Processor Information(_Total)\% Processor Performance"
COUNTER_GPU_ENGINE = r"\GPU Engine(*)\Utilization Percentage"

# Имя экземпляра счётчика GPU: pid_<pid>_luid_<hi>_<lo>_phys_<n>_eng_<n>_engtype_<type>
_GPU_INSTANCE_LUID_MARKER = "_luid_"
_GPU_INSTANCE_ENGTYPE_MARKER = "_engtype_"


def enable_utf8_console() -> None:
    """Переключает консоль Windows в UTF-8, иначе рамки и кириллица ломаются."""
    if not IS_WINDOWS:
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetConsoleOutputCP(_UTF8_CODE_PAGE)
        kernel32.SetConsoleCP(_UTF8_CODE_PAGE)
    except OSError:
        pass
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# PDH - счётчики производительности Windows
# --------------------------------------------------------------------------


class _PdhCounterValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _PdhCounterItemW(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _PdhCounterValue)]


class PerformanceCounters:
    """Один PDH-запрос на всё приложение.

    Счётчики делятся на скалярные (одно значение) и групповые (шаблон с ``*``,
    отдельное значение на каждый экземпляр). Данные появляются только со
    второго вызова :meth:`collect`: PDH считает их как дельту между сборами.
    """

    def __init__(self) -> None:
        self._pdh: ctypes.WinDLL | None = None
        self._query = wintypes.HANDLE()
        self._scalars: dict[str, wintypes.HANDLE] = {}
        self._groups: dict[str, wintypes.HANDLE] = {}
        self._collected = 0

    @property
    def available(self) -> bool:
        return self._pdh is not None

    @property
    def ready(self) -> bool:
        return self._collected >= 2

    def open(self) -> bool:
        if not IS_WINDOWS:
            return False
        try:
            pdh = ctypes.WinDLL("pdh.dll")
        except OSError:
            return False

        pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
        pdh.PdhOpenQueryW.restype = wintypes.DWORD
        pdh.PdhAddEnglishCounterW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        pdh.PdhAddEnglishCounterW.restype = wintypes.DWORD
        pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
        pdh.PdhCollectQueryData.restype = wintypes.DWORD
        pdh.PdhGetFormattedCounterValue.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(_PdhCounterValue),
        ]
        pdh.PdhGetFormattedCounterValue.restype = wintypes.DWORD
        pdh.PdhGetFormattedCounterArrayW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        pdh.PdhGetFormattedCounterArrayW.restype = wintypes.DWORD
        pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]
        pdh.PdhCloseQuery.restype = wintypes.DWORD

        if pdh.PdhOpenQueryW(None, None, ctypes.byref(self._query)) != _ERROR_SUCCESS:
            return False
        self._pdh = pdh
        return True

    def add_scalar(self, name: str, path: str) -> bool:
        return self._add(self._scalars, name, path)

    def add_group(self, name: str, path: str) -> bool:
        return self._add(self._groups, name, path)

    def _add(self, target: dict[str, wintypes.HANDLE], name: str, path: str) -> bool:
        if self._pdh is None:
            return False
        handle = wintypes.HANDLE()
        if self._pdh.PdhAddEnglishCounterW(self._query, path, None, ctypes.byref(handle)) != _ERROR_SUCCESS:
            return False
        target[name] = handle
        return True

    def collect(self) -> None:
        if self._pdh is None:
            return
        if self._pdh.PdhCollectQueryData(self._query) == _ERROR_SUCCESS:
            self._collected += 1

    def scalar(self, name: str) -> float | None:
        if self._pdh is None or not self.ready:
            return None
        handle = self._scalars.get(name)
        if handle is None:
            return None
        value = _PdhCounterValue()
        rc = self._pdh.PdhGetFormattedCounterValue(
            handle, _PDH_FMT_DOUBLE | _PDH_FMT_NOCAP100, None, ctypes.byref(value)
        )
        if rc != _ERROR_SUCCESS or value.CStatus != _ERROR_SUCCESS:
            return None
        return float(value.doubleValue)

    def group(self, name: str) -> dict[str, float]:
        if self._pdh is None or not self.ready:
            return {}
        handle = self._groups.get(name)
        if handle is None:
            return {}

        size = wintypes.DWORD(0)
        count = wintypes.DWORD(0)
        rc = self._pdh.PdhGetFormattedCounterArrayW(
            handle, _PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None
        )
        if rc != _PDH_MORE_DATA or size.value == 0:
            return {}

        buffer = ctypes.create_string_buffer(size.value)
        rc = self._pdh.PdhGetFormattedCounterArrayW(
            handle, _PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buffer
        )
        if rc != _ERROR_SUCCESS:
            return {}

        items = ctypes.cast(buffer, ctypes.POINTER(_PdhCounterItemW))
        values: dict[str, float] = {}
        for index in range(count.value):
            item = items[index]
            if item.FmtValue.CStatus != _ERROR_SUCCESS or not item.szName:
                continue
            values[item.szName] = float(item.FmtValue.doubleValue)
        return values

    def close(self) -> None:
        if self._pdh is None:
            return
        self._pdh.PdhCloseQuery(self._query)
        self._pdh = None
        self._scalars.clear()
        self._groups.clear()


def peak_gpu_utilization(engine_counters: dict[str, float]) -> float:
    """Загрузка самого нагруженного графического адаптера, доля от единицы.

    Счётчик даёт одно значение на каждую пару "процесс + движок", поэтому
    значения сначала складываются по всем процессам внутри пары "адаптер +
    тип движка", а затем берётся максимум. Складывать разные типы движков
    нельзя: 3D, копирование и видеодекодер работают параллельно, и их сумма
    легко превышает сто процентов при неполной загрузке чипа.
    """
    if not engine_counters:
        return 0.0

    grouped: dict[tuple[str, str], float] = {}
    for instance, value in engine_counters.items():
        if value <= 0.0:
            continue
        adapter, engine_type = _parse_gpu_instance(instance)
        key = (adapter, engine_type)
        grouped[key] = grouped.get(key, 0.0) + value

    if not grouped:
        return 0.0
    return min(1.0, max(grouped.values()) / 100.0)


def _parse_gpu_instance(instance: str) -> tuple[str, str]:
    adapter = ""
    engine_type = ""
    luid_at = instance.find(_GPU_INSTANCE_LUID_MARKER)
    if luid_at >= 0:
        adapter = instance[luid_at + len(_GPU_INSTANCE_LUID_MARKER) :]
        phys_at = adapter.find("_phys_")
        if phys_at >= 0:
            adapter = adapter[:phys_at]
    engtype_at = instance.find(_GPU_INSTANCE_ENGTYPE_MARKER)
    if engtype_at >= 0:
        engine_type = instance[engtype_at + len(_GPU_INSTANCE_ENGTYPE_MARKER) :]
    return adapter, engine_type


# --------------------------------------------------------------------------
# Батарея - прямое измерение потребления системы на ноутбуке
# --------------------------------------------------------------------------


class _SystemBatteryState(ctypes.Structure):
    _fields_ = [
        ("AcOnLine", ctypes.c_ubyte),
        ("BatteryPresent", ctypes.c_ubyte),
        ("Charging", ctypes.c_ubyte),
        ("Discharging", ctypes.c_ubyte),
        ("Spare1", ctypes.c_ubyte * 3),
        ("Tag", ctypes.c_ubyte),
        ("MaxCapacity", wintypes.DWORD),
        ("RemainingCapacity", wintypes.DWORD),
        ("Rate", wintypes.DWORD),
        ("EstimatedTime", wintypes.DWORD),
        ("DefaultAlert1", wintypes.DWORD),
        ("DefaultAlert2", wintypes.DWORD),
    ]


def read_battery_state() -> BatteryState | None:
    """Состояние батареи вместе с мгновенной скоростью разряда.

    Поле ``Rate`` объявлено как ULONG, но фактически знаковое и измеряется в
    милливаттах: отрицательное при разряде, положительное при заряде. Значение
    ``0x80000000`` означает, что контроллер батареи скорость не сообщает.
    """
    if not IS_WINDOWS:
        return None
    try:
        powrprof = ctypes.WinDLL("powrprof.dll")
    except OSError:
        return None

    powrprof.CallNtPowerInformation.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
    ]
    powrprof.CallNtPowerInformation.restype = ctypes.c_long

    state = _SystemBatteryState()
    status = powrprof.CallNtPowerInformation(
        _SYSTEM_BATTERY_STATE_LEVEL, None, 0, ctypes.byref(state), ctypes.sizeof(state)
    )
    if status != 0:
        return None

    if not state.BatteryPresent:
        return BatteryState(
            present=False,
            on_ac_power=bool(state.AcOnLine),
            discharging=False,
            charge_percent=None,
            discharge_watts=None,
        )

    charge_percent: float | None = None
    if state.MaxCapacity:
        charge_percent = min(100.0, state.RemainingCapacity * 100.0 / state.MaxCapacity)

    discharge_watts: float | None = None
    raw_rate = state.Rate
    if raw_rate != _BATTERY_RATE_UNKNOWN:
        signed_rate = raw_rate - (1 << 32) if raw_rate >= (1 << 31) else raw_rate
        if state.Discharging and signed_rate != 0:
            discharge_watts = abs(signed_rate) / _MILLIWATTS_PER_WATT

    return BatteryState(
        present=True,
        on_ac_power=bool(state.AcOnLine),
        discharging=bool(state.Discharging),
        charge_percent=charge_percent,
        discharge_watts=discharge_watts,
    )


# --------------------------------------------------------------------------
# Реестр - названия железа без обращения к WMI
# --------------------------------------------------------------------------

_CPU_REGISTRY_PATH = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
_DISPLAY_CLASS_PATH = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


def read_cpu_name() -> str | None:
    if not IS_WINDOWS:
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CPU_REGISTRY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
    except OSError:
        return None
    return str(value).strip() or None


def read_gpu_names() -> tuple[str, ...]:
    """Названия видеоадаптеров из ветки класса дисплеев в реестре."""
    if not IS_WINDOWS:
        return ()
    import winreg

    names: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS_PATH) as class_key:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(class_key, index)
                except OSError:
                    break
                index += 1
                if not subkey_name.isdigit():
                    continue
                try:
                    with winreg.OpenKey(class_key, subkey_name) as device_key:
                        description, _ = winreg.QueryValueEx(device_key, "DriverDesc")
                except OSError:
                    continue
                description = str(description).strip()
                if description and description not in names:
                    names.append(description)
    except OSError:
        return ()
    return tuple(names)
