"""Malformed-artifact and path-safety tests for the Step 3.4
recording-integrity F11 gate (`check_risk_recheck_recorded`).

Split out of `test_risk_recheck_recording.py` (which keeps the
skip/pass/fail comparison logic, `_rank`, and the drift-pin/registry tests)
to keep both files under the 300-line bloat guideline. Every field of the
persisted artifact is a self-report and must be validated defensively —
these tests are the ones the external plan and code reviews (2026-08-05)
drove: strict schema/shape validation, `run_id` safety, and directory
containment against a symlinked run directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from tools.verifiers.risk_recheck_recording import (  # noqa: E402
    RECHECK_SCHEMA_VERSION,
    check_risk_recheck_recorded,
    recheck_record_relpath,
)

RUN_ID = "iterate-2026-08-05-example"


def _write_recheck(project_root: Path, path_run_id: str, **overrides) -> Path:
    """Write the artifact at `path_run_id`'s location. `overrides` may include
    `run_id` to make the ENVELOPE's run_id diverge from the file's location."""
    path = project_root / recheck_record_relpath(path_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": RECHECK_SCHEMA_VERSION,
        "run_id": path_run_id,
        "risk_recheck": {"effective_complexity": "medium"},
    }
    body.update(overrides)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _write_f5c_entry(project_root: Path, run_id: str, complexity: str) -> Path:
    entries_dir = project_root / ".shipwright" / "agent_docs" / "iterates"
    entries_dir.mkdir(parents=True, exist_ok=True)
    path = entries_dir / f"{run_id}.json"
    path.write_text(json.dumps({
        "run_id": run_id,
        "date": "2026-08-05T00:00:00Z",
        "type": "change",
        "complexity": complexity,
        "branch": f"iterate/{run_id}",
        "tests_passed": True,
    }), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fail — malformed artifact, every field validated (external review findings)
# ---------------------------------------------------------------------------


def test_fail_when_artifact_is_not_json(tmp_path: Path):
    path = tmp_path / recheck_record_relpath(RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False


def test_fail_when_artifact_is_not_an_object(tmp_path: Path):
    path = tmp_path / recheck_record_relpath(RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False


def test_fail_when_schema_version_unrecognized(tmp_path: Path):
    _write_recheck(tmp_path, RUN_ID, schema_version=99)
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "schema_version" in result.detail


def test_fail_when_run_id_mismatched(tmp_path: Path):
    """A stale artifact from a DIFFERENT run must not license this one."""
    _write_recheck(tmp_path, RUN_ID, run_id="iterate-2026-08-05-other")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "another run" in result.detail


def test_fail_when_risk_recheck_is_not_an_object(tmp_path: Path):
    _write_recheck(tmp_path, RUN_ID, risk_recheck="medium")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False


def test_fail_when_effective_complexity_missing(tmp_path: Path):
    _write_recheck(tmp_path, RUN_ID, risk_recheck={})
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False


def test_fail_when_effective_complexity_unrecognized(tmp_path: Path):
    _write_recheck(tmp_path, RUN_ID, risk_recheck={"effective_complexity": "enormous"})
    _write_f5c_entry(tmp_path, RUN_ID, "medium")
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "enormous" in result.detail


def test_fail_when_artifact_exists_but_is_not_a_regular_file(tmp_path: Path):
    path = tmp_path / recheck_record_relpath(RUN_ID)
    path.mkdir(parents=True)  # a directory where a file is expected
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "not a regular file" in result.detail


def test_fail_when_effective_complexity_field_missing_names_it_as_missing(tmp_path: Path):
    """Distinct from 'unrecognized' (deepseek finding, external code review
    2026-08-05): a missing field and an invalid value are different defects."""
    _write_recheck(tmp_path, RUN_ID, risk_recheck={"risk_flags": []})
    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "lacks" in result.detail
    assert "unrecognized" not in result.detail


# ---------------------------------------------------------------------------
# run_id validation + directory containment (external code review, 2026-08-05)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_run_id", ["../escape", "..", ".", "", "with/slash"])
def test_fail_when_run_id_unsafe(tmp_path: Path, bad_run_id):
    """An unsafe run_id must FAIL, not SKIP — an unlocatable artifact is not
    the same as a genuinely absent one."""
    result = check_risk_recheck_recorded(tmp_path, bad_run_id)
    assert result.ok is False
    assert not result.is_skipped


def test_fail_when_run_directory_is_a_symlink_escaping_the_planning_tree(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "risk_recheck.json").write_text(json.dumps({
        "schema_version": RECHECK_SCHEMA_VERSION, "run_id": RUN_ID,
        "risk_recheck": {"effective_complexity": "large"},
    }), encoding="utf-8")
    planning = tmp_path / ".shipwright" / "planning" / "iterate"
    planning.mkdir(parents=True)
    try:
        (planning / RUN_ID).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation unavailable")

    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert "resolves outside" in result.detail


def test_fail_when_artifact_path_is_a_dangling_symlink(tmp_path: Path):
    """A dangling symlink makes `path.exists()` False — which must NOT be
    read as genuine absence (that would silently SKIP a planted artifact)."""
    path = tmp_path / recheck_record_relpath(RUN_ID)
    path.parent.mkdir(parents=True)
    try:
        path.symlink_to(path.parent / "nowhere")
    except OSError:
        pytest.skip("symlink creation unavailable")

    result = check_risk_recheck_recorded(tmp_path, RUN_ID)
    assert result.ok is False
    assert not result.is_skipped
    assert "symlink" in result.detail
