"""Tiny PNG writer + page 'drawings' for the screenshot-check tests (no third-party dependency)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

W, H = 320, 200


def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def _filtered(rows: list[bytes], bpp: int, ftype: int) -> bytes:
    out, prev = bytearray(), bytes(len(rows[0]))
    for row in rows:
        out.append(ftype)
        for i, v in enumerate(row):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            paeth = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            pred = {0: 0, 1: a, 2: b, 3: (a + b) >> 1, 4: paeth}[ftype]
            out.append((v - pred) & 255)
        prev = row
    return bytes(out)


def write_png(path: Path, pixels: list[list[int]], ftype: int = 0, color_type: int = 2) -> Path:
    """``pixels[y][x]`` = gray 0..255; written as gray (0), RGB (2) or RGBA (6)."""
    ch = {0: 1, 2: 3, 6: 4}[color_type]
    rows = [b"".join(bytes([v] * 3 + ([255] if ch == 4 else [])) if ch > 1 else bytes([v]) for v in line) for line in pixels]
    ihdr = struct.pack(">IIBBBBB", len(pixels[0]), len(pixels), 8, color_type, 0, 0, 0)
    data = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(_filtered(rows, ch, ftype))) + _chunk(b"IEND", b""))
    path.write_bytes(data)
    return path


def blank(bg: int = 248) -> list[list[int]]:
    return [[bg] * W for _ in range(H)]


def box(px: list[list[int]], x0: int, y0: int, x1: int, y1: int, fill: int, border: int = 120) -> None:
    for y in range(y0, y1):
        for x in range(x0, x1):
            edge = x in (x0, x1 - 1) or y in (y0, y1 - 1)
            px[y][x] = border if edge else fill


def dashboard(accent: int = 60, shift: int = 0) -> list[list[int]]:
    """Sidebar + three stat cards + a table card; ``accent`` / ``shift`` are harmless 'built app' deviations."""
    px = blank()
    box(px, 0, 0, 60, H, 255)
    for i in range(3):
        box(px, 70 + i * 82 + shift, 14, 70 + i * 82 + 76, 54, 255)
        for x in range(80 + i * 82, 100 + i * 82):
            px[30][x] = accent
    box(px, 70, 64, W - 8, H - 8, 255)
    for r in range(5):
        for x in range(80, 200):
            px[84 + r * 20][x] = accent
    return px


def login() -> list[list[int]]:
    px = [[20] * W for _ in range(H)]
    box(px, 100, 40, 220, 160, 40, border=200)
    for y in (70, 100):
        box(px, 110, y, 210, y + 18, 90, border=220)
    return px
