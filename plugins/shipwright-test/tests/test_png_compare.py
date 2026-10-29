"""png_compare: the dependency-free metric behind the screenshot check (campaign B3c, D9)."""

import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import png_compare as pc  # noqa: E402
from png_fixtures import blank, dashboard, login, write_png  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")


def test_identical_images_pass_with_zero_ratio(tmp_path):
    a = write_png(tmp_path / "a.png", dashboard())
    r = pc.compare_images(a, a)
    assert (r["status"], r["diff_ratio"]) == ("pass", 0.0)


def test_result_records_metric_and_tolerance(tmp_path):
    a = write_png(tmp_path / "a.png", dashboard())
    r = pc.compare_images(a, a)
    assert r["metric"] == pc.METRIC and r["tolerance"] == pc.TOLERANCE
    assert r["cell_delta"] == pc.CELL_DELTA and r["grid"] == [pc.GRID_W, pc.GRID_H]


def test_small_deviations_stay_inside_the_tolerance(tmp_path):
    approved = write_png(tmp_path / "a.png", dashboard())
    built = write_png(tmp_path / "b.png", dashboard(accent=30, shift=2))
    r = pc.compare_images(approved, built)
    assert r["status"] == "pass" and r["diff_ratio"] < pc.TOLERANCE / 2


@pytest.mark.parametrize("wrong", [login(), blank(), blank(20)], ids=["other-screen", "blank-page", "dark-blank"])
def test_wrong_screens_fail(tmp_path, wrong):
    approved = write_png(tmp_path / "a.png", dashboard())
    r = pc.compare_images(approved, write_png(tmp_path / "b.png", wrong))
    assert r["status"] == "fail" and r["diff_ratio"] > pc.TOLERANCE * 1.5


def test_tolerance_is_a_parameter(tmp_path):
    a = write_png(tmp_path / "a.png", dashboard())
    b = write_png(tmp_path / "b.png", login())
    assert pc.compare_images(a, b, tolerance=1.0)["status"] == "pass"


@pytest.mark.parametrize("ftype", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("ctype", [0, 2, 6])
def test_every_filter_and_color_type_decodes_the_same(tmp_path, ftype, ctype):
    ref = write_png(tmp_path / "ref.png", dashboard())
    other = write_png(tmp_path / "o.png", dashboard(), ftype=ftype, color_type=ctype)
    assert pc.compare_images(ref, other)["diff_ratio"] == 0.0


def test_unreadable_inputs_are_errors_not_exceptions(tmp_path):
    good = write_png(tmp_path / "g.png", dashboard())
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"not a png")
    trunc = tmp_path / "t.png"
    trunc.write_bytes(good.read_bytes()[:60])
    for bad in (junk, trunc, tmp_path / "missing.png"):
        assert pc.compare_images(good, bad)["status"] == "error"


def test_size_mismatch_is_an_error(tmp_path):
    a = write_png(tmp_path / "a.png", dashboard())
    small = write_png(tmp_path / "s.png", [row[:200] for row in dashboard()[:100]])
    r = pc.compare_images(a, small)
    assert r["status"] == "error" and "sizes differ" in r["error"]


def _png(width, height, interlace=0):
    def chunk(k, b):
        return struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, interlace)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\0")) + chunk(b"IEND", b"")


@pytest.mark.parametrize("data", [_png(4, 4, 1), _png(60000, 60000)], ids=["interlaced", "oversized"])
def test_interlaced_and_oversized_png_are_refused(tmp_path, data):
    good = write_png(tmp_path / "g.png", dashboard())
    bad = tmp_path / "bad.png"
    bad.write_bytes(data)
    assert pc.compare_images(good, bad)["status"] == "error"


def test_a_blank_approved_mockup_is_an_error_not_a_pass(tmp_path):
    blank_approved = write_png(tmp_path / "a.png", blank())
    built = write_png(tmp_path / "b.png", dashboard())
    r = pc.compare_images(blank_approved, built)
    assert r["status"] == "error" and "render blank" in r["error"]


def test_a_corrupt_chunk_is_an_error(tmp_path):
    good = write_png(tmp_path / "g.png", dashboard())
    data = bytearray(good.read_bytes())
    data[20] ^= 0xFF  # inside IHDR: the CRC no longer matches
    bad = tmp_path / "bad.png"
    bad.write_bytes(bytes(data))
    r = pc.compare_images(good, bad)
    assert r["status"] == "error" and "CRC" in r["error"]
