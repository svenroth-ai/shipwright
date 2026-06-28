"""Tests for the CLAUDE.md content-drift SessionStart hook (`check_drift.py`).

Split out of `test_hooks.py` / `test_drift_triage_emit.py`
(iterate-2026-06-28-drop-timestamp-drift) so the check_drift behaviour lives in
one focused module.

The former *timestamp-drift* detector was removed in that iterate: filesystem
mtime is not a content-staleness signal in a git repo (checkout / branch-switch
/ worktree-creation / release version-bump all reset mtimes), so it fired on
noise. These tests pin the content-drift behaviour and the absence of any
timestamp warning, plus an end-to-end composition test (the `cross_component`
integration coverage).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
HOOKS_DIR = _SHARED_SCRIPTS / "hooks"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

# Load check_drift by path (its hyphen-free module name is fine; the bootstrap
# inside the hook adds shared/scripts to sys.path for `lib.*` / `triage`).
_CHECK_DRIFT_PATH = HOOKS_DIR / "check_drift.py"
_spec = importlib.util.spec_from_file_location("check_drift_for_hook_test", _CHECK_DRIFT_PATH)
assert _spec is not None and _spec.loader is not None
check_drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_drift)

from triage import read_all_items  # noqa: E402


_STRUCTURE_DRIFT_CLAUDE_MD = (
    "# Project\n\n## Structure\n```\nghostdir/    # documented but absent on disk\n```\n"
)


def run_python_hook(script_name: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a Python hook script and return the result."""
    script = HOOKS_DIR / script_name
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")  # F7 marker
    return tmp_path


# --- subprocess behaviour ------------------------------------------------

class TestCheckDriftHook:
    def test_no_warning_without_claude_md(self, tmp_path):
        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_no_timestamp_warning_when_keyfile_newer(self, tmp_path):
        """AC-5: a config file modified more recently than CLAUDE.md must NOT
        produce a drift warning — that was the removed mtime heuristic's noise
        (e.g. a release `version =` bump)."""
        (tmp_path / "CLAUDE.md").write_text("# Project\n")  # no Structure block
        time.sleep(0.1)
        (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.0.2"\n')

        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0
        assert "Timestamp drift" not in result.stdout
        assert "DRIFT WARNING" not in result.stdout
        assert result.stdout.strip() == ""

    def test_content_drift_still_detected(self, tmp_path):
        """Content drift (Structure block vs filesystem) is unchanged: a
        documented-but-absent directory is still surfaced, with no timestamp
        warning leaking in."""
        (tmp_path / "CLAUDE.md").write_text(_STRUCTURE_DRIFT_CLAUDE_MD)

        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0
        assert "DRIFT WARNING" in result.stdout
        assert "Content drift" in result.stdout
        assert "ghostdir" in result.stdout
        assert "Timestamp drift" not in result.stdout

    def test_never_blocks(self, tmp_path):
        """Drift detection should never return non-zero, even when it warns."""
        (tmp_path / "CLAUDE.md").write_text(_STRUCTURE_DRIFT_CLAUDE_MD)

        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0  # Always 0, never blocks

    def test_integration_hook_composes_content_drift_and_retires_timestamp(self, tmp_path):
        """category:integration — end-to-end proof the hook composes with the
        triage store after the timestamp detector's removal.

        One real subprocess run must, together: (a) detect content drift,
        (b) emit a ``:content`` triage item, (c) leave NO timestamp warning,
        and (d) retire a pre-existing legacy ``:timestamp`` triage item via the
        resolve pass — all while exiting 0.
        """
        from triage import append_triage_item_idempotent

        (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text(_STRUCTURE_DRIFT_CLAUDE_MD)

        legacy_id = append_triage_item_idempotent(
            tmp_path, source="drift", severity="medium", kind="maintenance",
            title="Drift: pyproject.toml mtime newer than CLAUDE.md",
            detail="legacy timestamp drift", dedup_key="drift:pyproject.toml:timestamp",
            match_commit=False, window_seconds=None,
        )
        assert legacy_id is not None

        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0
        assert "Content drift" in result.stdout
        assert "ghostdir" in result.stdout
        assert "Timestamp drift" not in result.stdout

        by_id = {it["id"]: it for it in read_all_items(tmp_path)}
        assert by_id[legacy_id]["status"] == "dismissed"
        assert by_id[legacy_id]["statusReason"] == "driftResolved"
        open_content = [
            it for it in by_id.values()
            if it["status"] == "triage" and it["dedupKey"].endswith(":content")
        ]
        assert len(open_content) == 1


# --- producer (function-level) -------------------------------------------

def test_producer_never_emits_timestamp_item(project: Path) -> None:
    """The producer must never create a ``:timestamp`` triage item, and a
    content finding carries the standard drift schema."""
    appended = check_drift._emit_drift_to_triage(
        project,
        content_findings=[
            "CLAUDE.md: 'docs/' exists on disk but not listed in Structure",
        ],
    )
    assert appended == 1
    items = read_all_items(project)
    assert all(not it["dedupKey"].endswith(":timestamp") for it in items)
    for it in items:
        assert it["source"] == "drift"
        assert it["severity"] == "medium"
        assert it["kind"] == "maintenance"
        assert it["suggestedPriority"] == "P2"


def test_producer_retires_legacy_timestamp_item(project: Path) -> None:
    """Migration: a pre-existing open ``:timestamp`` item (written by the old
    detector) is dismissed by the resolve pass on the next run, because the
    producer no longer re-emits it."""
    from triage import append_triage_item_idempotent

    legacy_id = append_triage_item_idempotent(
        project, source="drift", severity="medium", kind="maintenance",
        title="Drift: pyproject.toml mtime newer than CLAUDE.md",
        detail="legacy timestamp drift", dedup_key="drift:pyproject.toml:timestamp",
        match_commit=False, window_seconds=None,
    )
    assert legacy_id is not None

    # A run with no findings at all → the legacy timestamp item clears.
    check_drift._emit_drift_to_triage(project, content_findings=[])
    by_id = {it["id"]: it for it in read_all_items(project)}
    assert by_id[legacy_id]["status"] == "dismissed"
    assert by_id[legacy_id]["statusReason"] == "driftResolved"
