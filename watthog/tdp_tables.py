"""Справочник энергопотребления процессоров и видеокарт.

Для процессоров хранится не паспортный TDP, а реальная мощность пакета: под
полной нагрузкой (``peak``) и в простое (``idle``). Паспортный TDP у AMD и
Intel считается по-разному и напрямую в модель не годится.

Если конкретная модель в таблице не нашлась, мощность оценивается по классу
процессора (разблокированный десктопный, мобильный H, мобильный U и так далее)
и числу ядер.
"""

from __future__ import annotations

import re
from enum import Enum

# (образец имени, пиковая мощность пакета, мощность в простое)
_CPU_TABLE: tuple[tuple[str, float, float], ...] = (
    # AMD Socket AM5
    ("ryzen 9 9950x3d", 200.0, 30.0),
    ("ryzen 9 9950x", 200.0, 30.0),
    ("ryzen 9 9900x3d", 180.0, 28.0),
    ("ryzen 9 9900x", 160.0, 28.0),
    ("ryzen 7 9800x3d", 140.0, 26.0),
    ("ryzen 7 9700x", 90.0, 24.0),
    ("ryzen 5 9600x", 88.0, 22.0),
    ("ryzen 9 7950x3d", 145.0, 30.0),
    ("ryzen 9 7950x", 200.0, 30.0),
    ("ryzen 9 7900x3d", 140.0, 28.0),
    ("ryzen 9 7900x", 175.0, 28.0),
    ("ryzen 9 7900", 88.0, 26.0),
    ("ryzen 7 7800x3d", 88.0, 24.0),
    ("ryzen 7 7700x", 140.0, 24.0),
    ("ryzen 7 7700", 88.0, 22.0),
    ("ryzen 5 7600x", 130.0, 22.0),
    ("ryzen 5 7600", 88.0, 20.0),
    ("ryzen 5 7500f", 88.0, 20.0),
    # AMD Socket AM4
    ("ryzen 9 5950x", 142.0, 24.0),
    ("ryzen 9 5900x", 142.0, 24.0),
    ("ryzen 7 5800x3d", 120.0, 22.0),
    ("ryzen 7 5800x", 142.0, 22.0),
    ("ryzen 7 5700x3d", 105.0, 20.0),
    ("ryzen 7 5700x", 88.0, 20.0),
    ("ryzen 5 5600x", 88.0, 18.0),
    ("ryzen 5 5600g", 88.0, 18.0),
    ("ryzen 5 5600", 88.0, 18.0),
    ("ryzen 5 5500", 88.0, 18.0),
    ("ryzen 9 3900x", 142.0, 22.0),
    ("ryzen 7 3800x", 105.0, 20.0),
    ("ryzen 7 3700x", 88.0, 20.0),
    ("ryzen 5 3600x", 95.0, 18.0),
    ("ryzen 5 3600", 88.0, 18.0),
    ("ryzen 7 2700x", 105.0, 20.0),
    ("ryzen 5 2600", 88.0, 18.0),
    ("ryzen 5 1600", 88.0, 18.0),
    # Intel Core Ultra
    ("core ultra 9 285k", 250.0, 20.0),
    ("core ultra 7 265k", 250.0, 18.0),
    ("core ultra 5 245k", 159.0, 16.0),
    # Intel LGA1700
    ("i9-14900ks", 253.0, 24.0),
    ("i9-14900k", 253.0, 22.0),
    ("i9-14900", 219.0, 20.0),
    ("i7-14700k", 253.0, 20.0),
    ("i7-14700", 219.0, 18.0),
    ("i5-14600k", 181.0, 16.0),
    ("i5-14500", 154.0, 14.0),
    ("i5-14400", 148.0, 14.0),
    ("i9-13900ks", 253.0, 24.0),
    ("i9-13900k", 253.0, 22.0),
    ("i9-13900", 219.0, 20.0),
    ("i7-13700k", 253.0, 20.0),
    ("i7-13700", 219.0, 18.0),
    ("i5-13600k", 181.0, 16.0),
    ("i5-13500", 154.0, 14.0),
    ("i5-13400", 148.0, 14.0),
    ("i9-12900k", 241.0, 20.0),
    ("i9-12900", 202.0, 18.0),
    ("i7-12700k", 190.0, 18.0),
    ("i7-12700", 180.0, 16.0),
    ("i5-12600k", 150.0, 16.0),
    ("i5-12500", 117.0, 12.0),
    ("i5-12400", 117.0, 12.0),
    ("i3-12100", 89.0, 10.0),
    # Intel LGA1200 и старше
    ("i9-11900k", 250.0, 20.0),
    ("i7-11700k", 225.0, 18.0),
    ("i5-11600k", 180.0, 16.0),
    ("i5-11400", 125.0, 12.0),
    ("i9-10900k", 250.0, 18.0),
    ("i7-10700k", 200.0, 16.0),
    ("i5-10600k", 160.0, 14.0),
    ("i5-10400", 100.0, 12.0),
    ("i9-9900k", 190.0, 16.0),
    ("i7-9700k", 150.0, 14.0),
    ("i5-9600k", 125.0, 12.0),
    ("i5-9400", 90.0, 12.0),
    ("i7-8700k", 130.0, 12.0),
    ("i5-8400", 80.0, 10.0),
    ("i7-7700k", 95.0, 10.0),
    ("i5-7500", 65.0, 9.0),
    ("i7-6700k", 91.0, 10.0),
    ("i5-6500", 65.0, 9.0),
    ("i7-4790k", 88.0, 12.0),
    ("i5-4590", 84.0, 11.0),
    # Мобильные, самые массовые модели
    ("i9-13980hx", 157.0, 6.0),
    ("i9-14900hx", 157.0, 6.0),
    ("i7-13700hx", 157.0, 6.0),
    ("i7-12700h", 115.0, 5.0),
    ("i7-13620h", 115.0, 5.0),
    ("i5-12450h", 95.0, 4.5),
    ("i7-1165g7", 28.0, 3.0),
    ("i5-1135g7", 28.0, 3.0),
    ("ryzen 9 7945hx", 120.0, 6.0),
    ("ryzen 9 7940hs", 65.0, 4.5),
    ("ryzen 7 7840hs", 65.0, 4.5),
    ("ryzen 7 6800h", 65.0, 4.5),
    ("ryzen 7 5800h", 65.0, 4.5),
    ("ryzen 5 5600h", 60.0, 4.0),
    ("ryzen 7 5700u", 25.0, 3.0),
    ("ryzen 5 5500u", 25.0, 3.0),
)

