"""Shape test for the `ci.yml` edit P3.5's restart (round 2,
``.shipwright/planning/iterate/2026-09-09-p3-5-promote-layers-per-fr-restart.md``)
made to the "python-checks" job: the new artifact-upload step carrying the
CI run's own regenerated traceability manifest (AC-R8, AC-R9).

Parses the REAL, checked-in `.github/workflows/ci.yml` (not a synthetic
fixture) — same "anchor on structure, then mutate and watch it fail"
convention as `test_ci_yml_provenance_step_shape.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import ci_execution_evidence  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_STEP_NAME = "Upload regenerated traceability manifest artifact (execution evidence)"


def _load_job() -> dict:
    data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    return data["jobs"]["python-checks"]


def _find(steps: list[dict], name: str) -> dict:
    for step in steps:
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r} in ci.yml python-checks job")


def test_artifact_step_uses_upload_artifact_action():
    step = _find(_load_job()["steps"], _STEP_NAME)
    assert step["uses"] == "actions/upload-artifact@v4"


def test_artifact_step_name_matches_the_python_constant():
    # AC-R9: `name:` (the artifact's own identity on the Artifacts API, `with.name`,
    # not the step's display `name:`) is pinned to the constant the resolver imports,
    # so a rename on either side fails loudly here rather than silently at query time.
    step = _find(_load_job()["steps"], _STEP_NAME)
    assert step["with"]["name"] == ci_execution_evidence.EXECUTION_EVIDENCE_ARTIFACT_NAME


def test_artifact_step_path_is_the_literal_manifest_path_not_a_glob():
    step = _find(_load_job()["steps"], _STEP_NAME)
    assert step["with"]["path"] == ".shipwright/compliance/test-traceability.json"


def test_artifact_step_is_gated_on_drift_clean_and_push_only():
    step = _find(_load_job()["steps"], _STEP_NAME)
    assert step["if"] == "steps.manifest_drift.outputs.code == '0' && github.event_name == 'push'"


def test_artifact_step_never_fails_the_build():
    # This upload is load-bearing for the whole unforgeability claim, but a
    # transient upload failure must never become a NEW way for ci.yml itself
    # to fail — continue-on-error: true is deliberate (see ci.yml comment).
    step = _find(_load_job()["steps"], _STEP_NAME)
    assert step["continue-on-error"] is True


def test_artifact_step_retention_is_pinned_explicitly():
    # Explicit, matching the repo default, so a future org-level default
    # change can't silently shrink the window the Known Limitations section
    # assumes.
    step = _find(_load_job()["steps"], _STEP_NAME)
    assert step["with"]["retention-days"] == 90


def test_artifact_step_ignores_a_missing_manifest_rather_than_failing():
    step = _find(_load_job()["steps"], _STEP_NAME)
    assert step["with"]["if-no-files-found"] == "ignore"


def test_artifact_step_runs_immediately_after_the_drift_check_step():
    steps = _load_job()["steps"]
    drift_idx = next(
        i for i, s in enumerate(steps)
        if s.get("name") == "Check traceability manifest against a fresh regeneration"
    )
    assert steps[drift_idx + 1]["name"] == _STEP_NAME


def test_python_checks_job_has_no_os_matrix():
    # AC-R8: the resolver's artifact query has no OS-axis to disambiguate —
    # this pins the assumption that the job producing the artifact never
    # fans out across a matrix, so "the newest qualifying run's artifact" is
    # unambiguous.
    job = _load_job()
    assert job["runs-on"] == "ubuntu-latest"
    assert "strategy" not in job
