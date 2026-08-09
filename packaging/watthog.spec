# -*- mode: python ; coding: utf-8 -*-
"""Сборка одного исполняемого файла WattHog."""

import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
IS_WINDOWS = sys.platform == "win32"

# Модули, которые тянутся в сборку по цепочке зависимостей, но приложению
# не нужны и только раздувают файл.
EXCLUDED_MODULES = [
    "tkinter",
    "unittest",
    "pydoc_data",
    "pytest",
    "_pytest",
    "setuptools",
    "pip",
]

analysis = Analysis(
    [os.path.join(ROOT, "watthog", "__main__.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
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
    icon=os.path.join(ROOT, "assets", "watthog.ico") if IS_WINDOWS else None,
    version=os.path.join(SPECPATH, "version_info.txt") if IS_WINDOWS else None,
)
