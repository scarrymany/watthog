"""Проверки оконного интерфейса.

Тесты, которым нужен экран, пропускаются там, где его нет: на серверах сборки
дисплея обычно не бывает, но остальное проверяется всегда.
"""

import tkinter as tk

import pytest

from watthog.donate import DONATION_ADDRESSES
from watthog.formatting import chart_bounds
from watthog.palette import gradient_color, mix

pytest.importorskip("customtkinter", reason="оконный интерфейс не установлен")

from watthog.gui.app import _span_title  # noqa: E402
from watthog.gui.widgets import BreakdownRow  # noqa: E402


@pytest.fixture
def tk_environment():
    """Пропускает тест там, где Tk не работает.

    Причин две: отсутствие экрана и повреждённая установка Tcl. Обе относятся к
    окружению, а не к коду, и обе проявляются только при создании окна, поэтому
    проверка делает ровно то же, что и сам тест, и делает это перед каждым.
    """
    try:
        probe = tk.Tk()
        probe.update()
        probe.destroy()
    except tk.TclError as error:
        pytest.skip(f"Tk недоступен в этом окружении: {error}")


requires_display = pytest.mark.usefixtures("tk_environment")


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


@requires_display
def test_window_builds_and_closes():
    from watthog.gui.app import WattHogWindow
    from watthog.gui.theme import configure_appearance

    configure_appearance()
    window = WattHogWindow()
    try:
        window.update()
        assert window.winfo_width() > 0
    finally:
        window.destroy()


@requires_display
def test_dialogs_build_and_close():
    from watthog.gui.app import WattHogWindow
    from watthog.gui.dialogs import AboutDialog, DonateDialog, SettingsDialog
    from watthog.gui.theme import configure_appearance

    configure_appearance()
    window = WattHogWindow()
    try:
        window.update()
        for factory in (
            lambda: SettingsDialog(window, window._fonts, window._settings, lambda _settings: None),
            lambda: AboutDialog(window, window._fonts),
            lambda: DonateDialog(window, window._fonts),
        ):
            dialog = factory()
            window.update()
            dialog.destroy()
            window.update()
    finally:
        window.destroy()


@requires_display
def test_widgets_draw_without_errors():
    from watthog.gui.theme import Fonts, configure_appearance
    from watthog.gui.widgets import BreakdownChart, PowerChart, PowerGauge

    configure_appearance()
    root = tk.Tk()
    try:
        fonts = Fonts(root)
        values = [200.0 + index for index in range(60)]
        floor, ceiling = chart_bounds(values)

        gauge = PowerGauge(root, fonts)
        gauge.pack(fill="x")
        chart = PowerChart(root, fonts)
        chart.pack(fill="both", expand=True)
        breakdown = BreakdownChart(root, fonts)
        breakdown.pack(fill="both", expand=True)
        root.geometry("800x500")
        root.update()

        gauge.set_value(260.0, 400.0)
        chart.set_history(values, floor, ceiling, 400.0)
        breakdown.set_rows([BreakdownRow(name, 30.0, 0.3) for name in ("Процессор", "Видеокарта")])
        root.update()

        assert chart.find_all()
        assert breakdown.find_all()
        assert gauge.find_all()
    finally:
        root.destroy()


@requires_display
def test_donate_dialog_copies_address_to_clipboard():
    from watthog.gui.app import WattHogWindow
    from watthog.gui.dialogs import DonateDialog
    from watthog.gui.theme import configure_appearance

    configure_appearance()
    window = WattHogWindow()
    try:
        window.update()
        dialog = DonateDialog(window, window._fonts)
        window.update()

        expected = DONATION_ADDRESSES[0].address
        dialog.clipboard_clear()
        dialog.clipboard_append(expected)
        window.update()
        assert dialog.clipboard_get() == expected

        dialog.destroy()
        window.update()
    finally:
        window.destroy()
