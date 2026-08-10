# -*- mode: python ; coding: utf-8 -*-
"""Сборка двух исполняемых файлов WattHog.

* ``WattHog`` - консольная версия с текстовым интерфейсом.
* ``WattHog-GUI`` - оконная версия без консоли.

Оконный интерфейс намеренно исключён из консольной сборки: он тянет за собой
tkinter и customtkinter, а консольной версии они не нужны.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
IS_WINDOWS = sys.platform == "win32"

# Модули, которые тянутся по цепочке зависимостей, но приложению не нужны.
COMMON_EXCLUDES = [
    "unittest",
    "pydoc_data",
    "pytest",
    "_pytest",
    "setuptools",
    "pip",
]
CONSOLE_EXCLUDES = [*COMMON_EXCLUDES, "tkinter", "customtkinter", "darkdetect", "watthog.gui"]

ICON_PATH = os.path.join(ROOT, "assets", "watthog.ico")
GUI_ASSETS = [
    (os.path.join(ROOT, "assets", "watthog.ico"), "assets"),
    (os.path.join(ROOT, "assets", "logo.png"), "assets"),
]

console_analysis = Analysis(
    [os.path.join(ROOT, "watthog", "__main__.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=CONSOLE_EXCLUDES,
    noarchive=False,
    optimize=0,
)

gui_analysis = Analysis(
    [os.path.join(ROOT, "watthog", "gui", "__main__.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[*GUI_ASSETS, *collect_data_files("customtkinter")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=COMMON_EXCLUDES,
    noarchive=False,
    optimize=0,
)

console_pyz = PYZ(console_analysis.pure)
gui_pyz = PYZ(gui_analysis.pure)

console_executable = EXE(
    console_pyz,
    console_analysis.scripts,
    console_analysis.binaries,
    console_analysis.datas,
    [],
    name="WattHog",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if IS_WINDOWS else None,
    version=os.path.join(SPECPATH, "version_info.txt") if IS_WINDOWS else None,
)

gui_executable = EXE(
    gui_pyz,
    gui_analysis.scripts,
    gui_analysis.binaries,
    gui_analysis.datas,
    [],
    name="WattHog-GUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if IS_WINDOWS else None,
    version=os.path.join(SPECPATH, "version_info_gui.txt") if IS_WINDOWS else None,
)
