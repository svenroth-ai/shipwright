"""Tests for `create_github_release.py` — the best-effort `gh` wrapper.

`subprocess.run` is always mocked here — this repo's convention is to never
invoke a real producer (here: a real `gh release create`) to verify it; a
real call would try to publish to GitHub from a test run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from tools import create_github_release as cgr  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_skips_when_gh_not_found(tmp_path: Path):
    with patch.object(cgr, "_gh_version", return_value=None):
        result = cgr.create_release("1.2.3", tmp_path / "notes.md", tmp_path)
    assert result == {"status": "skipped", "reason": "gh_not_found"}


def test_skips_when_gh_version_too_old(tmp_path: Path):
    with patch.object(cgr, "_gh_version", return_value=(2, 40, 0)):
        result = cgr.create_release("1.2.3", tmp_path / "notes.md", tmp_path)
    assert result == {"status": "skipped", "reason": "unsupported_gh_version:2.40.0"}


def test_skips_when_unauthenticated(tmp_path: Path):
    with patch.object(cgr, "_gh_version", return_value=(2, 60, 0)), \
         patch.object(cgr, "_gh_authenticated", return_value=False):
        result = cgr.create_release("1.2.3", tmp_path / "notes.md", tmp_path)
    assert result == {"status": "skipped", "reason": "gh_unauthenticated"}


def test_rejects_invalid_version(tmp_path: Path):
    with patch.object(cgr, "_gh_version", return_value=(2, 60, 0)), \
         patch.object(cgr, "_gh_authenticated", return_value=True):
        result = cgr.create_release("--not-a-version", tmp_path / "notes.md", tmp_path)
    assert result["status"] == "failed"
    assert "invalid version" in result["reason"]


def test_skips_when_repo_identity_unresolved(tmp_path: Path):
    with patch.object(cgr, "_gh_version", return_value=(2, 60, 0)), \
         patch.object(cgr, "_gh_authenticated", return_value=True), \
         patch("tools.create_github_release.resolve_repo_identity", return_value=None):
        result = cgr.create_release("1.2.3", tmp_path / "notes.md", tmp_path)
    assert result == {"status": "skipped", "reason": "repo_identity_unresolved"}


def test_run_survives_a_non_utf8_stdout_byte():
    """Same Windows cp1252-decode crash as `extract_changelog_section._git`
    (a `gh` release title/body can legitimately carry non-ASCII) — `_run`
    must not let a locale-undecodable byte turn `stdout` into `None`."""
    result = cgr._run([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\x8f')"])
    assert result.returncode == 0
    assert result.stdout is not None
    assert "�" in result.stdout


def test_reports_exists_without_creating(tmp_path: Path):
    with patch.object(cgr, "_gh_version", return_value=(2, 60, 0)), \
         patch.object(cgr, "_gh_authenticated", return_value=True), \
         patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"), \
         patch.object(cgr, "_run") as mock_run:
        mock_run.return_value = _completed(
            0, stdout='{"url":"https://github.com/acme/widgets/releases/v1.2.3"}'
        )
        result = cgr.create_release("1.2.3", tmp_path / "notes.md", tmp_path)
    assert result["status"] == "exists"
    assert mock_run.call_count == 1  # only the view call — create never attempted


def test_view_failure_reports_failed_not_create(tmp_path: Path):
    with patch.object(cgr, "_gh_version", return_value=(2, 60, 0)), \
         patch.object(cgr, "_gh_authenticated", return_value=True), \
         patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"), \
         patch.object(cgr, "_run") as mock_run:
        mock_run.return_value = _completed(1, stderr="network is unreachable")
        result = cgr.create_release("1.2.3", tmp_path / "notes.md", tmp_path)
    assert result["status"] == "failed"
    assert "release_view_failed" in result["reason"]
    assert mock_run.call_count == 1  # never falls through to create


def test_success_argv_shape(tmp_path: Path):
    notes_file = tmp_path / "notes.md"
    notes_file.write_text("body", encoding="utf-8")

    def _side_effect(args, **kwargs):
        if args[:3] == ["gh", "release", "view"]:
            return _completed(1, stderr="release not found")
        if args[:3] == ["gh", "release", "create"]:
            return _completed(0, stdout="https://github.com/acme/widgets/releases/v1.2.3\n")
        raise AssertionError(f"unexpected argv: {args}")

    with patch.object(cgr, "_gh_version", return_value=(2, 60, 0)), \
         patch.object(cgr, "_gh_authenticated", return_value=True), \
         patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"), \
         patch.object(cgr, "_run", side_effect=_side_effect) as mock_run:
        result = cgr.create_release("1.2.3", notes_file, tmp_path)

    assert result == {"status": "ok", "url": "https://github.com/acme/widgets/releases/v1.2.3"}
    create_call = mock_run.call_args_list[-1]
    argv = create_call.args[0]
    assert "--verify-tag" in argv
    assert "--repo" in argv and "acme/widgets" in argv
    assert "v1.2.3" in argv  # version lands as ONE safe argv element
    allowed_flags = {"--notes-file", "--title", "--verify-tag", "--repo"}
    assert not any(a.startswith("-") and a not in allowed_flags for a in argv)


def test_gh_version_parses_real_output():
    with patch.object(cgr, "_run", return_value=_completed(0, stdout="gh version 2.62.0 (2024-01-01)\n")):
        assert cgr._gh_version() == (2, 62, 0)


def test_gh_version_none_when_output_unparseable():
    with patch.object(cgr, "_run", return_value=_completed(0, stdout="not a version string")):
        assert cgr._gh_version() is None


def test_gh_version_none_on_nonzero_exit():
    with patch.object(cgr, "_run", return_value=_completed(1)):
        assert cgr._gh_version() is None


def test_gh_version_none_when_run_raises():
    with patch.object(cgr, "_run", side_effect=OSError("gh not found")):
        assert cgr._gh_version() is None


def test_gh_authenticated_true_and_false():
    with patch.object(cgr, "_run", return_value=_completed(0)):
        assert cgr._gh_authenticated() is True
    with patch.object(cgr, "_run", return_value=_completed(1)):
        assert cgr._gh_authenticated() is False


def test_gh_authenticated_false_when_run_raises():
    with patch.object(cgr, "_run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30)):
        assert cgr._gh_authenticated() is False


def test_release_view_indeterminate_when_run_raises():
    with patch.object(cgr, "_run", side_effect=OSError("boom")):
        result = cgr._release_view("v1.2.3", "acme/widgets")
    assert result["exists"] is None
    assert "failed to run" in result["reason"]


def test_release_view_tolerates_non_json_stdout():
    with patch.object(cgr, "_run", return_value=_completed(0, stdout="not json")):
        result = cgr._release_view("v1.2.3", "acme/widgets")
    assert result == {"exists": True, "url": None}


def test_missing_notes_file_reports_failed(tmp_path: Path):
    with patch.object(cgr, "_gh_version", return_value=(2, 60, 0)), \
         patch.object(cgr, "_gh_authenticated", return_value=True), \
         patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"), \
         patch.object(cgr, "_run") as mock_run:
        mock_run.return_value = _completed(1, stderr="release not found")
        result = cgr.create_release("1.2.3", tmp_path / "does-not-exist.md", tmp_path)
    assert result["status"] == "failed"
    assert "notes file not found" in result["reason"]


def test_create_call_raises_reports_failed(tmp_path: Path):
    notes_file = tmp_path / "notes.md"
    notes_file.write_text("body", encoding="utf-8")

    def _side_effect(args, **kwargs):
        if args[:3] == ["gh", "release", "view"]:
            return _completed(1, stderr="release not found")
        raise subprocess.TimeoutExpired(cmd=args, timeout=60)

    with patch.object(cgr, "_gh_version", return_value=(2, 60, 0)), \
         patch.object(cgr, "_gh_authenticated", return_value=True), \
         patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"), \
         patch.object(cgr, "_run", side_effect=_side_effect):
        result = cgr.create_release("1.2.3", notes_file, tmp_path)
    assert result["status"] == "failed"
    assert "gh release create failed to run" in result["reason"]


def test_main_prints_json_result(tmp_path: Path, capsys):
    notes_file = tmp_path / "notes.md"
    notes_file.write_text("body", encoding="utf-8")
    with patch.object(cgr, "_gh_version", return_value=None):
        rc = cgr.main([
            "--project-root", str(tmp_path),
            "--version", "1.2.3",
            "--notes-file", str(notes_file),
        ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"status": "skipped", "reason": "gh_not_found"}


def test_create_failure_reported(tmp_path: Path):
    notes_file = tmp_path / "notes.md"
    notes_file.write_text("body", encoding="utf-8")

    def _side_effect(args, **kwargs):
        if args[:3] == ["gh", "release", "view"]:
            return _completed(1, stderr="release not found")
        return _completed(1, stderr="422 Unprocessable Entity")

    with patch.object(cgr, "_gh_version", return_value=(2, 60, 0)), \
         patch.object(cgr, "_gh_authenticated", return_value=True), \
         patch("tools.create_github_release.resolve_repo_identity", return_value="acme/widgets"), \
         patch.object(cgr, "_run", side_effect=_side_effect):
        result = cgr.create_release("1.2.3", notes_file, tmp_path)

    assert result["status"] == "failed"
    assert "422" in result["reason"]
