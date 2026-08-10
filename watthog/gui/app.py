"""Главное окно WattHog."""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from watthog import APP_NAME, AUTHOR_TELEGRAM, __version__
from watthog import constants as const
from watthog.config import Settings, load_settings, save_settings
from watthog.formatting import (
    chart_bounds,
    format_kwh,
    format_money,
    format_watts,
    parse_number,
    shorten_hardware_name,
)
from watthog.gui.dialogs import AboutDialog, DonateDialog, HardwareDialog, SettingsDialog
from watthog.gui.theme import (
    ACCENT,
    ACCENT_HOVER,
    BACKGROUND,
    DANGER,
    DANGER_HOVER,
    SIZE_BASE,
    SIZE_MEDIUM,
    SIZE_READOUT,
    SIZE_SMALL,
    SIZE_TINY,
    SIZE_TITLE,
    SURFACE_RAISED,
    TEXT,
    TEXT_MUTED,
    Fonts,
    apply_window_icon,
    card,
    configure_appearance,
    entry,
    ghost_button,
    heading,
    muted,
    primary_button,
)
from watthog.gui.widgets import BreakdownChart, BreakdownRow, PowerChart, PowerGauge
from watthog.gui.worker import (
    HardwareFound,
    HardwareProbe,
    MeasurementFinished,
    MeasurementWorker,
    SampleTaken,
    TaskFailed,
)
from watthog.inventory import HardwareProfile
from watthog.meter import ACCURACY_DETAILS
from watthog.palette import gradient_color
from watthog.projections import build_projections, consumption_tier
from watthog.session import SessionResult
from watthog.telemetry import SourceStatus
from watthog.ui.report import save_report

WINDOW_WIDTH = 1120
WINDOW_HEIGHT = 930
WINDOW_MIN_WIDTH = 960
WINDOW_MIN_HEIGHT = 820
# Без нижней границы строка графика отдаёт всё место соседям и схлопывается.
CHART_ROW_MIN_HEIGHT = 210
_POLL_INTERVAL_MS = 60
_MIN_SCALE_WATTS = 50.0
_SCALE_HEADROOM = 1.15
_PROJECTION_CARD_HOURS = (1.0, 10.0, 12.0, 24.0, 168.0, 720.0)
_UNSUPPORTED_PLATFORM_EXIT_CODE = 2
_PLACEHOLDER = "-"
_IDLE_READOUT_TEXT = "нет данных"


