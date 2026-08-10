"""Снимок окна WattHog для документации.

Скрипт открывает оконный интерфейс, проводит короткий настоящий замер и
сохраняет окно в PNG. Захват идёт через PrintWindow с флагом
``PW_RENDERFULLCONTENT``: обычный BitBlt отдаёт чёрный прямоугольник, если окно
рисуется через композитор рабочего стола.

Работает только в Windows: на других системах штатного способа снять окно
без внешних зависимостей нет.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pngwriter import write_png  # noqa: E402

from watthog.gui.app import WattHogWindow  # noqa: E402
from watthog.gui.dialogs import DonateDialog, SettingsDialog  # noqa: E402
from watthog.gui.theme import configure_appearance  # noqa: E402

MEASUREMENT_SECONDS = 30
SETTLE_SECONDS = 1.2
_PW_RENDERFULLCONTENT = 0x00000002
_BI_RGB = 0
_DIB_RGB_COLORS = 0


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BitmapInfoHeader), ("bmiColors", wintypes.DWORD * 3)]


def capture_window(handle: int) -> tuple[list[bytes], int, int]:
    """Содержимое окна в виде строк RGBA."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(handle), ctypes.byref(rect)):
        raise OSError("GetWindowRect не смог определить размеры окна")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise OSError(f"некорректный размер окна: {width}x{height}")

    window_dc = user32.GetWindowDC(wintypes.HWND(handle))
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(wintypes.HWND(handle), memory_dc, _PW_RENDERFULLCONTENT):
            raise OSError("PrintWindow не смог отрисовать окно")

        info = _BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(_BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        # Отрицательная высота разворачивает изображение в привычный порядок
        # строк: сверху вниз, как ждёт PNG.
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = _BI_RGB

        buffer = ctypes.create_string_buffer(width * height * 4)
        copied = gdi32.GetDIBits(
            memory_dc, bitmap, 0, height, buffer, ctypes.byref(info), _DIB_RGB_COLORS
        )
        if copied != height:
            raise OSError(f"GetDIBits вернул {copied} строк из {height}")
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(wintypes.HWND(handle), window_dc)

    return _to_rgba_rows(buffer.raw, width, height), width, height


def _to_rgba_rows(raw: bytes, width: int, height: int) -> list[bytes]:
    rows = []
    stride = width * 4
    for y in range(height):
        line = bytearray(stride)
        offset = y * stride
        for x in range(0, stride, 4):
            blue, green, red = raw[offset + x], raw[offset + x + 1], raw[offset + x + 2]
            line[x] = red
            line[x + 1] = green
            line[x + 2] = blue
            line[x + 3] = 255
        rows.append(bytes(line))
    return rows


def pump(window: WattHogWindow, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        window.update()
        time.sleep(0.02)


def main() -> int:
    if sys.platform != "win32":
        print("Снимок окна умеет делать только сборка для Windows.", file=sys.stderr)
        return 2

    output = Path(__file__).resolve().parents[1] / "docs"
    output.mkdir(parents=True, exist_ok=True)

    configure_appearance()
    window = WattHogWindow()
    window._duration_input.delete(0, "end")
    window._duration_input.insert(0, str(MEASUREMENT_SECONDS))
    window.update()
    window.lift()
    window.focus_force()

    print(f"замер {MEASUREMENT_SECONDS} с...")
    window._start()
    deadline = time.monotonic() + MEASUREMENT_SECONDS + 20
    while time.monotonic() < deadline and window._result is None:
        window.update()
        time.sleep(0.02)

    if window._result is None:
        print("замер не завершился", file=sys.stderr)
        window.destroy()
        return 1

    pump(window, SETTLE_SECONDS)
    _capture_to(window.winfo_id(), output / "gui.png")

    dialog = DonateDialog(window, window._fonts)
    pump(window, SETTLE_SECONDS)
    _capture_to(dialog.winfo_id(), output / "gui-donate.png")
    dialog.destroy()

    settings = SettingsDialog(window, window._fonts, window._settings, lambda _settings: None)
    pump(window, SETTLE_SECONDS)
    _capture_to(settings.winfo_id(), output / "gui-settings.png")
    settings.destroy()

    window.destroy()
    return 0


def _capture_to(handle: int, target: Path) -> None:
    rows, width, height = capture_window(handle)
    write_png(target, rows, width, height)
    print(f"{target.name}: {width}x{height}, {target.stat().st_size} байт")


if __name__ == "__main__":
    sys.exit(main())
