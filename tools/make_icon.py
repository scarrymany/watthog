"""Генерация иконки приложения без внешних зависимостей.

Рисует логотип (молния на скруглённом тёмном квадрате) в память, затем
собирает многоразмерный ICO из DIB-изображений и отдельный PNG для README.
Всё делается стандартной библиотекой: Pillow в сборке не нужен.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pngwriter import write_png  # noqa: E402

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
LOGO_PNG_SIZE = 256

BACKGROUND = (22, 27, 34, 255)
BOLT = (255, 210, 63, 255)
CORNER_RADIUS_RATIO = 0.22
SUPERSAMPLE = 3

# Контур молнии в долях от стороны иконки.
BOLT_OUTLINE = (
    (0.60, 0.06),
    (0.24, 0.55),
    (0.45, 0.55),
    (0.39, 0.94),
    (0.76, 0.45),
    (0.55, 0.45),
)


def _point_in_polygon(x: float, y: float, polygon: tuple[tuple[float, float], ...]) -> bool:
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if (y1 > y) != (y2 > y):
            crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing_x:
                inside = not inside
    return inside


def _inside_rounded_square(x: float, y: float, radius: float) -> bool:
    if radius <= 0.0:
        return True
    near_x = min(max(x, radius), 1.0 - radius)
    near_y = min(max(y, radius), 1.0 - radius)
    dx, dy = x - near_x, y - near_y
    return dx * dx + dy * dy <= radius * radius


def _blend(bottom: tuple[int, int, int, int], top: tuple[int, int, int, int], alpha: float) -> tuple[int, ...]:
    return tuple(round(bottom[channel] * (1.0 - alpha) + top[channel] * alpha) for channel in range(4))


def render_rgba(size: int) -> list[bytes]:
    """Строки изображения в формате RGBA со сглаживанием краёв."""
    rows: list[bytes] = []
    samples = SUPERSAMPLE * SUPERSAMPLE
    for pixel_y in range(size):
        row = bytearray()
        for pixel_x in range(size):
            background_hits = 0
            bolt_hits = 0
            for sub_y in range(SUPERSAMPLE):
                for sub_x in range(SUPERSAMPLE):
                    x = (pixel_x + (sub_x + 0.5) / SUPERSAMPLE) / size
                    y = (pixel_y + (sub_y + 0.5) / SUPERSAMPLE) / size
                    if _inside_rounded_square(x, y, CORNER_RADIUS_RATIO):
                        background_hits += 1
                        if _point_in_polygon(x, y, BOLT_OUTLINE):
                            bolt_hits += 1

            if background_hits == 0:
                row.extend((0, 0, 0, 0))
                continue

            base = (BACKGROUND[0], BACKGROUND[1], BACKGROUND[2], round(255 * background_hits / samples))
            pixel = _blend(base, BOLT, bolt_hits / samples) if bolt_hits else base
            row.extend(pixel)
        rows.append(bytes(row))
    return rows


def _dib_image(rows: list[bytes], size: int) -> bytes:
    """Изображение в формате DIB для контейнера ICO: BGRA, строки снизу вверх."""
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, size * size * 4, 0, 0, 0, 0)
    pixels = bytearray()
    for row in reversed(rows):
        for offset in range(0, len(row), 4):
            red, green, blue, alpha = row[offset : offset + 4]
            pixels.extend((blue, green, red, alpha))

    # Маска прозрачности обязательна по формату, но для 32-битных иконок
    # Windows использует альфа-канал, поэтому маска пустая.
    mask_row_bytes = ((size + 31) // 32) * 4
    return bytes(header) + bytes(pixels) + b"\x00" * (mask_row_bytes * size)


def write_ico(path: Path, sizes: tuple[int, ...]) -> None:
    images = [(size, _dib_image(render_rgba(size), size)) for size in sizes]
    offset = 6 + 16 * len(images)

    directory = struct.pack("<HHH", 0, 1, len(images))
    entries = bytearray()
    for size, payload in images:
        dimension = 0 if size >= 256 else size
        entries.extend(struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(payload), offset))
        offset += len(payload)

    path.write_bytes(directory + bytes(entries) + b"".join(payload for _, payload in images))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    icon_path = assets / "watthog.ico"
    write_ico(icon_path, ICON_SIZES)
    print(f"иконка: {icon_path} ({icon_path.stat().st_size} байт)")

    logo_path = assets / "logo.png"
    write_png(logo_path, render_rgba(LOGO_PNG_SIZE), LOGO_PNG_SIZE, LOGO_PNG_SIZE)
    print(f"логотип: {logo_path} ({logo_path.stat().st_size} байт)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
