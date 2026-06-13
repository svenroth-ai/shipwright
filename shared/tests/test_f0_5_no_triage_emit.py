"""Regression: the F0.5 surface-verification gate STOPs but files NO triage.

iterate-2026-06-13-triage-not-current-work — the F0.5 fail-closed exit codes
already STOP the iterate; the prior ``source="f0.5"`` triage producer mirrored
the *current run's own blocked work* into the "later" backlog, which is the
board's job, not triage's. This guards that:
  * the fail-closed exit code is unchanged (the gate still STOPs), and
  * ``surface_verification.main()`` appends nothing to triage, and
  * the producer helpers were removed at the source (not merely unreferenced).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_SV_PATH = _SHARED_SCRIPTS / "surface_verification.py"
_spec = importlib.util.spec_from_file_location("surface_verification_for_test", _SV_PATH)
assert _spec is not None and _spec.loader is not None
sv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sv)

from triage import read_all_items  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def test_fail_closed_none_no_justification_stops_without_triage(project: Path) -> None:
    """surface=none + no justification → fail-closed STOP, zero triage items."""
    rc = sv.main([
        "--project-root", str(project),
        "--run-id", "iterate-2026-06-13-x",
        "--surface", "none",
    ])
    # Still STOPs the iterate (exit code unchanged)...
    assert rc == sv.EXIT_NONE_WITHOUT_JUSTIFICATION
    # ...and nothing lands in the "later" backlog.
    assert read_all_items(project) == []


def test_success_path_unchanged_no_triage(project: Path) -> None:
    """Non-fail path (surface=none WITH justification) → EXIT_OK, no triage,
    evidence still written. Guards against the dead-helper removal accidentally
    changing success-path side effects (external-review hardening)."""
    rc = sv.main([
        "--project-root", str(project),
        "--run-id", "iterate-2026-06-13-ok",
        "--surface", "none",
        "--justification", "framework script change; no app surface exercised",
    ])
    assert rc == sv.EXIT_OK
    assert (project / ".shipwright" / "runs" / "iterate-2026-06-13-ok").exists()
    assert read_all_items(project) == []


def test_evidence_block_still_written(project: Path) -> None:
    """The evidence artifact is still produced (only the triage emit was cut)."""
    sv.main([
        "--project-root", str(project),
        "--run-id", "iterate-2026-06-13-y",
        "--surface", "none",
    ])
    evidence = project / ".shipwright" / "runs" / "iterate-2026-06-13-y"
    assert evidence.exists()
    assert read_all_items(project) == []


def test_f05_triage_producer_helpers_removed() -> None:
    """The F0.5 triage producer + resolve pass were removed at the source."""
    for name in (
        "_emit_failure_to_triage",
        "_resolve_stale_f05_items",
        "_f05_dedup_key",
        "_EXIT_TO_CONDITION",
        "_detail_for_condition",
    ):
        assert not hasattr(sv, name), f"{name} should have been removed"