# (образец имени, мощность платы под нагрузкой, мощность в простое)
_GPU_TABLE: tuple[tuple[str, float, float], ...] = (
    # NVIDIA GeForce RTX 50
    ("rtx 5090", 575.0, 30.0),
    ("rtx 5080", 360.0, 22.0),
    ("rtx 5070 ti", 300.0, 18.0),
    ("rtx 5070", 250.0, 16.0),
    ("rtx 5060 ti", 180.0, 14.0),
    ("rtx 5060", 145.0, 12.0),
    # NVIDIA GeForce RTX 40
    ("rtx 4090", 450.0, 25.0),
    ("rtx 4080 super", 320.0, 20.0),
    ("rtx 4080", 320.0, 20.0),
    ("rtx 4070 ti super", 285.0, 17.0),
    ("rtx 4070 ti", 285.0, 17.0),
    ("rtx 4070 super", 220.0, 15.0),
    ("rtx 4070", 200.0, 14.0),
    ("rtx 4060 ti", 160.0, 12.0),
    ("rtx 4060", 115.0, 10.0),
    # NVIDIA GeForce RTX 30
    ("rtx 3090 ti", 450.0, 26.0),
    ("rtx 3090", 350.0, 25.0),
    ("rtx 3080 ti", 350.0, 22.0),
    ("rtx 3080", 320.0, 22.0),
    ("rtx 3070 ti", 290.0, 18.0),
    ("rtx 3070", 220.0, 16.0),
    ("rtx 3060 ti", 200.0, 15.0),
    ("rtx 3060", 170.0, 13.0),
    ("rtx 3050", 130.0, 10.0),
    # NVIDIA GeForce RTX 20 и GTX
    ("rtx 2080 ti", 250.0, 18.0),
    ("rtx 2080", 215.0, 16.0),
    ("rtx 2070", 175.0, 14.0),
    ("rtx 2060", 160.0, 12.0),
    ("gtx 1660", 120.0, 9.0),
    ("gtx 1650", 75.0, 7.0),
    ("gtx 1080 ti", 250.0, 15.0),
    ("gtx 1080", 180.0, 12.0),
    ("gtx 1070", 150.0, 10.0),
    ("gtx 1060", 120.0, 8.0),
    ("gtx 1050", 75.0, 6.0),
    ("gtx 970", 145.0, 12.0),
    ("gtx 960", 120.0, 10.0),
    # AMD Radeon
    ("rx 9070 xt", 304.0, 18.0),
    ("rx 9070", 220.0, 16.0),
    ("rx 7900 xtx", 355.0, 22.0),
    ("rx 7900 xt", 315.0, 20.0),
    ("rx 7800 xt", 263.0, 18.0),
    ("rx 7700 xt", 245.0, 16.0),
    ("rx 7600", 165.0, 12.0),
    ("rx 6950 xt", 335.0, 20.0),
    ("rx 6900 xt", 300.0, 18.0),
    ("rx 6800 xt", 300.0, 18.0),
    ("rx 6800", 250.0, 16.0),
    ("rx 6700 xt", 230.0, 14.0),
    ("rx 6650 xt", 180.0, 12.0),
    ("rx 6600 xt", 160.0, 11.0),
    ("rx 6600", 132.0, 10.0),
    ("rx 6500 xt", 107.0, 8.0),
    ("rx 5700 xt", 225.0, 14.0),
    ("rx 5600 xt", 150.0, 11.0),
    ("rx 590", 225.0, 14.0),
    ("rx 580", 185.0, 12.0),
    ("rx 570", 150.0, 11.0),
    ("rx 560", 80.0, 8.0),
    # Intel Arc
    ("arc b580", 190.0, 12.0),
    ("arc b570", 150.0, 10.0),
    ("arc a770", 225.0, 15.0),
    ("arc a750", 225.0, 15.0),
    ("arc a580", 185.0, 13.0),
    ("arc a380", 75.0, 8.0),
)

