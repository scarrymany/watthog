"""Главное меню и редактор настроек."""

from __future__ import annotations

import re
from dataclasses import replace

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from watthog import APP_TAGLINE, AUTHOR_TELEGRAM, REPO_URL, __version__
from watthog import constants as const
from watthog.config import Settings, config_path, save_settings

_LOGO = (
    "██╗    ██╗ █████╗ ████████╗████████╗██╗  ██╗ ██████╗  ██████╗ ",
    "██║    ██║██╔══██╗╚══██╔══╝╚══██╔══╝██║  ██║██╔═══██╗██╔════╝ ",
    "██║ █╗ ██║███████║   ██║      ██║   ███████║██║   ██║██║  ███╗",
    "██║███╗██║██╔══██║   ██║      ██║   ██╔══██║██║   ██║██║   ██║",
    "╚███╔███╔╝██║  ██║   ██║      ██║   ██║  ██║╚██████╔╝╚██████╔╝",
    " ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ",
)
_LOGO_MIN_WIDTH = 66
_AUTO = "авто"
_AUTO_INPUT_VALUES = frozenset({"авто", "auto", "-", ""})
_AFFIRMATIVE_INPUT_VALUES = frozenset({"да", "yes", "y", "1", "true", "on"})
_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

MENU_RUN = "1"
MENU_RUN_CUSTOM = "2"
MENU_SETTINGS = "3"
MENU_HARDWARE = "4"
MENU_ABOUT = "5"
MENU_EXIT = "0"

_MENU_ITEMS = (
    (MENU_RUN, "Запустить замер", "тест длительностью {duration} с"),
    (MENU_RUN_CUSTOM, "Замер другой длительности", "указать время вручную"),
    (MENU_SETTINGS, "Настройки", "тариф, блок питания, калибровка"),
    (MENU_HARDWARE, "Железо и источники данных", "что найдено и что измеряется"),
    (MENU_ABOUT, "О программе", "как считается мощность"),
    (MENU_EXIT, "Выход", ""),
)


def banner(console: Console) -> RenderableType:
    """Заставка с логотипом, которая ужимается до строки на узком терминале."""
    if console.size.width >= _LOGO_MIN_WIDTH:
        logo: RenderableType = Text("\n".join(_LOGO), style="app.accent")
    else:
        logo = Text("⚡ WattHog", style="app.title")

    subtitle = Text.assemble(
        (APP_TAGLINE, "app.label"),
        ("   v", "app.muted"),
        (__version__, "app.muted"),
        ("   ·   ", "app.muted"),
        (AUTHOR_TELEGRAM, "app.accent"),
    )
    return Panel(
        Group(Align.center(logo), Text(""), Align.center(subtitle)),
        border_style="app.border",
        padding=(1, 2),
    )


def render_menu(console: Console, settings: Settings) -> str:
    """Показывает меню и возвращает выбранный пункт."""
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", width=3)
    table.add_column(justify="left")
    table.add_column(justify="left")

    for key, title, hint in _MENU_ITEMS:
        table.add_row(
            Text(f"[{key}]", style="app.accent"),
            Text(title, style="app.label"),
            Text(hint.format(duration=settings.duration_seconds), style="app.muted"),
        )

    console.print(Panel(table, title="[app.label]Меню", border_style="app.border", padding=(1, 2)))
    return Prompt.ask(
        "[app.accent]Выбор[/app.accent]",
        choices=[key for key, _, _ in _MENU_ITEMS],
        default=MENU_RUN,
        console=console,
        show_choices=False,
    )


def ask_duration(console: Console, current: int) -> int:
    raw = Prompt.ask(
        f"[app.accent]Длительность замера в секундах[/app.accent] "
        f"[app.muted]({const.MIN_DURATION_SECONDS}-{const.MAX_DURATION_SECONDS})[/app.muted]",
        default=str(current),
        console=console,
    )
    try:
        value = int(float(raw))
    except ValueError:
        console.print(Text("Не похоже на число, оставляю прежнее значение.", style="app.warn"))
        return current
    return max(const.MIN_DURATION_SECONDS, min(const.MAX_DURATION_SECONDS, value))


def about_panel() -> RenderableType:
    text = Text()
    text.append("Как WattHog считает мощность\n\n", style="app.label")
    text.append(
        "Программа берёт показания настоящих датчиков там, где они есть, и достраивает\n"
        "картину моделью там, где их нет.\n\n",
        style="app.muted",
    )
    for line in (
        "Видеокарты NVIDIA читаются через NVML - это реальная мощность платы.",
        "Видеокарты AMD и Intel в Linux читаются через hwmon, тоже реальные ватты.",
        "Процессор в Linux читается через RAPL, если есть доступ к счётчику энергии.",
        "На ноутбуке при работе от батареи измеряется потребление всей системы сразу.",
        "Остальное считается по загрузке, частоте и справочным пределам мощности.",
        "К сумме добавляются потери блока питания - их тоже оплачивает счётчик.",
    ):
        text.append("  • ", style="app.accent")
        text.append(f"{line}\n", style="app.muted")

    text.append("\nТочность\n", style="app.label")
    text.append(
        "  Чем больше настоящих датчиков, тем ближе цифра к показаниям розеточного\n"
        "  ваттметра. Полностью расчётный режим даёт порядок величины, а не точное\n"
        "  значение: подстройте пики процессора и видеокарты в настройках, если знаете\n"
        "  реальные цифры своей системы.\n",
        style="app.muted",
    )
    text.append("\n")
    text.append("Автор ", style="app.muted")
    text.append(AUTHOR_TELEGRAM, style="app.accent")
    text.append("   ·   ", style="app.muted")
    text.append(REPO_URL, style="app.muted")
    return Panel(text, title="[app.label]О программе", border_style="app.border", padding=(1, 2))


