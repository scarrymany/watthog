"""Главное меню и редактор настроек."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from watthog import APP_TAGLINE, AUTHOR_TELEGRAM, REPO_URL, __version__
from watthog import constants as const
from watthog.config import Settings, config_path, save_settings
from watthog.donate import DONATION_ADDRESSES, DONATION_NOTE
from watthog.formatting import format_price, parse_number
from watthog.tariffs import TARIFF_PRESETS, match_preset

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

MENU_RUN = "1"
MENU_RUN_CUSTOM = "2"
MENU_GUI = "3"
MENU_SETTINGS = "4"
MENU_TARIFFS = "5"
MENU_HARDWARE = "6"
MENU_ABOUT = "7"
MENU_DONATE = "8"
MENU_EXIT = "0"

_MENU_ITEMS = (
    (MENU_RUN, "Запустить замер", "тест длительностью {duration} с"),
    (MENU_RUN_CUSTOM, "Замер другой длительности", "указать время вручную"),
    (MENU_GUI, "Оконный интерфейс", "то же самое, но в окне"),
    (MENU_SETTINGS, "Настройки", "блок питания, калибровка, отчёты"),
    (MENU_TARIFFS, "Тариф на электроэнергию", "справочник цен и валюта"),
    (MENU_HARDWARE, "Железо и источники данных", "что найдено и что измеряется"),
    (MENU_ABOUT, "О программе", "как считается мощность"),
    (MENU_DONATE, "Поддержать проект", "реквизиты в криптовалюте"),
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


def tariffs_panel(settings: Settings | None = None) -> RenderableType:
    """Справочник тарифов с отметкой того, что выбран сейчас."""
    today = date.today()
    current = None
    if settings is not None:
        current = match_preset(settings.tariff_per_kwh, settings.currency, today)

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", width=3)
    table.add_column(justify="left", width=30)
    table.add_column(justify="right", width=12)
    table.add_column(justify="left")

    for index, preset in enumerate(TARIFF_PRESETS, start=1):
        chosen = current is not None and current.key == preset.key
        note = preset.description
        upcoming = preset.upcoming_change(today)
        if upcoming is not None:
            note += (
                f", с {upcoming.effective_from.strftime('%d.%m.%Y')} будет "
                f"{format_price(upcoming.price)} {preset.currency}"
            )
        table.add_row(
            Text(f"[{index}]", style="app.accent"),
            Text(("● " if chosen else "  ") + preset.region, style="app.accent" if chosen else "app.value"),
            Text(f"{format_price(preset.price_on(today))} {preset.currency}", style="app.value"),
            Text(note, style="app.muted"),
        )

    sources = Table.grid(padding=(0, 2))
    sources.add_column(justify="left", width=30)
    sources.add_column(justify="left")
    for preset in TARIFF_PRESETS:
        sources.add_row(Text(preset.region, style="app.muted"), Text(preset.source, style="app.muted"))

    body = Group(
        table,
        Text(""),
        Text("Откуда цифры", style="app.label"),
        sources,
        Text(""),
        Text(
            "Тариф зависит от региона, счётчика и категории жилья. Любое значение "
            "можно заменить своим в настройках.",
            style="app.hint",
        ),
    )
    return Panel(body, title="[app.label]Тариф на электроэнергию", border_style="app.border", padding=(1, 2))


def pick_tariff(console: Console, settings: Settings) -> Settings:
    """Показывает справочник и применяет выбранный тариф."""
    console.print(tariffs_panel(settings))
    choices = [str(index) for index in range(1, len(TARIFF_PRESETS) + 1)]
    answer = Prompt.ask(
        "[app.accent]Какой тариф применить[/app.accent] [app.muted](0 - оставить как есть)[/app.muted]",
        choices=[*choices, "0"],
        default="0",
        console=console,
        show_choices=False,
    )
    if answer == "0":
        return settings

    preset = TARIFF_PRESETS[int(answer) - 1]
    updated = replace(
        settings,
        tariff_per_kwh=preset.price_on(date.today()),
        currency=preset.currency,
    ).normalized()
    save_settings(updated)
    console.print(
        Text(
            f"Тариф: {format_price(updated.tariff_per_kwh)} {updated.currency} за кВт·ч ({preset.region})",
            style="app.ok",
        )
    )
    return updated


def donate_panel() -> RenderableType:
    """Реквизиты для поддержки проекта."""
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="left", width=10)
    table.add_column(justify="left", width=11)
    table.add_column(justify="left")

    for donation in DONATION_ADDRESSES:
        table.add_row(
            Text(donation.network, style="app.label"),
            Text(donation.asset, style="app.muted"),
            Text(donation.address, style="app.accent"),
        )

    body = Group(
        Text(DONATION_NOTE, style="app.muted"),
        Text(""),
        table,
        Text(""),
        Text.assemble(("Спасибо. ", "app.muted"), (AUTHOR_TELEGRAM, "app.accent")),
    )
    return Panel(body, title="[app.label]Поддержать проект", border_style="app.accent", padding=(1, 2))


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

    number = parse_number(raw)
    if number is None:
        raise ValueError(f"в строке {raw!r} нет числа")

    if field.kind == "int":
        return int(number)
    if field.kind == "percent":
        return number / 100.0 if number > 1.0 else number
    return number