# Встроенная графика питается от того же пакета, что и процессор, поэтому её
# мощность нельзя считать отдельно - это было бы двойным учётом. Образцы
# сравниваются уже с нормализованным именем, где убраны "(R)" и "(TM)".
_INTEGRATED_GPU_PATTERNS: tuple[str, ...] = (
    "radeon graphics",
    "radeon vega",
    "vega graphics",
    "uhd graphics",
    "hd graphics",
    "iris xe",
    "iris plus",
    "iris graphics",
    "arc graphics",
)

_INTEGRATED_GPU_REGEXES: tuple[re.Pattern[str], ...] = (
    # Мобильные встроенные Radeon: 610M, 660M, 680M, 760M, 780M, 890M и далее.
    re.compile(r"\bradeon \d{3}m\b"),
    # Встроенные Radeon старых APU: R2 - R7 Graphics.
    re.compile(r"\bradeon r\d\b"),
)

# Виртуальные и служебные адаптеры без собственного питания.
_VIRTUAL_GPU_PATTERNS: tuple[str, ...] = (
    "microsoft basic display",
    "microsoft remote display",
    "microsoft hyper-v video",
    "citrix indirect display",
    "parsec virtual display",
    "virtual display",
    "idd hdr",
    "vmware svga",
    "virtualbox graphics",
    "meta virtual monitor",
    "oray idd",
    "usb display",
    "displaylink",
)

_MOBILE_GPU_MARKERS: tuple[str, ...] = ("laptop gpu", "max-q", " mobile")
# Мобильные версии видеокарт носят то же имя, но живут в куда более жёстком
# лимите мощности, чем десктопные.
MOBILE_GPU_POWER_FACTOR = 0.6


class CpuClass(Enum):
    """Класс процессора, определяющий порядок его энергопотребления."""

    DESKTOP_UNLOCKED = "десктопный разблокированный"
    DESKTOP_STANDARD = "десктопный"
    DESKTOP_LOW_POWER = "десктопный энергоэффективный"
    MOBILE_HX = "мобильный HX"
    MOBILE_H = "мобильный H"
    MOBILE_U = "мобильный U"


# Класс -> (ватт на ядро, базовые ватты, ватт простоя на ядро, базовый простой,
#           минимум пика, максимум пика)
_CLASS_PROFILES: dict[CpuClass, tuple[float, float, float, float, float, float]] = {
    CpuClass.DESKTOP_UNLOCKED: (15.0, 40.0, 1.6, 10.0, 65.0, 260.0),
    CpuClass.DESKTOP_STANDARD: (9.0, 28.0, 1.2, 8.0, 45.0, 200.0),
    CpuClass.DESKTOP_LOW_POWER: (5.0, 18.0, 0.8, 6.0, 30.0, 110.0),
    CpuClass.MOBILE_HX: (7.0, 25.0, 0.4, 3.0, 45.0, 160.0),
    CpuClass.MOBILE_H: (4.5, 16.0, 0.3, 2.5, 25.0, 120.0),
    CpuClass.MOBILE_U: (2.2, 9.0, 0.2, 1.5, 12.0, 45.0),
}

