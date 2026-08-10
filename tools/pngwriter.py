"""Минимальная запись PNG стандартной библиотекой.

Нужна инструментам сборки иконки и снимков экрана, чтобы не тянуть Pillow
в зависимости разработки.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_COLOR_TYPE_RGBA = 6
_BIT_DEPTH = 8


def write_png(path: Path, rows: list[bytes], width: int, height: int) -> None:
    """Сохраняет изображение RGBA: по четыре байта на пиксель, строка за строкой."""
    expected = width * 4
    for index, row in enumerate(rows):
        if len(row) != expected:
            raise ValueError(f"строка {index}: ожидалось {expected} байт, получено {len(row)}")

    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", width, height, _BIT_DEPTH, _COLOR_TYPE_RGBA, 0, 0, 0)
    payload = b"".join(
        _chunk(name, data)
        for name, data in ((b"IHDR", header), (b"IDAT", zlib.compress(raw, 9)), (b"IEND", b""))
    )
    path.write_bytes(_PNG_SIGNATURE + payload)


def _chunk(name: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
