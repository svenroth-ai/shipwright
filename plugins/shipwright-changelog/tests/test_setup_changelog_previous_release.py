"""Tests for `_check_previous_release` in `checks/setup-changelog.py` — the
advisory (never-blocking) tri-state check for whether the immediately
preceding tag has a GitHub Release, surfaced as a Step 1 notice.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "checks" / "setup-changelog.py"
_spec = importlib.util.spec_from_file_location("setup_changelog", _SCRIPT_PATH)
setup_changelog = importlib.util.module_from_spec(_spec)
sys.modules["setup_changelog"] = setup_changelog
_spec.loader.exec_module(setup_changelog)  # noqa: E402


def _completed(returncode: int, stderr: str = "", stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_no_previous_tag_is_not_applicable(tmp_path: Path):
    assert setup_changelog._check_previous_release(tmp_path, None) is None


def test_gh_missing_is_indeterminate(tmp_path: Path):
    with patch("setup_changelog.subprocess.run", side_effect=OSError("not found")):
        assert setup_changelog._check_previous_release(tmp_path, "v1.0.0") is None


def test_release_found_is_true(tmp_path: Path):
    with patch("setup_changelog.subprocess.run", return_value=_completed(0)) as mock_run, \
         patch("setup_changelog.resolve_repo_identity", return_value="acme/widgets"):
        mock_run.side_effect = [_completed(0), _completed(0, stdout='{"url": "https://x"}')]
        assert setup_changelog._check_previous_release(tmp_path, "v1.0.0") is True


def test_release_not_found_is_false(tmp_path: Path):
    with patch("setup_changelog.subprocess.run") as mock_run, \
         patch("setup_changelog.resolve_repo_identity", return_value="acme/widgets"):
        mock_run.side_effect = [_completed(0), _completed(1, stderr="release not found")]
        assert setup_changelog._check_previous_release(tmp_path, "v1.0.0") is False


def test_indeterminate_gh_failure_is_none(tmp_path: Path):
    with patch("setup_changelog.subprocess.run") as mock_run, \
         patch("setup_changelog.resolve_repo_identity", return_value="acme/widgets"):
        mock_run.side_effect = [_completed(0), _completed(1, stderr="network error")]
        assert setup_changelog._check_previous_release(tmp_path, "v1.0.0") is None


def test_unresolved_repo_identity_is_none(tmp_path: Path):
    with patch("setup_changelog.subprocess.run", return_value=_completed(0)), \
         patch("setup_changelog.resolve_repo_identity", return_value=None):
        assert setup_changelog._check_previous_release(tmp_path, "v1.0.0") is None


def test_gh_version_nonzero_exit_is_indeterminate(tmp_path: Path):
    with patch("setup_changelog.subprocess.run", return_value=_completed(1)):
        assert setup_changelog._check_previous_release(tmp_path, "v1.0.0") is None


def test_gh_release_view_raising_is_indeterminate(tmp_path: Path):
    with patch("setup_changelog.subprocess.run") as mock_run, \
         patch("setup_changelog.resolve_repo_identity", return_value="acme/widgets"):
        mock_run.side_effect = [_completed(0), OSError("gh crashed")]
        assert setup_changelog._check_previous_release(tmp_path, "v1.0.0") is None
