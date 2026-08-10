"""Константы модели энергопотребления и параметры измерения.

Числа собраны из независимых замеров энергопотребления железа (обзоры
TechPowerUp, AnandTech, Tom's Hardware) и вынесены в один модуль, чтобы
модель можно было калибровать, не трогая логику.
"""

SECONDS_PER_HOUR = 3600.0
WATTS_PER_KILOWATT = 1000.0
BYTES_PER_GIB = 1024 ** 3

# --- Параметры сессии измерения ---
DEFAULT_DURATION_SECONDS = 60
MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 12 * 3600
DEFAULT_SAMPLE_INTERVAL = 0.5
MIN_SAMPLE_INTERVAL = 0.2
MAX_SAMPLE_INTERVAL = 5.0

# --- Процессор ---
# P = idle + (peak - idle) * load^LOAD_EXP * (freq_ratio / REF_FREQ_RATIO)^FREQ_EXP
#
# Экспонента загрузки меньше единицы: первые нагруженные потоки стоят заметно
# дороже последних. На одном активном ядре процессор держит максимальный буст и
# высокое напряжение, а при полной загрузке частота и напряжение падают.
CPU_LOAD_EXPONENT = 0.55
CPU_FREQ_EXPONENT = 1.0
# Типичное отношение всеядерного буста к номинальной частоте. Приводит модель к
# тому, что при 100% загрузки множитель частоты равен единице и P = peak.
CPU_REFERENCE_FREQ_RATIO = 1.05
CPU_FREQ_RATIO_MIN = 0.25
CPU_FREQ_RATIO_MAX = 1.60
# КПД VRM материнской платы: пакет процессора питается через неё, и эти потери
# в его телеметрию не входят.
VRM_EFFICIENCY = 0.90

# --- Видеокарта ---
# Мощность GPU растёт почти линейно с загрузкой, лёгкая вогнутость - вклад
# памяти и обвязки, которые нагружаются раньше самих шейдерных блоков.
GPU_LOAD_EXPONENT = 0.90

# --- Оперативная память ---
RAM_WATTS_PER_GIB_DESKTOP = 0.22
RAM_WATTS_PER_GIB_LAPTOP = 0.09
RAM_LOAD_WATTS_PER_GIB_DESKTOP = 0.08
RAM_LOAD_WATTS_PER_GIB_LAPTOP = 0.03

# --- Накопители ---
DISK_IDLE_WATTS_DESKTOP = 1.0
DISK_IDLE_WATTS_LAPTOP = 0.6
DISK_ACTIVE_WATTS_DESKTOP = 5.0
DISK_ACTIVE_WATTS_LAPTOP = 2.5
# Поток, при котором накопитель считается загруженным на 100%.
DISK_SATURATION_BYTES_PER_SECOND = 500 * 1024 * 1024

# --- Платформа ---
# Десктоп: чипсет, вентиляторы, звук, сеть, USB, подсветка, простой VRM.
PLATFORM_WATTS_DESKTOP = 25.0
# Ноутбук: чипсет, вентилятор, Wi-Fi, встроенная матрица.
PLATFORM_WATTS_LAPTOP = 11.0
# Мини-ПК и неттоп: мобильная платформа без собственного экрана.
PLATFORM_WATTS_COMPACT = 8.0

# --- Преобразование питания ---
DEFAULT_PSU_PEAK_EFFICIENCY = 0.90
DEFAULT_PSU_RATED_WATTS = 650
MIN_PSU_RATED_WATTS = 100
MAX_PSU_RATED_WATTS = 2000
MIN_PSU_EFFICIENCY = 0.50
MAX_PSU_EFFICIENCY = 0.99
LAPTOP_ADAPTER_EFFICIENCY = 0.89
# КПД блока питания относительно пикового в зависимости от доли нагрузки от
# номинала. Форма кривой одинакова у всех сертификатов 80 PLUS, отличается
# только пиковое значение.
PSU_EFFICIENCY_CURVE = (
    (0.02, 0.62),
    (0.05, 0.76),
    (0.10, 0.86),
    (0.20, 0.96),
    (0.50, 1.00),
    (0.75, 0.99),
    (1.00, 0.96),
)

# --- Проекции ---
PROJECTION_HOURS = (1.0, 10.0, 12.0, 24.0, 168.0, 720.0)
HIGHLIGHTED_PROJECTION_HOURS = (10.0, 24.0)

# --- Оценка прожорливости ---
# Пороги в ваттах от розетки для словесной оценки уровня потребления. Цвет
# задан шестнадцатеричным кодом, потому что его понимают и rich, и tkinter.
CONSUMPTION_TIERS = (
    (60.0, "Экономный", "#43d675"),
    (150.0, "Умеренный", "#3fb6ff"),
    (300.0, "Заметный", "#ffd23f"),
    (500.0, "Прожорливый", "#ff9f40"),
    (float("inf"), "Ненасытный", "#ff4d4d"),
)

REPORT_FILENAME_FORMAT = "watthog-%Y%m%d-%H%M%S"
