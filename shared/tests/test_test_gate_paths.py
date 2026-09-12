"""Tests for the shared path-safety helpers (``_test_gate_paths.py``,
FR-01.06, sub-iterate ``e3-checks-test-security``). No dedicated test file
existed for this module before it was split out of ``_test_gate_extras.py``
(round 5, Tier-3 CI review on PR #748) — its escape/absence distinction was
previously exercised only indirectly through each check's own hardening
tests.
"""

from __future__ import annotations

import pytest

from tools.verifiers._test_gate_paths import _project_file_or_escape, _safe_project_file


def test_genuinely_absent_file_is_reported_as_absent_not_escaped(tmp_path):
    path, escaped = _project_file_or_escape(tmp_path, "does-not-exist.json")
    assert path is None
    assert escaped is False


def test_present_safe_file_is_returned(tmp_path):
    target = tmp_path / "present.json"
    target.write_text("{}")
    path, escaped = _project_file_or_escape(tmp_path, "present.json")
    assert path == target
    assert escaped is False
    assert _safe_project_file(tmp_path, "present.json") == target


def test_dangling_symlink_fails_as_present_but_invalid_not_absent(tmp_path):
    """Tier-3 CI review (PR #748, round 5): a plain `Path.is_file()` check
    returns False for a dangling symlink (the same as genuine absence),
    silently folding "a symlink dirent exists but resolves to nothing" —
    itself the same tamper-signal class as an escaping symlink — into the
    caller's SKIP-on-absence branch instead of FAILing it."""
    link = tmp_path / "dangling.json"
    try:
        link.symlink_to(tmp_path / "target-that-does-not-exist.json")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    path, escaped = _project_file_or_escape(tmp_path, "dangling.json")
    assert path is None
    assert escaped is True
    assert _safe_project_file(tmp_path, "dangling.json") is None


def test_symlink_to_a_directory_fails_as_present_but_invalid(tmp_path):
    """Same class of gap: a symlink resolving to a directory is not a
    regular file either, and must FAIL the same way a dangling one does."""
    target_dir = tmp_path / "a-directory"
    target_dir.mkdir()
    link = tmp_path / "dir-symlink.json"
    try:
        link.symlink_to(target_dir, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    path, escaped = _project_file_or_escape(tmp_path, "dir-symlink.json")
    assert path is None
    assert escaped is True


def test_symlink_escaping_the_project_root_still_fails_as_escaped(tmp_path):
    outside = tmp_path.parent / "outside_test_gate_paths_target.json"
    outside.write_text("{}")
    link = tmp_path / "escaping.json"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    try:
        path, escaped = _project_file_or_escape(tmp_path, "escaping.json")
        assert path is None
        assert escaped is True
    finally:
        outside.unlink(missing_ok=True)