class WattHogWindow(ctk.CTk):
    """Окно замера: живые показания, разбивка, график и прогноз расхода."""

    def __init__(self) -> None:
        super().__init__(fg_color=BACKGROUND)
        self._settings = load_settings()
        self._fonts = Fonts(self)

        self.title(f"{APP_NAME} {__version__} - измеритель прожорливости ПК")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._probe = HardwareProbe()
        self._worker = MeasurementWorker()
        self._profile: HardwareProfile | None = None
        self._sources: tuple[SourceStatus, ...] = ()
        self._result: SessionResult | None = None
        self._history: list[float] = []
        self._minimum = 0.0
        self._maximum = 0.0

        self._build()
        self._probe.start(self._settings)
        self.after(_POLL_INTERVAL_MS, self._poll)

    # -- построение интерфейса ---------------------------------------------

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1, minsize=CHART_ROW_MIN_HEIGHT)

        self._build_header()
        self._build_body()
        self._build_chart()
        self._build_controls()
        self._build_projections()
        self._build_status()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        header.grid_columnconfigure(1, weight=1)

        title = ctk.CTkFrame(header, fg_color="transparent")
        title.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title,
            text=f"⚡ {APP_NAME}",
            font=self._fonts.ctk(SIZE_TITLE, bold=True),
            text_color=ACCENT,
        ).pack(side="left")
        ctk.CTkLabel(
            title,
            text=f"  v{__version__}",
            font=self._fonts.ctk(SIZE_SMALL),
            text_color=TEXT_MUTED,
        ).pack(side="left", pady=(6, 0))

        self._hardware_label = ctk.CTkLabel(
            header,
            text="определяю железо...",
            font=self._fonts.ctk(SIZE_SMALL),
            text_color=TEXT_MUTED,
            anchor="e",
        )
        self._hardware_label.grid(row=0, column=1, sticky="ew", padx=14)

        buttons = ctk.CTkFrame(header, fg_color="transparent")
        buttons.grid(row=0, column=2, sticky="e")
        ghost_button(buttons, "Железо", self._open_hardware, self._fonts, width=96).pack(side="left", padx=4)
        ghost_button(buttons, "Настройки", self._open_settings, self._fonts, width=110).pack(side="left", padx=4)
        ghost_button(buttons, "О программе", self._open_about, self._fonts, width=120).pack(side="left", padx=4)
        ghost_button(
            buttons, "♥ Поддержать", self._open_donate, self._fonts, width=130, text_color=ACCENT
        ).pack(side="left", padx=4)

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=16, pady=6)
        body.grid_columnconfigure(0, weight=3, uniform="body")
        body.grid_columnconfigure(1, weight=4, uniform="body")

        readout = card(body)
        readout.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        heading(readout, "Текущая мощность из розетки", self._fonts).pack(fill="x", padx=16, pady=(12, 2))

        value_row = ctk.CTkFrame(readout, fg_color="transparent")
        value_row.pack(fill="x", padx=16)
        self._readout = ctk.CTkLabel(value_row, text="", font=self._fonts.ctk(SIZE_READOUT, bold=True))
        self._readout.pack(side="left")
        self._readout_unit = ctk.CTkLabel(
            value_row, text="Вт", font=self._fonts.ctk(SIZE_MEDIUM), text_color=TEXT_MUTED
        )
        self._readout_unit.pack(side="left", padx=(8, 0), pady=(28, 0))
        self._set_readout_idle()

        self._gauge = PowerGauge(readout, self._fonts)
        self._gauge.pack(fill="x", padx=16, pady=(4, 8))

        self._stats_label = muted(readout, "мин - · сред - · макс -", self._fonts)
        self._stats_label.pack(fill="x", padx=16)

        tier_row = ctk.CTkFrame(readout, fg_color="transparent")
        tier_row.pack(fill="x", padx=16, pady=(6, 14))
        self._tier_label = ctk.CTkLabel(
            tier_row, text="", font=self._fonts.ctk(SIZE_BASE, bold=True), text_color=TEXT_MUTED
        )
        self._tier_label.pack(side="left")
        self._sensors_label = muted(tier_row, "", self._fonts, SIZE_TINY)
        self._sensors_label.pack(side="left", padx=(12, 0))

        breakdown = card(body)
        breakdown.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        heading(breakdown, "Разбивка по компонентам", self._fonts).pack(fill="x", padx=16, pady=(12, 6))
        self._breakdown = BreakdownChart(breakdown, self._fonts)
        self._breakdown.pack(fill="both", expand=True, padx=12)
        self._totals_label = muted(breakdown, "", self._fonts)
        self._totals_label.pack(fill="x", padx=16, pady=(4, 14))

    def _build_chart(self) -> None:
        container = card(self)
        container.grid(row=2, column=0, sticky="nsew", padx=16, pady=6)
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))
        heading(header, "График мощности", self._fonts).pack(side="left")
        self._chart_scale_label = muted(header, "", self._fonts, SIZE_TINY)
        self._chart_scale_label.pack(side="right")

        self._chart = PowerChart(container, self._fonts)
        self._chart.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _build_controls(self) -> None:
        container = card(self)
        container.grid(row=3, column=0, sticky="ew", padx=16, pady=6)

        row = ctk.CTkFrame(container, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=12)

        self._duration_input = self._labelled_entry(row, "Длительность, с", str(self._settings.duration_seconds))
        self._tariff_input = self._labelled_entry(row, "Тариф за кВт·ч", f"{self._settings.tariff_per_kwh:g}")

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="right")
        self._save_button = ghost_button(actions, "Сохранить отчёт", self._save_report, self._fonts, width=150)
        self._save_button.configure(state="disabled")
        self._save_button.pack(side="right", padx=(10, 0))
        self._start_button = primary_button(actions, "Запустить замер", self._start, self._fonts, width=180)
        self._start_button.pack(side="right")

        progress_row = ctk.CTkFrame(container, fg_color="transparent")
        progress_row.pack(fill="x", padx=16, pady=(0, 12))
        self._progress = ctk.CTkProgressBar(
            progress_row, height=8, corner_radius=4, fg_color=SURFACE_RAISED, progress_color=ACCENT
        )
        self._progress.set(0.0)
        self._progress.pack(side="left", fill="x", expand=True, pady=6)
        self._progress_label = muted(progress_row, "готов к запуску", self._fonts, SIZE_TINY)
        self._progress_label.pack(side="right", padx=(12, 0))

    def _labelled_entry(self, parent: tk.Misc, title: str, value: str) -> ctk.CTkEntry:
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.pack(side="left", padx=(0, 22))
        muted(holder, title, self._fonts, SIZE_TINY).pack(anchor="w")
        widget = entry(holder, self._fonts, width=110)
        widget.insert(0, value)
        widget.pack(anchor="w", pady=(2, 0))
        return widget

    def _build_projections(self) -> None:
        container = card(self)
        container.grid(row=4, column=0, sticky="ew", padx=16, pady=6)
        heading(container, "Прогноз расхода", self._fonts).pack(fill="x", padx=16, pady=(12, 6))

        grid = ctk.CTkFrame(container, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=(0, 14))

        self._projection_cards: list[tuple[ctk.CTkLabel, ctk.CTkLabel, ctk.CTkLabel]] = []
        for index, hours in enumerate(_PROJECTION_CARD_HOURS):
            grid.grid_columnconfigure(index, weight=1, uniform="projection")
            cell = ctk.CTkFrame(grid, fg_color=SURFACE_RAISED, corner_radius=10)
            cell.grid(row=0, column=index, sticky="ew", padx=4)

            span = ctk.CTkLabel(
                cell,
                text=_span_title(hours),
                font=self._fonts.ctk(SIZE_TINY),
                text_color=TEXT_MUTED,
            )
            span.pack(pady=(8, 0))
            energy = ctk.CTkLabel(
                cell, text=_PLACEHOLDER, font=self._fonts.ctk(SIZE_MEDIUM, bold=True), text_color=TEXT
            )
            energy.pack()
            cost = ctk.CTkLabel(cell, text="", font=self._fonts.ctk(SIZE_TINY), text_color=ACCENT)
            cost.pack(pady=(0, 8))
            self._projection_cards.append((span, energy, cost))

    def _build_status(self) -> None:
        status = ctk.CTkFrame(self, fg_color="transparent")
        status.grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 12))
        status.grid_columnconfigure(1, weight=1)

        self._sources_label = muted(status, "источники: определяю...", self._fonts, SIZE_TINY)
        self._sources_label.grid(row=0, column=0, sticky="w")

        self._accuracy_label = ctk.CTkLabel(
            status, text="", font=self._fonts.ctk(SIZE_TINY), text_color=TEXT_MUTED
        )
        self._accuracy_label.grid(row=0, column=1)

        ctk.CTkLabel(
            status,
            text=f"автор {AUTHOR_TELEGRAM}",
            font=self._fonts.ctk(SIZE_TINY, bold=True),
            text_color=ACCENT,
        ).grid(row=0, column=2, sticky="e")

    # -- события ------------------------------------------------------------

    def _poll(self) -> None:
        for event in [*self._probe.drain(), *self._worker.drain()]:
            self._handle(event)
        self.after(_POLL_INTERVAL_MS, self._poll)

    def _handle(self, event: object) -> None:
        if isinstance(event, HardwareFound):
            self._profile = event.profile
            self._sources = event.sources
            self._show_hardware_summary()
        elif isinstance(event, SampleTaken):
            self._show_sample(event)
        elif isinstance(event, MeasurementFinished):
            self._show_result(event.result)
        elif isinstance(event, TaskFailed):
            self._finish_run()
            messagebox.showerror(APP_NAME, event.message, parent=self)

    def _show_hardware_summary(self) -> None:
        if self._profile is None:
            return
        parts = [shorten_hardware_name(self._profile.cpu.name)]
        parts.extend(shorten_hardware_name(gpu.name) for gpu in self._profile.discrete_gpus)
        parts.append(f"{self._profile.ram_gib:.0f} ГБ")
        parts.append(self._profile.form_factor.value)
        self._hardware_label.configure(text=" · ".join(parts))

        active = [source.name for source in self._sources if source.active]
        self._sources_label.configure(text=f"источники: {', '.join(active) or 'нет'}")

    def _show_sample(self, event: SampleTaken) -> None:
        sample = event.sample
        self._history.append(sample.watts)
        self._minimum = min(self._history)
        self._maximum = max(self._history)
        scale = max(_MIN_SCALE_WATTS, self._maximum * _SCALE_HEADROOM)

        self._set_readout_value(format_watts(sample.watts), gradient_color(sample.watts / scale))
        self._gauge.set_value(sample.watts, scale)

        average = sum(self._history) / len(self._history)
        self._stats_label.configure(
            text=f"мин {format_watts(self._minimum)} · сред {format_watts(average)} "
            f"· макс {format_watts(self._maximum)}"
        )

        tier_label, tier_color = consumption_tier(sample.watts)
        self._tier_label.configure(text=tier_label, text_color=tier_color)
        self._sensors_label.configure(text=_sensor_summary(event.sample))

        self._update_breakdown(sample)
        self._update_chart(scale)

        fraction = min(1.0, sample.elapsed / event.duration_seconds) if event.duration_seconds else 0.0
        self._progress.set(fraction)
        self._progress_label.configure(text=f"{sample.elapsed:.0f} с из {event.duration_seconds:.0f} с")
        self._accuracy_label.configure(text=f"точность: {sample.accuracy.value}")

    def _set_readout_idle(self) -> None:
        """До первой выборки показывать нечего, и крупные цифры только мешают."""
        self._readout.configure(
            text=_IDLE_READOUT_TEXT, font=self._fonts.ctk(SIZE_MEDIUM), text_color=TEXT_MUTED
        )
        self._readout_unit.configure(text="")

    def _set_readout_value(self, text: str, color: str) -> None:
        self._readout.configure(text=text, font=self._fonts.ctk(SIZE_READOUT, bold=True), text_color=color)
        self._readout_unit.configure(text="Вт")

    def _update_breakdown(self, sample) -> None:
        total = sample.breakdown.total_ac
        rows = [
            BreakdownRow(label, watts, watts / total if total > 0 else 0.0)
            for label, watts in sample.breakdown.components()
            if watts > 0.0
        ]
        self._breakdown.set_rows(rows)
        self._totals_label.configure(
            text=f"железо {format_watts(sample.breakdown.total_dc)} Вт   ·   "
            f"из розетки {format_watts(total)} Вт"
        )

    def _update_chart(self, scale: float) -> None:
        floor, ceiling = chart_bounds(self._history)
        self._chart.set_history(self._history, floor, ceiling, scale)
        self._chart_scale_label.configure(
            text=f"шкала {floor:.0f} - {ceiling:.0f} Вт   ·   {len(self._history)} выборок"
        )

    def _show_result(self, result: SessionResult) -> None:
        self._result = result
        self._finish_run()

        self._set_readout_value(format_watts(result.average_watts), TEXT)
        self._progress.set(1.0)
        self._progress_label.configure(
            text=("замер прерван" if result.interrupted else "замер завершён")
            + f", средняя {format_watts(result.average_watts)} Вт"
        )
        self._accuracy_label.configure(
            text=f"точность: {result.accuracy.value} - {ACCURACY_DETAILS[result.accuracy]}"
        )
        self._fill_projections(result)

        if result.settings.save_reports:
            saved = save_report(result)
            if saved is not None:
                self._sources_label.configure(text=f"отчёт сохранён: {saved.name}")

    def _fill_projections(self, result: SessionResult) -> None:
        projections = {
            projection.hours: projection
            for projection in build_projections(result.average_watts, result.settings.tariff_per_kwh)
        }
        for index, hours in enumerate(_PROJECTION_CARD_HOURS):
            projection = projections.get(hours)
            _, energy_label, cost_label = self._projection_cards[index]
            if projection is None:
                continue
            energy_label.configure(text=f"{format_kwh(projection.kwh)} кВт·ч")
            cost_label.configure(
                text=f"{format_money(projection.cost)} {result.settings.currency}"
                if projection.cost is not None
                else ""
            )

    # -- действия -----------------------------------------------------------

    def _start(self) -> None:
        if self._worker.running:
            return
        self._settings = self._settings_from_inputs()
        save_settings(self._settings)

        self._history.clear()
        self._minimum = 0.0
        self._maximum = 0.0
        self._result = None
        self._set_readout_idle()
        self._stats_label.configure(text="мин - · сред - · макс -")
        self._tier_label.configure(text="")
        self._sensors_label.configure(text="")
        self._breakdown.set_rows([])
        self._chart.set_history([], 0.0, 1.0, 1.0)
        self._chart_scale_label.configure(text="")
        self._progress.set(0.0)
        self._progress_label.configure(text="открываю источники телеметрии...")
        self._save_button.configure(state="disabled")
        self._set_button_mode(running=True)

        self._worker.start(self._settings, float(self._settings.duration_seconds))

    def _stop(self) -> None:
        self._worker.request_stop()
        self._progress_label.configure(text="останавливаю...")

    def _set_button_mode(self, running: bool) -> None:
        """Одна кнопка на два состояния: запуск замера и его остановка."""
        if running:
            self._start_button.configure(
                text="Остановить",
                command=self._stop,
                fg_color=DANGER,
                hover_color=DANGER_HOVER,
                text_color="#ffffff",
            )
            return
        self._start_button.configure(
            text="Запустить замер",
            command=self._start,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=BACKGROUND,
        )

    def _finish_run(self) -> None:
        self._set_button_mode(running=False)
        if self._result is not None:
            self._save_button.configure(state="normal")

    def _settings_from_inputs(self) -> Settings:
        duration = parse_number(self._duration_input.get()) or self._settings.duration_seconds
        tariff = parse_number(self._tariff_input.get())
        updated = replace(
            self._settings,
            duration_seconds=int(duration),
            tariff_per_kwh=tariff if tariff is not None else self._settings.tariff_per_kwh,
        ).normalized()

        self._duration_input.delete(0, "end")
        self._duration_input.insert(0, str(updated.duration_seconds))
        self._tariff_input.delete(0, "end")
        self._tariff_input.insert(0, f"{updated.tariff_per_kwh:g}")
        return updated

    def _save_report(self) -> None:
        if self._result is None:
            return
        target = filedialog.asksaveasfilename(
            parent=self,
            title="Сохранить отчёт",
            defaultextension=".json",
            initialfile=self._result.started_at.strftime(const.REPORT_FILENAME_FORMAT) + ".json",
            filetypes=[("Отчёт JSON", "*.json"), ("Все файлы", "*.*")],
        )
        if not target:
            return
        saved = save_report(self._result, Path(target))
        if saved is None:
            messagebox.showerror(APP_NAME, f"Не удалось записать отчёт в {target}", parent=self)
        else:
            messagebox.showinfo(APP_NAME, f"Отчёт сохранён:\n{saved}", parent=self)

    def _open_settings(self) -> None:
        SettingsDialog(self, self._fonts, self._settings, self._apply_settings)

    def _apply_settings(self, settings: Settings) -> None:
        self._settings = settings
        self._duration_input.delete(0, "end")
        self._duration_input.insert(0, str(settings.duration_seconds))
        self._tariff_input.delete(0, "end")
        self._tariff_input.insert(0, f"{settings.tariff_per_kwh:g}")

    def _open_hardware(self) -> None:
        if self._profile is None:
            messagebox.showinfo(APP_NAME, "Железо ещё определяется, попробуйте через мгновение.", parent=self)
            return
        HardwareDialog(self, self._fonts, self._profile, self._sources)

    def _open_about(self) -> None:
        AboutDialog(self, self._fonts)

    def _open_donate(self) -> None:
        DonateDialog(self, self._fonts)

    def _on_close(self) -> None:
        if self._worker.running:
            self._worker.request_stop()
        self.destroy()


def _span_title(hours: float) -> str:
    if hours >= 24.0 and hours % 24.0 == 0:
        days = int(hours // 24.0)
        return f"{days} дн" if days > 1 else "1 день"
    return f"{int(hours)} ч"


def _sensor_summary(sample) -> str:
    telemetry = sample.telemetry
    parts = [f"ЦП {telemetry.cpu_load * 100:.0f}%"]
    for reading in telemetry.gpus:
        if reading.utilization is not None:
            parts.append(f"GPU {reading.utilization * 100:.0f}%")
        if reading.temperature_c is not None:
            parts.append(f"{reading.temperature_c:.0f}°C")
    battery = telemetry.battery
    if battery is not None and battery.present and battery.charge_percent is not None:
        parts.append(f"батарея {battery.charge_percent:.0f}%")
    return " · ".join(parts)


def main(_argv: list[str] | None = None) -> int:
    if sys.platform == "darwin":
        print(
            f"{APP_NAME} не поддерживает macOS: там нет ни RAPL, ни счётчиков PDH, "
            "и честно измерить систему нечем.",
            file=sys.stderr,
        )
        return _UNSUPPORTED_PLATFORM_EXIT_CODE

    configure_appearance()
    window = WattHogWindow()
    window.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