def edit_settings(console: Console, settings: Settings) -> Settings:
    """Интерактивный редактор настроек. Возвращает изменённые настройки."""
    while True:
        console.print(_settings_panel(settings))
        choice = Prompt.ask(
            "[app.accent]Что изменить[/app.accent]",
            choices=[str(index) for index in range(0, len(_SETTINGS_FIELDS) + 1)],
            default="0",
            console=console,
            show_choices=False,
        )
        if choice == "0":
            break

        field = _SETTINGS_FIELDS[int(choice) - 1]
        settings = _prompt_field(console, settings, field)

    normalized = settings.normalized()
    saved_to = save_settings(normalized)
    if saved_to is None:
        console.print(Text("Не удалось сохранить настройки на диск.", style="app.warn"))
    else:
        console.print(Text(f"Настройки сохранены: {saved_to}", style="app.ok"))
    return normalized


class _Field:
    """Описание одной редактируемой настройки."""

    def __init__(self, name: str, title: str, unit: str, kind: str, optional: bool = False) -> None:
        self.name = name
        self.title = title
        self.unit = unit
        self.kind = kind
        self.optional = optional

    def display(self, settings: Settings) -> str:
        value = getattr(settings, self.name)
        if value is None:
            return _AUTO
        if self.kind == "bool":
            return "да" if value else "нет"
        if self.kind == "int":
            return f"{int(value)} {self.unit}".strip()
        if self.kind == "percent":
            return f"{value * 100:.0f} {self.unit}".strip()
        if self.kind == "float":
            return f"{value:.2f} {self.unit}".strip()
        return f"{value}"


_SETTINGS_FIELDS = (
    _Field("duration_seconds", "Длительность замера", "с", "int"),
    _Field("sample_interval", "Интервал выборки", "с", "float"),
    _Field("tariff_per_kwh", "Тариф за кВт·ч", "", "float"),
    _Field("currency", "Валюта", "", "text"),
    _Field("psu_peak_efficiency", "Пиковый КПД блока питания", "%", "percent"),
    _Field("psu_rated_watts", "Номинал блока питания", "Вт", "int"),
    _Field("extra_devices_watts", "Периферия: монитор, колонки", "Вт", "float"),
    _Field("cpu_peak_watts", "Пик процессора", "Вт", "float", optional=True),
    _Field("gpu_peak_watts", "Пик видеокарты", "Вт", "float", optional=True),
    _Field("platform_watts", "Плата и обвязка", "Вт", "float", optional=True),
    _Field("save_reports", "Сохранять отчёты", "", "bool"),
)


def _settings_panel(settings: Settings) -> RenderableType:
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", width=4)
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="right")

    for index, field in enumerate(_SETTINGS_FIELDS, start=1):
        table.add_row(
            Text(f"[{index}]", style="app.accent"),
            Text(field.title, style="app.label"),
            Text(field.display(settings), style="app.value"),
        )
    table.add_row(Text("[0]", style="app.accent"), Text("Назад", style="app.label"), Text(""))

    hint = Text(f"Файл настроек: {config_path()}", style="app.hint")
    return Panel(
        Group(table, Text(""), hint),
        title="[app.label]Настройки",
        border_style="app.border",
        padding=(1, 2),
    )


def _prompt_field(console: Console, settings: Settings, field: _Field) -> Settings:
    suffix = f" [app.muted]({_AUTO} - определить автоматически)[/app.muted]" if field.optional else ""
    raw = Prompt.ask(
        f"[app.accent]{field.title}[/app.accent]{suffix}",
        default=field.display(settings),
        console=console,
    ).strip()

    if field.optional and raw.lower() in _AUTO_INPUT_VALUES:
        return replace(settings, **{field.name: None})

    try:
        value = _parse_value(raw, field)
    except ValueError:
        console.print(Text("Не удалось разобрать значение, настройка не изменена.", style="app.warn"))
        return settings
    return replace(settings, **{field.name: value}).normalized()


def _parse_value(raw: str, field: _Field) -> object:
    if field.kind == "bool":
        return raw.lower() in _AFFIRMATIVE_INPUT_VALUES
    if field.kind == "text":
        return raw

    # Пользователь легко повторит подсказанную единицу измерения ("650 Вт"),
    # поэтому из строки берётся первое число, а остальное отбрасывается.
    match = _NUMBER_PATTERN.search(raw.replace(",", "."))
    if match is None:
        raise ValueError(f"в строке {raw!r} нет числа")
    number = float(match.group())

    if field.kind == "int":
        return int(number)
    if field.kind == "percent":
        return number / 100.0 if number > 1.0 else number
    return number
