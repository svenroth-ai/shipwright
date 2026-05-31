"""iterate-2026-05-31-phasequality-dashboard-skip — hook-level FAIL→SKIP for
phases the project never engaged (dashboard consistency with the triage
backlog). Unit-tests `_skip_unengaged_fails`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402

_HOOK_PATH = _SHARED_SCRIPTS / "hooks" / "audit_phase_quality_on_stop.py"
_spec = importlib.util.spec_from_file_location("audit_phase_quality_on_stop", _HOOK_PATH)
assert _spec is not None and _spec.loader is not None
audit_hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit_hook)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _cfg(project: Path, **kw: object) -> None:
    (project / "shipwright_run_config.json").write_text(json.dumps(kw), encoding="utf-8")


def _events(project: Path, events: list[dict]) -> None:
    (project / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8")


def _findings(*statuses: str) -> dict[str, list[dict]]:
    return {"canon": [
        {"id": f"C{i}", "name": f"C{i}", "status": s, "evidence": "e"}
        for i, s in enumerate(statuses, 1)
    ]}


def test_unengaged_phase_fails_become_skip(project: Path) -> None:
    _cfg(project, status="complete")            # deploy never engaged
    f = audit_hook._skip_unengaged_fails(_findings("FAIL", "FAIL"), "deploy", project)
    canon = f["canon"]
    assert all(c["status"] == pq.STATUS_SKIP for c in canon)
    assert all(c["provenance"] == "not-engaged" for c in canon)
    assert "not engaged" in canon[0]["evidence"]


def test_engaged_phase_preserves_fail(project: Path) -> None:
    _cfg(project, status="complete")
    _events(project, [{"type": "phase_completed", "source": "changelog"}])
    f = audit_hook._skip_unengaged_fails(_findings("FAIL"), "changelog", project)
    assert f["canon"][0]["status"] == pq.STATUS_FAIL


def test_iterate_engaged_when_complete_preserves_fail(project: Path) -> None:
    _cfg(project, status="complete")
    f = audit_hook._skip_unengaged_fails(_findings("FAIL"), "iterate", project)
    assert f["canon"][0]["status"] == pq.STATUS_FAIL


def test_fail_open_without_run_config(project: Path) -> None:
    # No run_config → cfg None → engaged → FAIL preserved (never silently hide).
    f = audit_hook._skip_unengaged_fails(_findings("FAIL"), "deploy", project)
    assert f["canon"][0]["status"] == pq.STATUS_FAIL


def test_pass_warn_skip_untouched(project: Path) -> None:
    _cfg(project, status="complete")
    f = audit_hook._skip_unengaged_fails(_findings("PASS", "WARN", "SKIP"), "deploy", project)
    assert [c["status"] for c in f["canon"]] == ["PASS", "WARN", "SKIP"]


def test_in_progress_current_step_engaged_preserves_fail(project: Path) -> None:
    _cfg(project, status="in_progress", current_step="build", completed_steps=[])
    f = audit_hook._skip_unengaged_fails(_findings("FAIL"), "build", project)
    assert f["canon"][0]["status"] == pq.STATUS_FAIL
