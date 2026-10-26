"""Dependency-free screenshot comparison for the Test-phase screenshot check (campaign B3c, D9).

The plugin ships with no third-party Python dependency, so this decodes the PNGs Playwright
writes (8-bit, non-interlaced) with ``zlib`` only.

THE METRIC (recorded in every result, see ``METRIC``):

* each image is reduced to a ``GRID_W x GRID_H`` grid: per cell the mean luminance (0..1) and
  whether the cell has content (edges) -- a layout picture of the page, blind to anti-aliasing and
  to what the text says;
* a grid cell DIFFERS when its content flag differs OR its luminances differ by more than ``CELL_DELTA``;
* ``diff_ratio`` = differing cells / all cells. A screen PASSES when ``diff_ratio <= TOLERANCE``.

Two guards are not part of the ratio: a blank APPROVED mockup is an ``error`` (nothing to compare against) and a
blank BUILT screen is a ``fail`` (a sparse mockup could otherwise hide it under the tolerance). One rule, no per-screen special cases. ``TOLERANCE`` is a first calibration (the run_to_green
procedure tunes it); it lives in ONE place and is printed with every result.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

GRID_W = 32
GRID_H = 20
CELL_DELTA = 0.10
EDGE_STEP = 0.04
OCCUPIED_SHARE = 0.002
TOLERANCE = 0.15
METRIC = "grid-luma-occupancy-diff-ratio"

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
_MAX_PIXELS = 4096 * 4096  # a screenshot is a viewport; refuse a decompression bomb
_MAX_CHUNK = 64 * 1024 * 1024


class PngError(ValueError):
    """The file is not a PNG this module can read."""


def _chunks(data: bytes):
    pos = len(_SIGNATURE)
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if length > _MAX_CHUNK or pos + 12 + length > len(data):
            raise PngError("truncated or oversized PNG chunk")
        body = data[pos + 8:pos + 8 + length]
        if struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0] != zlib.crc32(kind + body):
            raise PngError(f"corrupt PNG chunk {kind!r} (CRC mismatch)")
        yield kind, body
        pos += 12 + length
        if kind == b"IEND":
            return


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> list[bytearray]:
    rows: list[bytearray] = []
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ftype = raw[pos]
        cur = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ftype == 1:
            for i in range(bpp, stride):
                cur[i] = (cur[i] + cur[i - bpp]) & 255
        elif ftype == 2:
            for i in range(stride):
                cur[i] = (cur[i] + prev[i]) & 255
        elif ftype == 3:
            for i in range(stride):
                left = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                cur[i] = (cur[i] + pred) & 255
        elif ftype != 0:
            raise PngError(f"unknown PNG filter type {ftype}")
        rows.append(cur)
        prev = cur
    return rows


def decode_luma(path: Path) -> tuple[int, int, list[list[float]]]:
    """``(width, height, rows)`` of per-pixel luminance 0..1."""
    data = Path(path).read_bytes()
    if not data.startswith(_SIGNATURE):
        raise PngError(f"{path}: not a PNG")
    header, idat = None, bytearray()
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
    if header is None or not idat:
        raise PngError(f"{path}: missing IHDR or IDAT")
    width, height, depth, ctype, _comp, _flt, interlace = header
    if depth != 8 or ctype not in _CHANNELS or interlace != 0:
        raise PngError(f"{path}: only 8-bit non-interlaced gray/RGB(A) PNG is supported")
    if width * height > _MAX_PIXELS or width < 1 or height < 1:
        raise PngError(f"{path}: implausible image size {width}x{height}")
    ch = _CHANNELS[ctype]
    stride = width * ch
    raw = zlib.decompressobj().decompress(bytes(idat), (stride + 1) * height + 1)
    if len(raw) < (stride + 1) * height:
        raise PngError(f"{path}: truncated image data")
    rows = _unfilter(raw, height, stride, ch)
    out: list[list[float]] = []
    for r in rows:
        if ch >= 3:
            out.append([(0.2126 * r[x] + 0.7152 * r[x + 1] + 0.0722 * r[x + 2]) / 255 for x in range(0, stride, ch)])
        else:
            out.append([r[x] / 255 for x in range(0, stride, ch)])
    return width, height, out


def cell_grids(path: Path) -> tuple[tuple[int, int], list[float], list[bool]]:
    """``((w, h), mean luminance per cell, 'has content' per cell)`` over a GRID_W x GRID_H grid.

    A cell has content when at least ``OCCUPIED_SHARE`` of its pixels sit on an edge (a neighbour
    luminance step above ``EDGE_STEP``): text, borders, controls. A blank page or an error page has
    none, whatever its background colour.
    """
    width, height, rows = decode_luma(path)
    n = GRID_W * GRID_H
    sums, edges, counts = [0.0] * n, [0] * n, [0] * n
    for y, row in enumerate(rows):
        below = rows[y + 1] if y + 1 < height else row
        base = (y * GRID_H // height) * GRID_W
        for x, v in enumerate(row):
            i = base + x * GRID_W // width
            sums[i] += v
            counts[i] += 1
            if abs(v - row[x + 1 if x + 1 < width else x]) > EDGE_STEP or abs(v - below[x]) > EDGE_STEP:
                edges[i] += 1
    lum = [s / c if c else 0.0 for s, c in zip(sums, counts)]
    return (width, height), lum, [c > 0 and e / c >= OCCUPIED_SHARE for e, c in zip(edges, counts)]


def compare_images(approved: Path, built: Path, tolerance: float = TOLERANCE) -> dict:
    """Compare two screenshots of the SAME viewport size; never raises for an unreadable file."""
    try:
        size_a, lum_a, occ_a = cell_grids(approved)
        size_b, lum_b, occ_b = cell_grids(built)
    except (PngError, OSError, zlib.error, struct.error, IndexError) as exc:
        return {"status": "error", "error": f"cannot read screenshot: {exc}"}
    base = {"metric": METRIC, "tolerance": tolerance, "cell_delta": CELL_DELTA, "grid": [GRID_W, GRID_H]}
    if size_a != size_b:
        return {**base, "status": "error", "error": f"screenshot sizes differ: approved {size_a}, built {size_b}"}
    if not any(occ_a):
        return {**base, "status": "error", "error": "the approved mockup renders blank (no content): it cannot be compared"}
    if not any(occ_b):
        return {**base, "status": "fail", "diff_ratio": 1.0, "error": "the built screen renders blank (no content)"}
    differing = sum(1 for a, b, oa, ob in zip(lum_a, lum_b, occ_a, occ_b) if oa != ob or abs(a - b) > CELL_DELTA)
    ratio = differing / len(lum_a)
    return {**base, "status": "pass" if ratio <= tolerance else "fail", "diff_ratio": round(ratio, 4)}