_CLASS_PATTERNS: tuple[tuple[re.Pattern[str], CpuClass], ...] = (
    (re.compile(r"\d{3,5}hx\b"), CpuClass.MOBILE_HX),
    (re.compile(r"\d{3,5}h[sk]?\b"), CpuClass.MOBILE_H),
    (re.compile(r"\d{3,5}g\d\b"), CpuClass.MOBILE_U),
    (re.compile(r"\d{3,5}[up]\b"), CpuClass.MOBILE_U),
    (re.compile(r"\d{3,5}(?:x3d|xt|x|ks|kf|k)\b"), CpuClass.DESKTOP_UNLOCKED),
    (re.compile(r"\d{3,5}(?:ge|te|t|e)\b"), CpuClass.DESKTOP_LOW_POWER),
)

_NOISE_PATTERN = re.compile(r"\(r\)|\(tm\)|\btm\b|\bcpu\b|\bprocessor\b|@.*$|\d+-core", re.IGNORECASE)
_WHITESPACE_PATTERN = re.compile(r"\s+")

_CPU_LOOKUP = tuple(sorted(_CPU_TABLE, key=lambda row: len(row[0]), reverse=True))
_GPU_LOOKUP = tuple(sorted(_GPU_TABLE, key=lambda row: len(row[0]), reverse=True))

MATCH_SOURCE_TABLE = "справочник"
MATCH_SOURCE_ESTIMATE = "оценка по классу"
MATCH_SOURCE_TELEMETRY = "телеметрия"
MATCH_SOURCE_SETTINGS = "настройки"


def normalize_name(name: str) -> str:
    """Приводит имя железа к виду, пригодному для поиска по образцам."""
    cleaned = _NOISE_PATTERN.sub(" ", name.lower())
    return _WHITESPACE_PATTERN.sub(" ", cleaned).strip()


def classify_cpu(name: str) -> CpuClass:
    normalized = normalize_name(name)
    for pattern, cpu_class in _CLASS_PATTERNS:
        if pattern.search(normalized):
            return cpu_class
    return CpuClass.DESKTOP_STANDARD


def is_mobile_cpu(cpu_class: CpuClass) -> bool:
    return cpu_class in (CpuClass.MOBILE_HX, CpuClass.MOBILE_H, CpuClass.MOBILE_U)


def lookup_cpu_power(name: str, physical_cores: int) -> tuple[float, float, str]:
    """Возвращает (пиковые ватты, ватты простоя, источник значения)."""
    normalized = normalize_name(name)
    for pattern, peak, idle in _CPU_LOOKUP:
        if pattern in normalized:
            return peak, idle, MATCH_SOURCE_TABLE

    cpu_class = classify_cpu(name)
    per_core, base, idle_per_core, idle_base, floor, ceiling = _CLASS_PROFILES[cpu_class]
    cores = max(1, physical_cores)
    peak = min(ceiling, max(floor, per_core * cores + base))
    idle = idle_per_core * cores + idle_base
    return peak, idle, MATCH_SOURCE_ESTIMATE


def is_integrated_gpu(name: str) -> bool:
    normalized = normalize_name(name)
    if any(pattern in normalized for pattern in _INTEGRATED_GPU_PATTERNS):
        return True
    return any(pattern.search(normalized) for pattern in _INTEGRATED_GPU_REGEXES)


def is_virtual_gpu(name: str) -> bool:
    normalized = normalize_name(name)
    return any(pattern in normalized for pattern in _VIRTUAL_GPU_PATTERNS)


def is_mobile_gpu(name: str) -> bool:
    normalized = normalize_name(name)
    return any(marker in normalized for marker in _MOBILE_GPU_MARKERS)


def lookup_gpu_power(name: str) -> tuple[float, float, str]:
    """Возвращает (пиковые ватты платы, ватты простоя, источник значения)."""
    normalized = normalize_name(name)
    factor = MOBILE_GPU_POWER_FACTOR if is_mobile_gpu(name) else 1.0
    for pattern, peak, idle in _GPU_LOOKUP:
        if pattern in normalized:
            return peak * factor, idle * factor, MATCH_SOURCE_TABLE

    # Неизвестная дискретная карта: берём средний по рынку уровень, чтобы
    # оценка не уходила ни в ноль, ни в заведомо завышенные сотни ватт.
    return 180.0 * factor, 14.0 * factor, MATCH_SOURCE_ESTIMATE
