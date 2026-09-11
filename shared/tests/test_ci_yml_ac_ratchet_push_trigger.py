"""trg-e69bf1ba / iterate-2026-09-11-ac-ratchet-push-observe — shape test for
widening the `AC coverage ratchet (gate)` step's trigger to also run on push
to `main`, the one P3.7 feeder that needs no merge base.

Parses the REAL, checked-in `.github/workflows/ci.yml` (never a synthetic
fixture), matching `test_ci_yml_keystone_step_shape.py`'s own convention.
"""

from __future__ import annotations

import yaml

from tools.check_ci_gate_coverage import is_gate_step, parse_workflows

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

RATCHET_STEP_NAME = "AC coverage ratchet (gate)"
ORPHAN_STEP_NAME = "Orphan AC binding (gate)"
DRIFT_STEP_NAME = "Check traceability manifest against a fresh regeneration"


def _steps() -> list[dict]:
    data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    return data["jobs"]["python-checks"]["steps"]


def _index_of(name: str) -> int:
    for i, step in enumerate(_steps()):
        if step.get("name") == name:
            return i
    raise AssertionError(f"no step named {name!r} in ci.yml python-checks job")


def _ratchet() -> dict:
    return _steps()[_index_of(RATCHET_STEP_NAME)]


def test_the_step_runs_on_pull_request_or_push_to_main():
    """The one feeder that CAN run on push, because it needs no merge base —
    `check_ac_coverage_ratchet.py` only ever reads HEAD's own manifest and the
    committed baseline, never `--base-sha`/`--head-sha`."""
    condition = _ratchet()["if"]
    assert condition == (
        "github.event_name == 'pull_request' || "
        "(github.event_name == 'push' && github.ref == 'refs/heads/main')"
    )


def test_the_sibling_orphan_gate_stays_pull_request_only():
    """The OTHER feeder is a genuine merge condition (its arm 2 needs a base
    to diff against) — widening the ratchet gate's trigger must not silently
    widen its sibling's too."""
    orphan = _steps()[_index_of(ORPHAN_STEP_NAME)]
    assert orphan["if"] == "github.event_name == 'pull_request'"


def test_the_step_still_has_no_continue_on_error():
    assert "continue-on-error" not in _ratchet()


def test_the_step_still_comes_after_the_manifest_regeneration_step():
    assert _index_of(RATCHET_STEP_NAME) > _index_of(DRIFT_STEP_NAME)


def test_the_step_takes_no_conditional_dependency_on_another_step():
    step = _ratchet()
    assert "needs" not in step
    condition = str(step.get("if", ""))
    for token in ("hashFiles", "coverage.xml", "steps."):
        assert token not in condition, (
            f"the ratchet step's `if:` references {token!r} — its execution must depend "
            "on the EVENT alone, never on another step's outcome or artifact"
        )


def test_the_step_command_adds_the_growth_flag_only_on_push():
    """External code review (openai, HIGH): re-running the SAME comparison
    against the SAME committed baseline on push detects nothing new for a
    same-PR self-grandfathered entry. `--check-baseline-growth
    --parent-sha <before-sha>` is the actual fix, and it must be conditioned
    on `push` specifically, not blanket-on — the pull_request invocation
    stays exactly as it was (no merge-base flags either).

    Asserts the FULL conditional expression, not merely that its pieces
    appear somewhere in the body (external code review, glm, low, round 2):
    a malformed expression like `push || '--check-baseline-growth'` would
    satisfy a substring-only check while evaluating to something else
    entirely.
    """
    body = _ratchet()["run"]
    assert "shared/scripts/tools/check_ac_coverage_ratchet.py --project-root ." in body
    assert (
        "${{ github.event_name == 'push' && "
        "format('--check-baseline-growth --parent-sha \"{0}\"', github.event.before) || '' }}"
    ) in body
    assert "--write" not in body
    assert "--base-sha" not in body
    assert "--head-sha" not in body


def test_the_job_permissions_stay_read_only():
    """The whole point is re-deriving the comparison, never writing the
    baseline back — the job (and workflow) must stay contents: read."""
    data = yaml.safe_load(_CI_YML.read_text(encoding="utf-8"))
    assert data["permissions"]["contents"] == "read"
    job = data["jobs"]["python-checks"]
    assert "permissions" not in job, (
        "python-checks must not widen the workflow's read-only top-level permissions"
    )


def test_the_step_still_ends_in_gate_so_the_ci_gate_guard_enrols_it():
    steps = [
        s for s in parse_workflows(_REPO_ROOT)
        if s.workflow == "ci.yml" and s.name == RATCHET_STEP_NAME
    ]
    assert len(steps) == 1, f"expected exactly one {RATCHET_STEP_NAME!r} step, found {len(steps)}"
    assert is_gate_step(steps[0])
