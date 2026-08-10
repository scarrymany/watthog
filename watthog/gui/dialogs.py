"""Модальные окна: настройки, состав железа и справка."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

import customtkinter as ctk

from watthog import APP_NAME, AUTHOR_TELEGRAM, REPO_URL, __version__
from watthog.config import Settings, config_path, save_settings
from watthog.donate import DONATION_ADDRESSES, DONATION_NOTE, DonationAddress
from watthog.formatting import format_price, format_watts, parse_number
from watthog.gui.theme import (
    ACCENT,
    BACKGROUND,
    BORDER,
    OK,
    SIZE_BASE,
    SIZE_SMALL,
    SIZE_TINY,
    SIZE_TITLE,
    SURFACE,
    TEXT,
    TEXT_MUTED,
    Fonts,
    apply_window_icon,
    card,
    entry,
    ghost_button,
    heading,
    muted,
    primary_button,
)
from watthog.inventory import GpuKind, HardwareProfile
from watthog.tariffs import CUSTOM_PRESET_TITLE, TARIFF_PRESETS, TariffPreset, match_preset
from watthog.telemetry import SourceStatus

_AUTO_LABEL = "авто"
_AUTO_INPUT_VALUES = frozenset({"авто", "auto", "-", ""})
# Захват фокуса сразу после создания окна на Windows иногда срывается,
# поэтому он ставится следующим тактом цикла событий.
_GRAB_DELAY_MS = 120


class _Dialog(ctk.CTkToplevel):
    """Модальное окно с общими правилами поведения."""

    def __init__(self, parent: tk.Misc, fonts: Fonts, title: str, width: int, height: int) -> None:
        super().__init__(parent, fg_color=BACKGROUND)
        self._fonts = fonts
        self.title(f"{APP_NAME} - {title}")
        self.geometry(f"{width}x{height}")
        self.minsize(width, height)
        self.transient(parent)
        self.resizable(False, False)
        apply_window_icon(self)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(_GRAB_DELAY_MS, self._take_focus)
        self._center_on(parent, width, height)

    def _take_focus(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _center_on(self, parent: tk.Misc, width: int, height: int) -> None:
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 3
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")


@dataclass(frozen=True)
class _Field:
    """Описание одной редактируемой настройки."""

    name: str
    title: str
    hint: str
    kind: str
    optional: bool = False

    def display(self, settings: Settings) -> str:
        value = getattr(settings, self.name)
        if value is None:
            return _AUTO_LABEL
        if self.kind == "percent":
            return f"{value * 100:.0f}"
        if self.kind == "int":
            return str(int(value))
        if self.kind == "text":
            return str(value)
        return f"{value:g}"


_FIELDS: tuple[_Field, ...] = (
    _Field("duration_seconds", "Длительность замера", "секунд", "int"),
    _Field("sample_interval", "Интервал выборки", "секунд", "float"),
    _Field("tariff_per_kwh", "Тариф за кВт·ч", "цена киловатт-часа", "float"),
    _Field("currency", "Валюта", "знак в отчёте", "text"),
    _Field("psu_peak_efficiency", "Пиковый КПД блока питания", "%, Gold ~90", "percent"),
    _Field("psu_rated_watts", "Номинал блока питания", "Вт", "int"),
    _Field("extra_devices_watts", "Периферия", "Вт, монитор и колонки", "float"),
    _Field("cpu_peak_watts", "Пик процессора", "Вт", "float", optional=True),
    _Field("gpu_peak_watts", "Пик видеокарты", "Вт", "float", optional=True),
    _Field("platform_watts", "Плата и обвязка", "Вт", "float", optional=True),
)


class SettingsDialog(_Dialog):
    """Редактор настроек измерения и калибровки модели."""

    def __init__(
        self,
        parent: tk.Misc,
        fonts: Fonts,
        settings: Settings,
        on_apply: Callable[[Settings], None],
    ) -> None:
        super().__init__(parent, fonts, "настройки", 620, 700)
        self._settings = settings
        self._on_apply = on_apply
        self._inputs: dict[str, ctk.CTkEntry] = {}
        self._save_reports = tk.BooleanVar(value=settings.save_reports)
        self._build()

    def _build(self) -> None:
        container = card(self)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            container,
            text="Настройки",
            font=self._fonts.ctk(SIZE_TITLE, bold=True),
            text_color=TEXT,
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 2))
        muted(
            container,
            "Пустое значение или «авто» - определить по железу автоматически.",
            self._fonts,
            SIZE_TINY,
        ).pack(fill="x", padx=16, pady=(0, 10))

        self._add_preset_picker(container)

        form = ctk.CTkScrollableFrame(container, fg_color="transparent", scrollbar_button_color=BORDER)
        form.pack(fill="both", expand=True, padx=8)

        for field in _FIELDS:
            self._add_field(form, field)

        ctk.CTkCheckBox(
            form,
            text="Сохранять отчёты автоматически",
            variable=self._save_reports,
            font=self._fonts.ctk(SIZE_BASE),
            text_color=TEXT,
            fg_color=ACCENT,
            hover_color=ACCENT,
            checkmark_color=BACKGROUND,
            border_color=BORDER,
        ).pack(fill="x", padx=8, pady=(12, 4))

        muted(form, f"Файл настроек: {config_path()}", self._fonts, SIZE_TINY).pack(
            fill="x", padx=8, pady=(6, 4)
        )

        buttons = ctk.CTkFrame(container, fg_color="transparent")
        buttons.pack(fill="x", padx=16, pady=(8, 14))
        primary_button(buttons, "Сохранить", self._apply, self._fonts, width=150).pack(side="right")
        ghost_button(buttons, "Отмена", self.destroy, self._fonts, width=110).pack(side="right", padx=(0, 10))
        ghost_button(buttons, "Сбросить", self._reset, self._fonts, width=110).pack(side="left")

    def _add_preset_picker(self, parent: tk.Misc) -> None:
        """Выбор готового тарифа: заполняет цену и валюту одним движением."""
        today = date.today()
        self._presets_by_label = {_preset_label(preset, today): preset for preset in TARIFF_PRESETS}
        labels = [*self._presets_by_label, CUSTOM_PRESET_TITLE]

        current = match_preset(self._settings.tariff_per_kwh, self._settings.currency, today)
        selected = CUSTOM_PRESET_TITLE
        if current is not None:
            selected = _preset_label(current, today)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 8))

        labels_column = ctk.CTkFrame(row, fg_color="transparent")
        labels_column.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            labels_column,
            text="Тариф из справочника",
            font=self._fonts.ctk(SIZE_BASE),
            text_color=TEXT,
            anchor="w",
        ).pack(fill="x")
        self._preset_hint = muted(labels_column, "", self._fonts, SIZE_TINY)
        self._preset_hint.pack(fill="x")

        self._preset_menu = ctk.CTkOptionMenu(
            row,
            values=labels,
            command=self._apply_preset,
            width=230,
            height=34,
            font=self._fonts.ctk(SIZE_SMALL),
            fg_color=BACKGROUND,
            button_color=BORDER,
            button_hover_color=ACCENT,
            text_color=TEXT,
            dropdown_fg_color=SURFACE,
            dropdown_text_color=TEXT,
            dropdown_hover_color=BORDER,
            dropdown_font=self._fonts.ctk(SIZE_SMALL),
        )
        self._preset_menu.set(selected)
        self._preset_menu.pack(side="right")
        self._update_preset_hint(current)

    def _apply_preset(self, label: str) -> None:
        preset = self._presets_by_label.get(label)
        self._update_preset_hint(preset)
        if preset is None:
            return

        today = date.today()
        for name, value in (
            ("tariff_per_kwh", f"{preset.price_on(today):g}"),
            ("currency", preset.currency),
        ):
            widget = self._inputs[name]
            widget.delete(0, "end")
            widget.insert(0, value)

    def _update_preset_hint(self, preset: TariffPreset | None) -> None:
        if preset is None:
            self._preset_hint.configure(text="цена и валюта задаются вручную")
            return

        hint = preset.source
        upcoming = preset.upcoming_change(date.today())
        if upcoming is not None:
            hint += (
                f"; с {upcoming.effective_from.strftime('%d.%m.%Y')} будет "
                f"{format_price(upcoming.price)} {preset.currency}"
            )
        self._preset_hint.configure(text=hint)

    def _add_field(self, parent: tk.Misc, field: _Field) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=5)

        labels = ctk.CTkFrame(row, fg_color="transparent")
        labels.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            labels, text=field.title, font=self._fonts.ctk(SIZE_BASE), text_color=TEXT, anchor="w"
        ).pack(fill="x")
        muted(labels, field.hint, self._fonts, SIZE_TINY).pack(fill="x")

        widget = entry(row, self._fonts, width=110)
        widget.insert(0, field.display(self._settings))
        widget.pack(side="right")
        self._inputs[field.name] = widget

    def _reset(self) -> None:
        self._settings = Settings()
        for field in _FIELDS:
            widget = self._inputs[field.name]
            widget.delete(0, "end")
            widget.insert(0, field.display(self._settings))
        self._save_reports.set(self._settings.save_reports)

    def _apply(self) -> None:
        updated = replace(self._settings, save_reports=self._save_reports.get())
        for field in _FIELDS:
            raw = self._inputs[field.name].get().strip()
            value = _parse_field(field, raw)
            if value is _INVALID:
                continue
            updated = replace(updated, **{field.name: value})

        normalized = updated.normalized()
        save_settings(normalized)
        self._on_apply(normalized)
        self.destroy()


_INVALID = object()


def _preset_label(preset: TariffPreset, today: date) -> str:
    return f"{preset.region} - {format_price(preset.price_on(today))} {preset.currency}"


def _parse_field(field: _Field, raw: str) -> object:
    if field.kind == "text":
        return raw or None if field.optional else (raw or _INVALID)
    if field.optional and raw.lower() in _AUTO_INPUT_VALUES:
        return None

    number = parse_number(raw)
    if number is None:
        return _INVALID
    if field.kind == "int":
        return int(number)
    if field.kind == "percent":
        return number / 100.0 if number > 1.0 else number
    return number


class HardwareDialog(_Dialog):
    """Состав железа и список доступных источников телеметрии."""

    def __init__(
        self,
        parent: tk.Misc,
        fonts: Fonts,
        profile: HardwareProfile,
        sources: tuple[SourceStatus, ...],
    ) -> None:
        super().__init__(parent, fonts, "железо", 660, 560)
        self._build(profile, sources)

    def _build(self, profile: HardwareProfile, sources: tuple[SourceStatus, ...]) -> None:
        container = card(self)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        body = ctk.CTkScrollableFrame(container, fg_color="transparent", scrollbar_button_color=BORDER)
        body.pack(fill="both", expand=True, padx=8, pady=12)

        heading(body, "Железо", self._fonts).pack(fill="x", padx=8, pady=(0, 6))
        for label, value in _hardware_rows(profile):
            self._add_row(body, label, value)

        heading(body, "Источники данных", self._fonts).pack(fill="x", padx=8, pady=(16, 6))
        for source in sources:
            self._add_source(body, source)

        ghost_button(container, "Закрыть", self.destroy, self._fonts, width=120).pack(pady=(0, 14))

    def _add_row(self, parent: tk.Misc, label: str, value: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=3)
        ctk.CTkLabel(
            row,
            text=label,
            font=self._fonts.ctk(SIZE_SMALL),
            text_color=TEXT_MUTED,
            anchor="w",
            width=130,
        ).pack(side="left")
        ctk.CTkLabel(
            row,
            text=value,
            font=self._fonts.ctk(SIZE_SMALL),
            text_color=TEXT,
            anchor="w",
            justify="left",
            wraplength=440,
        ).pack(side="left", fill="x", expand=True)

    def _add_source(self, parent: tk.Misc, source: SourceStatus) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=3)
        ctk.CTkLabel(
            row,
            text="●",
            font=self._fonts.ctk(SIZE_BASE),
            text_color=OK if source.active else BORDER,
            width=22,
        ).pack(side="left")
        ctk.CTkLabel(
            row,
            text=source.name,
            font=self._fonts.ctk(SIZE_SMALL, bold=True),
            text_color=TEXT if source.active else TEXT_MUTED,
            anchor="w",
            width=170,
        ).pack(side="left")
        ctk.CTkLabel(
            row,
            text=source.detail,
            font=self._fonts.ctk(SIZE_SMALL),
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=380,
        ).pack(side="left", fill="x", expand=True)


def _hardware_rows(profile: HardwareProfile) -> list[tuple[str, str]]:
    cpu = profile.cpu
    rows = [
        ("Система", f"{profile.os_description}, {profile.form_factor.value}"),
        (
            "Процессор",
            f"{cpu.name}\n{cpu.physical_cores} ядер / {cpu.logical_cores} потоков, "
            f"до {format_watts(cpu.peak_watts)} Вт ({cpu.power_source})",
        ),
    ]
    for gpu in profile.gpus:
        if gpu.draws_own_power:
            detail = f"{gpu.kind.value}, до {format_watts(gpu.peak_watts)} Вт ({gpu.power_source})"
        elif gpu.kind is GpuKind.INTEGRATED:
            detail = "встроенная, питается от пакета процессора"
        else:
            detail = "виртуальная, собственного питания нет"
        rows.append(("Видеокарта", f"{gpu.name}\n{detail}"))

    rows.append(("Память", f"{profile.ram_gib:.1f} ГБ"))
    rows.append(("Накопители", str(profile.disk_count)))
    return rows


class AboutDialog(_Dialog):
    """Короткая справка о том, как считается мощность."""

    _POINTS = (
        "Видеокарты NVIDIA читаются через NVML - это реальная мощность платы.",
        "Видеокарты AMD и Intel в Linux читаются через hwmon, тоже реальные ватты.",
        "Процессор в Linux читается через RAPL, если есть доступ к счётчику энергии.",
        "На ноутбуке от батареи измеряется потребление всей системы сразу.",
        "Остальное считается по загрузке, частоте и справочным пределам мощности.",
        "К сумме добавляются потери блока питания - их тоже оплачивает счётчик.",
    )

    def __init__(self, parent: tk.Misc, fonts: Fonts) -> None:
        super().__init__(parent, fonts, "о программе", 600, 470)
        self._build()

    def _build(self) -> None:
        container = card(self)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            container,
            text=f"{APP_NAME} {__version__}",
            font=self._fonts.ctk(SIZE_TITLE, bold=True),
            text_color=ACCENT,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 2))
        muted(container, "Измеритель прожорливости ПК", self._fonts).pack(fill="x", padx=18)

        ctk.CTkLabel(
            container,
            text="Программа берёт показания настоящих датчиков там, где они есть,\n"
            "и достраивает картину моделью там, где их нет.",
            font=self._fonts.ctk(SIZE_SMALL),
            text_color=TEXT,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=18, pady=(14, 8))

        for point in self._POINTS:
            row = ctk.CTkFrame(container, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=1)
            ctk.CTkLabel(
                row, text="•", font=self._fonts.ctk(SIZE_SMALL), text_color=ACCENT, width=14
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=point,
                font=self._fonts.ctk(SIZE_SMALL),
                text_color=TEXT_MUTED,
                anchor="w",
                justify="left",
                wraplength=500,
            ).pack(side="left", fill="x", expand=True)

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(16, 16), side="bottom")
        ctk.CTkLabel(
            footer,
            text=f"Автор {AUTHOR_TELEGRAM}",
            font=self._fonts.ctk(SIZE_SMALL, bold=True),
            text_color=ACCENT,
            anchor="w",
        ).pack(side="left")
        muted(footer, REPO_URL, self._fonts, SIZE_TINY).pack(side="right")


class DonateDialog(_Dialog):
    """Реквизиты для поддержки проекта с копированием в буфер обмена."""

    _COPIED_LABEL = "Скопировано"
    _COPY_LABEL = "Копировать"
    _COPIED_RESET_MS = 1600

    def __init__(self, parent: tk.Misc, fonts: Fonts) -> None:
        super().__init__(parent, fonts, "поддержать", 640, 600)
        self._build()

    def _build(self) -> None:
        container = card(self)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            container,
            text="Поддержать проект",
            font=self._fonts.ctk(SIZE_TITLE, bold=True),
            text_color=ACCENT,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            container,
            text=DONATION_NOTE,
            font=self._fonts.ctk(SIZE_SMALL),
            text_color=TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=540,
        ).pack(fill="x", padx=18, pady=(0, 12))

        for donation in DONATION_ADDRESSES:
            self._add_address(container, donation)

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(10, 16))
        ctk.CTkLabel(
            footer,
            text=f"Спасибо. {AUTHOR_TELEGRAM}",
            font=self._fonts.ctk(SIZE_SMALL, bold=True),
            text_color=ACCENT,
        ).pack(side="left")
        ghost_button(footer, "Закрыть", self.destroy, self._fonts, width=110).pack(side="right")

    def _add_address(self, parent: tk.Misc, donation: DonationAddress) -> None:
        row = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10, border_color=BORDER, border_width=1)
        row.pack(fill="x", padx=14, pady=4)

        titles = ctk.CTkFrame(row, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        header_row = ctk.CTkFrame(titles, fg_color="transparent")
        header_row.pack(fill="x")
        ctk.CTkLabel(
            header_row,
            text=donation.network,
            font=self._fonts.ctk(SIZE_BASE, bold=True),
            text_color=TEXT,
            anchor="w",
        ).pack(side="left")
        muted(header_row, f"  {donation.asset}", self._fonts, SIZE_TINY).pack(side="left")

        ctk.CTkLabel(
            titles,
            text=donation.address,
            font=self._fonts.ctk_mono(SIZE_TINY),
            text_color=TEXT_MUTED,
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        button = ghost_button(
            row, self._COPY_LABEL, lambda: None, self._fonts, width=118
        )
        button.configure(command=lambda: self._copy(donation.address, button))
        button.pack(side="right", padx=12)

    def _copy(self, address: str, button: ctk.CTkButton) -> None:
        self.clipboard_clear()
        self.clipboard_append(address)
        self.update()
        button.configure(text=self._COPIED_LABEL, text_color=OK)
        self.after(self._COPIED_RESET_MS, lambda: button.configure(text=self._COPY_LABEL, text_color=TEXT))


__all__ = ["AboutDialog", "DonateDialog", "HardwareDialog", "SettingsDialog"]
