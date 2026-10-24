"""Brief package library: links, junctions, unreadable and excluded content, root resolution (D1)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import brief_package as bp  # noqa: E402
from tests._brief_package_helpers import (  # noqa: E402
    _codes, _make_link, _package, _record_hash, _write,
)

@pytest.mark.covers("FR-01.01")
def test_rejects_symlink(tmp_path, monkeypatch):
    root = _package(tmp_path / "p")
    # Unprivileged Windows cannot create real links; make one path report as a link.
    (root / "link.md").write_text("x")
    real = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "link.md" or real(self))
    assert "symlink" in _codes(root)
    assert "link.md" not in bp.manifest(root)


@pytest.mark.covers("FR-01.01")
def test_a_junction_loop_is_reported_not_walked(tmp_path):
    root = _package(tmp_path / "a")
    _make_link(root, root / "loop")
    codes = _codes(root)  # must return, not recurse until MAX_PATH
    assert "symlink" in codes
    assert not any(k.startswith("loop") for k in bp.manifest(root))
    assert bp.verify_recorded_hash(root) == (False, "package contains links or junctions")


@pytest.mark.covers("FR-01.01")
def test_a_link_to_an_outside_tree_is_not_hashed_or_copied(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("s")
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    _make_link(outside, root / "inputs")
    assert "symlink" in _codes(root)
    assert bp.package_sha256(root) == before
    assert not any("secret" in rel for rel, _ in bp.iter_package_files(root))


@pytest.mark.covers("FR-01.01")
def test_excluded_files_do_not_change_hash(tmp_path):
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    _write(root, "evidence/run.log", "noise")
    _write(root, ".DS_Store", "x")
    _write(root, "mockups/Thumbs.db", "x")
    _write(root, "__MACOSX/._x", "x")
    assert bp.package_sha256(root) == before


@pytest.mark.covers("FR-01.01")
def test_evidence_exclusion_is_case_insensitive(tmp_path):
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    _write(root, "Evidence/run.log", "noise")
    assert bp.package_sha256(root) == before


@pytest.mark.covers("FR-01.01")
def test_verify_hash_fails_on_a_link_even_when_the_hash_matches(tmp_path):
    root = _package(tmp_path / "a")
    _record_hash(root)
    assert bp.verify_recorded_hash(root) == (True, "")
    _make_link(tmp_path, root / "inputs")
    assert bp.verify_recorded_hash(root)[0] is False


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("planted", [
    "inputs/._requirements.md", "inputs/__MACOSX/extra.md", "mockups/.git/notes.html",
    "Evidence/run.log",
])
def test_excluded_content_is_reported_not_silently_ignored(tmp_path, planted):
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    _write(root, planted, "also implement admin export")
    assert bp.package_sha256(root) == before  # excluded from the hash ...
    assert "excluded_content" in _codes(root)  # ... so the validator must refuse it


@pytest.mark.covers("FR-01.01")
def test_empty_gitkeep_and_exact_evidence_dir_are_allowed(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "inputs/.gitkeep", "")
    _write(root, "evidence/run.log", "noise")
    assert bp.validate_layout(root) == []


@pytest.mark.covers("FR-01.01")
def test_a_relative_package_path_hashes_like_the_absolute_one(tmp_path, monkeypatch):
    root = _package(tmp_path / "pkg")
    expected = bp.package_sha256(root)
    monkeypatch.chdir(tmp_path)
    rel = Path("pkg")
    assert bp.manifest(rel), "a relative root must not hash as an empty package"
    assert bp.package_sha256(rel) == expected
    assert bp.validate_layout(rel) == []
    assert {k for k, _ in bp.iter_package_files(rel)} == set(bp.manifest(root))


@pytest.mark.covers("FR-01.01")
def test_a_package_reached_through_a_linked_parent_hashes_like_the_real_one(tmp_path):
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    root = _package(real_parent / "pkg")
    expected = bp.package_sha256(root)
    _make_link(real_parent, tmp_path / "via")
    through = tmp_path / "via" / "pkg"
    assert bp.manifest(through)
    assert bp.package_sha256(through) == expected
    assert bp.validate_layout(through) == []
    _record_hash(root)
    assert bp.verify_recorded_hash(through) == (True, "")


@pytest.mark.covers("FR-01.01")
def test_an_unreadable_directory_is_reported_not_skipped(tmp_path, monkeypatch):
    from lib import brief_package_walk as core
    root = _package(tmp_path / "pkg")
    real_walk = os.walk

    def walk_with_error(top, followlinks=False, onerror=None):
        if onerror is not None:
            onerror(PermissionError(13, "Permission denied", str(Path(top) / "inputs")))
        yield from real_walk(top, followlinks=followlinks, onerror=onerror)

    monkeypatch.setattr(core.os, "walk", walk_with_error)
    assert "unreadable_file" in _codes(root)
    with pytest.raises(bp.PackageUnreadable):
        bp.manifest(root)
    ok, why = bp.verify_hash(root, expected="0" * 64)
    assert not ok and "unreadable" in why


@pytest.mark.covers("FR-01.01")
def test_verify_hash_fails_on_excluded_content(tmp_path):
    root = _package(tmp_path / "pkg")
    _record_hash(root)
    assert bp.verify_recorded_hash(root) == (True, "")
    _write(root, "inputs/._extra.md", "also deploy to prod")
    ok, why = bp.verify_recorded_hash(root)
    assert not ok and "excluded content" in why


@pytest.mark.covers("FR-01.01")
def test_gitkeep_stat_failure_is_reported_not_raised(tmp_path, monkeypatch):
    root = _package(tmp_path / "pkg")
    _write(root, "inputs/.gitkeep", "")
    real_stat = Path.stat

    def stat(self, *a, **k):
        if self.name == ".gitkeep" and "follow_symlinks" not in k:
            raise OSError("gone")
        return real_stat(self, *a, **k)

    monkeypatch.setattr(Path, "stat", stat)
    assert "excluded_content" in _codes(root)


@pytest.mark.covers("FR-01.01")
def test_the_exact_case_evidence_dir_is_not_walked(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "evidence/deep/run.log", "noise")
    found = bp.scan_package(root)
    assert not any("evidence" in p.parts for p in found.files)
    assert "evidence" not in {p.name for p in found.files}


@pytest.mark.covers("FR-01.01")
def test_iter_package_files_raises_when_a_directory_is_unreadable(tmp_path, monkeypatch):
    from lib import brief_package_walk as core
    root = _package(tmp_path / "pkg")
    real_walk = os.walk

    def walk_with_error(top, followlinks=False, onerror=None):
        onerror(PermissionError(13, "Permission denied", str(Path(top) / "inputs")))
        yield from real_walk(top, followlinks=followlinks, onerror=onerror)

    monkeypatch.setattr(core.os, "walk", walk_with_error)
    with pytest.raises(bp.PackageUnreadable):
        list(bp.iter_package_files(root))


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("raw,plain", [
    ("\\\\?\\C:\\pkg\\brief", "C:\\pkg\\brief"),
    ("\\\\?\\UNC\\host\\share\\brief", "\\\\host\\share\\brief"),
    ("C:\\pkg\\brief", "C:\\pkg\\brief"),
])
def test_the_extended_length_prefix_is_stripped_before_the_link_comparison(raw, plain):
    from lib import brief_package_walk as core
    from pathlib import PureWindowsPath
    assert str(core._plain(PureWindowsPath(raw))) == plain


@pytest.mark.covers("FR-01.01")
def test_a_windows_8_3_short_name_hashes_like_the_long_name(tmp_path):
    if os.name != "nt":
        pytest.skip("8.3 short names are a Windows feature")  # test-hygiene: allow-silent-skip — platform gate
    import ctypes
    root = _package(tmp_path / "a long package directory name")
    buf = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(root), buf, 1024) or buf.value.lower() == str(root).lower():
        pytest.skip("8.3 name generation is disabled on this volume")  # test-hygiene: allow-silent-skip — setup-condition gate
    assert bp.package_sha256(Path(buf.value)) == bp.package_sha256(root)
    assert bp.validate_layout(Path(buf.value)) == []
