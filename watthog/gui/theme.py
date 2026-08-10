"""Оформление оконного интерфейса: палитра, шрифты и ресурсы.

Цвета задаются явно, а не берутся из темы customtkinter: интерфейс должен
выглядеть одинаково на всех системах и совпадать по палитре с консольной
версией.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

import customtkinter as ctk

from watthog.palette import (
    ACCENT,
    BACKGROUND,
    BORDER,
    DANGER,
    OK,
    SURFACE,
    SURFACE_RAISED,
    TEXT,
    TEXT_MUTED,
)

ACCENT_HOVER = "#ffdf6b"
ACCENT_PRESSED = "#e0b825"
DANGER_HOVER = "#ff6b6b"

CORNER_RADIUS = 12
CARD_BORDER_WIDTH = 1

_UI_FONT_CANDIDATES = ("Segoe UI Variable", "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "Liberation Sans")
_MONO_FONT_CANDIDATES = ("Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono")

SIZE_TINY = 11
SIZE_SMALL = 12
SIZE_BASE = 13
SIZE_MEDIUM = 15
SIZE_TITLE = 20
SIZE_READOUT = 76

_ICON_RELATIVE_PATH = Path("assets") / "watthog.ico"
_LOGO_RELATIVE_PATH = Path("assets") / "logo.png"
# tkinter не удерживает ссылку на изображение окна, поэтому её приходится
# хранить в модуле: иначе сборщик мусора уничтожит иконку сразу после вызова.
_icon_reference: tk.PhotoImage | None = None


class Fonts:
    """Подобранные под систему шрифты и готовые начертания."""

    def __init__(self, root: tk.Misc) -> None:
        available = set(tkfont.families(root))
        self.ui = _first_available(_UI_FONT_CANDIDATES, available, "TkDefaultFont")
        self.mono = _first_available(_MONO_FONT_CANDIDATES, available, "TkFixedFont")

    def ctk(self, size: int = SIZE_BASE, bold: bool = False) -> ctk.CTkFont:
        return ctk.CTkFont(family=self.ui, size=size, weight="bold" if bold else "normal")

    def ctk_mono(self, size: int = SIZE_BASE, bold: bool = False) -> ctk.CTkFont:
        return ctk.CTkFont(family=self.mono, size=size, weight="bold" if bold else "normal")

    def canvas(self, size: int = SIZE_BASE, bold: bool = False) -> tuple:
        return (self.ui, size, "bold") if bold else (self.ui, size)

    def canvas_mono(self, size: int = SIZE_BASE, bold: bool = False) -> tuple:
        return (self.mono, size, "bold") if bold else (self.mono, size)


def _first_available(candidates: tuple[str, ...], available: set[str], fallback: str) -> str:
    for candidate in candidates:
        if candidate in available:
            return candidate
    return fallback


def configure_appearance() -> None:
    """Фиксирует тёмную тему до создания окна."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


def resource_path(relative: Path) -> Path:
    """Путь к ресурсу и при обычном запуске, и внутри сборки PyInstaller."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / relative
    return Path(__file__).resolve().parents[2] / relative


def apply_window_icon(window: tk.Misc) -> None:
    global _icon_reference

    icon = resource_path(_ICON_RELATIVE_PATH)
    if sys.platform == "win32" and icon.exists():
        try:
            window.iconbitmap(str(icon))
            return
        except tk.TclError:
            pass

    logo = resource_path(_LOGO_RELATIVE_PATH)
    if not logo.exists():
        return
    try:
        _icon_reference = tk.PhotoImage(file=str(logo))
        window.iconphoto(True, _icon_reference)
    except tk.TclError:
        _icon_reference = None


def card(parent: tk.Misc, **kwargs) -> ctk.CTkFrame:
    """Панель с рамкой и скруглением - основной строительный блок интерфейса."""
    options = {
        "fg_color": SURFACE,
        "border_color": BORDER,
        "border_width": CARD_BORDER_WIDTH,
        "corner_radius": CORNER_RADIUS,
    }
    options.update(kwargs)
    return ctk.CTkFrame(parent, **options)


def heading(parent: tk.Misc, text: str, fonts: Fonts) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent,
        text=text.upper(),
        font=fonts.ctk(SIZE_TINY, bold=True),
        text_color=TEXT_MUTED,
        anchor="w",
    )


def muted(parent: tk.Misc, text: str, fonts: Fonts, size: int = SIZE_SMALL) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=fonts.ctk(size), text_color=TEXT_MUTED, anchor="w")


def primary_button(parent: tk.Misc, text: str, command, fonts: Fonts, **kwargs) -> ctk.CTkButton:
    options = {
        "text": text,
        "command": command,
        "font": fonts.ctk(SIZE_MEDIUM, bold=True),
        "fg_color": ACCENT,
        "hover_color": ACCENT_HOVER,
        "text_color": BACKGROUND,
        "corner_radius": CORNER_RADIUS,
        "height": 42,
    }
    options.update(kwargs)
    return ctk.CTkButton(parent, **options)


def danger_button(parent: tk.Misc, text: str, command, fonts: Fonts, **kwargs) -> ctk.CTkButton:
    options = {
        "text": text,
        "command": command,
        "font": fonts.ctk(SIZE_MEDIUM, bold=True),
        "fg_color": DANGER,
        "hover_color": DANGER_HOVER,
        "text_color": "#ffffff",
        "corner_radius": CORNER_RADIUS,
        "height": 42,
    }
    options.update(kwargs)
    return ctk.CTkButton(parent, **options)


def ghost_button(parent: tk.Misc, text: str, command, fonts: Fonts, **kwargs) -> ctk.CTkButton:
    options = {
        "text": text,
        "command": command,
        "font": fonts.ctk(SIZE_BASE),
        "fg_color": SURFACE_RAISED,
        "hover_color": BORDER,
        "text_color": TEXT,
        "border_color": BORDER,
        "border_width": 1,
        "corner_radius": CORNER_RADIUS,
        "height": 38,
    }
    options.update(kwargs)
    return ctk.CTkButton(parent, **options)


def entry(parent: tk.Misc, fonts: Fonts, width: int = 90, **kwargs) -> ctk.CTkEntry:
    options = {
        "width": width,
        "height": 36,
        "font": fonts.ctk(SIZE_BASE),
        "fg_color": BACKGROUND,
        "border_color": BORDER,
        "text_color": TEXT,
        "corner_radius": 8,
        "justify": "center",
    }
    options.update(kwargs)
    return ctk.CTkEntry(parent, **options)


__all__ = [
    "ACCENT",
    "ACCENT_HOVER",
    "BACKGROUND",
    "BORDER",
    "CORNER_RADIUS",
    "DANGER",
    "DANGER_HOVER",
    "OK",
    "SIZE_BASE",
    "SIZE_MEDIUM",
    "SIZE_READOUT",
    "SIZE_SMALL",
    "SIZE_TINY",
    "SIZE_TITLE",
    "SURFACE",
    "SURFACE_RAISED",
    "TEXT",
    "TEXT_MUTED",
    "Fonts",
    "apply_window_icon",
    "card",
    "configure_appearance",
    "danger_button",
    "entry",
    "ghost_button",
    "heading",
    "muted",
    "primary_button",
    "resource_path",
]
