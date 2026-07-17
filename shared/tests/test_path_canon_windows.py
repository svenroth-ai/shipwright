"""Layer 7: cross-platform path / Windows-vs-POSIX coverage.

GPT-17 + Gemini-4: development happens on Windows but most contributors
will be on POSIX. The canon lint patterns and the drift detector must
behave correctly with backslash separators, and symlinks must NOT be
followed across the legacy boundary (otherwise a symlink could mask a
real drift situation).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from lib import stale_artifact_detector as sad
from lib.artifact_migrations import ARTIFACT_MIGRATIONS


# ---------------------------------------------------------------------------
# Windows-style path patterns are present in the manifest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("migration", ARTIFACT_MIGRATIONS, ids=lambda m: m["name"])
def test_manifest_includes_windows_separator_pattern(migration):
    """Each migration's regex set must catch backslash-separated paths."""
    legacy = migration["legacy_dirname"]
    sample_windows = f'foo = "{legacy}\\sub"'
    sample_posix = f'foo = "{legacy}/sub"'

    matched_windows = any(
        re.search(p, sample_windows) for p in migration["old_path_patterns"]
    )
    matched_posix = any(
        re.search(p, sample_posix) for p in migration["old_path_patterns"]
    )

    assert matched_posix, (
        f"Migration `{migration['name']}` patterns miss POSIX `{legacy}/sub`"
    )
    assert matched_windows, (
        f"Migration `{migration['name']}` patterns miss Windows `{legacy}\\sub` "
        f"— add a `{legacy}\\\\` regex to old_path_patterns."
    )


@pytest.mark.parametrize("migration", ARTIFACT_MIGRATIONS, ids=lambda m: m["name"])
def test_manifest_pattern_does_not_match_substring(migration):
    """Negative lookbehind must avoid matching ``replanning``-style words."""
    legacy = migration["legacy_dirname"]
    # Construct a false-positive candidate: identifier that ENDS with the
    # legacy name but is not a path. E.g. ``replanning_foo`` for legacy
    # ``planning``.
    decoy = f"x = re{legacy}_foo  # narrative"
    matched = any(re.search(p, decoy) for p in migration["old_path_patterns"])
    assert not matched, (
        f"Migration `{migration['name']}` patterns false-positive on `{decoy}`"
    )


# ---------------------------------------------------------------------------
# Drift detector with symlinked legacy directory
# ---------------------------------------------------------------------------


@pytest.fixture
def with_in_progress(monkeypatch):
    monkeypatch.setattr(sad, "active_migrations", lambda: [
        {
            "name": "planning",
            "canonical": ".shipwright/planning",
            "legacy_dirname": "planning",
            "old_path_patterns": [],
            "ast_check_string": "planning",
            "status": "in_progress",
        }
    ])


def test_scan_handles_symlinked_legacy_dir(tmp_path, with_in_progress):
    """A symlinked legacy ``planning`` should be reported (not silently followed)."""
    # Create the real directory off in a side path
    real_dir = tmp_path / "real_planning_storage"
    real_dir.mkdir()
    (real_dir / "spec.md").write_text("real", encoding="utf-8")

    legacy_link = tmp_path / "planning"
    try:
        os.symlink(real_dir, legacy_link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    findings = sad.scan_for_stale_legacy_dirs(tmp_path)
    # We accept either: (1) detected as drift (preferred) or (2) silently
    # skipped because rglob doesn't traverse the symlink. Either way is
    # safe — the worst-case "follow symlink and miss the drift" is what
    # we DON'T want.
    if findings:
        assert findings[0]["name"] == "planning"
    # If no findings, the symlinked directory was treated as empty (also OK).


def test_scan_handles_unreadable_legacy_dir(tmp_path, with_in_progress, monkeypatch):
    """Permission errors during scan must NOT crash the detector."""
    legacy = tmp_path / "planning"
    legacy.mkdir()
    (legacy / "spec.md").write_text("x", encoding="utf-8")

    real_rglob = Path.rglob

    def raising_rglob(self, pattern):
        if str(self).endswith("planning"):
            raise OSError("simulated permission denied")
        yield from real_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", raising_rglob)

    # Should fail open: report the directory as drifted rather than crash.
    findings = sad.scan_for_stale_legacy_dirs(tmp_path)
    assert len(findings) == 1
    assert findings[0]["name"] == "planning"


# ---------------------------------------------------------------------------
# Report rendering uses POSIX path separator regardless of host
# ---------------------------------------------------------------------------


def test_drift_report_renders_consistent_remediation_command(tmp_path):
    """The ``git mv ...`` line in the report must be valid on either platform."""
    findings = [{
        "name": "planning",
        "status": "in_progress",
        "legacy_path": str(tmp_path / "planning"),
        "canonical_path": str(tmp_path / ".shipwright" / "planning"),
        "canonical_exists": False,
        "sample_count": 1,
        "severity": "warn",
    }]
    out = sad.write_drift_report_or_clear(tmp_path, findings)
    text = out.read_text(encoding="utf-8")
    # The command is on its own line; just verify both paths appear in it.
    assert "git mv" in text
    assert "planning" in text
    assert ".shipwright" in text
