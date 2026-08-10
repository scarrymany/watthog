"""Проверки оконного интерфейса.

Тесты, которым нужен экран, пропускаются там, где его нет: на серверах сборки
дисплея обычно не бывает, но остальное проверяется всегда.
"""

import tkinter as tk
from datetime import date

import pytest

from watthog.donate import DONATION_ADDRESSES
from watthog.formatting import chart_bounds
from watthog.palette import gradient_color, mix

pytest.importorskip("customtkinter", reason="оконный интерфейс не установлен")

from watthog.gui.app import _span_title  # noqa: E402
from watthog.gui.widgets import BreakdownRow  # noqa: E402


def _skip_if_tk_is_broken(error: tk.TclError) -> None:
    """Отсутствие экрана и повреждённая установка Tcl - проблемы окружения.

    Отдельная проба перед тестом ненадёжна: на серверах сборки встречается Tk,
    где простое окно создаётся, а полноценное падает на недостающих файлах
    библиотеки. Поэтому пропуск навешивается прямо на создание окна.
    """
    pytest.skip(f"Tk недоступен в этом окружении: {error}")


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
        root.update()
    except tk.TclError as error:
        _skip_if_tk_is_broken(error)
    try:
        yield root
    finally:
        root.destroy()


@pytest.fixture
def gui_window():
    from watthog.gui.app import WattHogWindow
    from watthog.gui.theme import configure_appearance

    configure_appearance()
    try:
        window = WattHogWindow()
        window.update()
    except tk.TclError as error:
        _skip_if_tk_is_broken(error)
    try:
        yield window
    finally:
        window.destroy()


def test_palette_gradient_covers_the_whole_range():
    assert gradient_color(0.0) == "#43d675"
    assert gradient_color(1.0) == "#ff4d4d"
    assert gradient_color(-5.0) == gradient_color(0.0)
    assert gradient_color(5.0) == gradient_color(1.0)


def test_palette_gradient_returns_valid_colors():
    for step in range(0, 101):
        color = gradient_color(step / 100)
        assert len(color) == 7 and color.startswith("#")
        int(color[1:], 16)


def test_mix_returns_the_endpoints():
    assert mix("#000000", "#ffffff", 0.0) == "#000000"
    assert mix("#000000", "#ffffff", 1.0) == "#ffffff"
    assert mix("#000000", "#ffffff", 0.5) == "#808080"


def test_span_title_reads_naturally():
    assert _span_title(1.0) == "1 ч"
    assert _span_title(12.0) == "12 ч"
    assert _span_title(24.0) == "1 день"
    assert _span_title(168.0) == "7 дн"
    assert _span_title(720.0) == "30 дн"


def test_breakdown_row_keeps_its_values():
    row = BreakdownRow("Процессор", 73.7, 0.24)
    assert (row.label, row.watts, row.share) == ("Процессор", 73.7, 0.24)


def test_window_builds_and_shows_placeholders(gui_window):
    assert gui_window.winfo_width() > 0
    assert gui_window._readout.cget("text")
    assert gui_window._save_button.cget("state") == "disabled"


def test_dialogs_build_and_close(gui_window):
    from watthog.gui.dialogs import AboutDialog, DonateDialog, SettingsDialog

    for factory in (
        lambda: SettingsDialog(gui_window, gui_window._fonts, gui_window._settings, lambda _settings: None),
        lambda: AboutDialog(gui_window, gui_window._fonts),
        lambda: DonateDialog(gui_window, gui_window._fonts),
    ):
        dialog = factory()
        gui_window.update()
        dialog.destroy()
        gui_window.update()


def test_widgets_draw_without_errors(tk_root):
    from watthog.gui.theme import Fonts
    from watthog.gui.widgets import BreakdownChart, PowerChart, PowerGauge

    fonts = Fonts(tk_root)
    values = [200.0 + index for index in range(60)]
    floor, ceiling = chart_bounds(values)

    gauge = PowerGauge(tk_root, fonts)
    gauge.pack(fill="x")
    chart = PowerChart(tk_root, fonts)
    chart.pack(fill="both", expand=True)
    breakdown = BreakdownChart(tk_root, fonts)
    breakdown.pack(fill="both", expand=True)
    tk_root.geometry("800x500")
    tk_root.update()

    gauge.set_value(260.0, 400.0)
    chart.set_history(values, floor, ceiling, 400.0)
    breakdown.set_rows([BreakdownRow(name, 30.0, 0.3) for name in ("Процессор", "Видеокарта")])
    tk_root.update()

    assert chart.find_all()
    assert breakdown.find_all()
    assert gauge.find_all()


def test_empty_chart_draws_no_axis_labels(tk_root):
    from watthog.gui.theme import Fonts
    from watthog.gui.widgets import PowerChart

    chart = PowerChart(tk_root, Fonts(tk_root))
    chart.pack(fill="both", expand=True)
    tk_root.geometry("800x400")
    tk_root.update()

    chart.set_history([], 0.0, 1.0, 1.0)
    tk_root.update()

    texts = [chart.itemcget(item, "text") for item in chart.find_all() if chart.type(item) == "text"]
    # Подписи шкалы без данных были бы бессмысленными нулями и единицами.
    assert texts == ["График появится после запуска замера"]


def test_settings_dialog_applies_a_tariff_preset(gui_window, monkeypatch):
    from watthog.gui import dialogs
    from watthog.tariffs import find_preset

    # Настройки пользователя не должны меняться из-за прогона тестов.
    monkeypatch.setattr(dialogs, "save_settings", lambda *_args, **_kwargs: None)

    moscow = find_preset("ru-msk-gas")
    assert moscow is not None
    today = date.today()

    applied: list = []
    dialog = dialogs.SettingsDialog(gui_window, gui_window._fonts, gui_window._settings, applied.append)
    gui_window.update()

    dialog._apply_preset(dialogs._preset_label(moscow, today))
    gui_window.update()
    assert dialog._inputs["currency"].get() == moscow.currency
    assert float(dialog._inputs["tariff_per_kwh"].get()) == moscow.price_on(today)

    dialog._apply()
    gui_window.update()
    assert applied and applied[0].currency == moscow.currency
    assert applied[0].tariff_per_kwh == moscow.price_on(today)


def test_donate_dialog_copies_address_to_clipboard(gui_window):
    from watthog.gui.dialogs import DonateDialog

    dialog = DonateDialog(gui_window, gui_window._fonts)
    gui_window.update()

    expected = DONATION_ADDRESSES[0].address
    dialog.clipboard_clear()
    dialog.clipboard_append(expected)
    gui_window.update()
    assert dialog.clipboard_get() == expected

    dialog.destroy()
    gui_window.update()
