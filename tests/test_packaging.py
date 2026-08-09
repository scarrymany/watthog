"""Проверки упаковки и установочных скриптов.

Ошибки в этих файлах не ловятся обычными тестами, а ломают установку у всех
пользователей сразу, поэтому проверяются отдельно.
"""

from pathlib import Path

import pytest

from watthog import __version__

ROOT = Path(__file__).resolve().parents[1]
UTF8_BOM = b"\xef\xbb\xbf"


def read_bytes(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


def test_windows_installer_starts_with_utf8_bom():
    # Windows PowerShell 5.1 читает .ps1 без BOM в системной кодировке и
    # спотыкается на кириллице ещё на этапе разбора скрипта.
    assert read_bytes("install.ps1").startswith(UTF8_BOM)


def test_linux_installer_has_no_bom_and_uses_lf():
    payload = read_bytes("install.sh")
    # BOM перед shebang не даст ядру найти интерпретатор.
    assert not payload.startswith(UTF8_BOM)
    assert payload.startswith(b"#!/usr/bin/env bash")
    assert b"\r\n" not in payload


def test_linux_installer_rejects_macos():
    assert "Darwin" in (ROOT / "install.sh").read_text(encoding="utf-8")


@pytest.mark.parametrize("script", ["install.ps1", "install.sh"])
def test_installers_point_at_the_real_repository(script):
    text = (ROOT / script).read_text(encoding="utf-8-sig")
    assert "scarrymany/watthog" in text


def test_version_is_consistent_across_project_files():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version_info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f'version = "{__version__}"' in pyproject
    assert f"'FileVersion', '{__version__}'" in version_info
    assert f"[{__version__}]" in changelog


def test_icon_exists_and_is_a_valid_ico():
    payload = read_bytes("assets/watthog.ico")
    # Заголовок ICONDIR: два нулевых байта, тип 1, затем число изображений.
    assert payload[:4] == b"\x00\x00\x01\x00"
    assert int.from_bytes(payload[4:6], "little") > 0


def test_pyinstaller_spec_references_the_entry_point():
    spec = (ROOT / "packaging" / "watthog.spec").read_text(encoding="utf-8")
    assert "__main__.py" in spec
    assert 'name="WattHog"' in spec
