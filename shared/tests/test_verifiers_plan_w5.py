"""W5 reads review state through the one shared evaluator.

Split out of ``test_review_state_gate.py``, which owns the evaluator and the
``mark-review-state.py`` CLI. This file owns the compliance-verifier end: that
W5 blocks an undecided reviewer disagreement, and that it treats a marker
written before verdicts existed as a warning rather than a failure — it audits
plans of any age, unlike the in-session gate.
"""

from pathlib import Path

import pytest

from lib.phase_quality import STATUS_FAIL, STATUS_PASS, STATUS_WARN
from lib.review_marker import build_marker, write_marker
from tools.verifiers.plan_compliance import check_w5_external_review_marker

AGREEING = {"deepseek": "approve", "openai": "revise"}
CONTRADICTING = {"deepseek": "approve", "openai": "reject"}


def _project_with_marker(tmp_path: Path, **marker_kwargs) -> Path:
    planning = tmp_path / ".shipwright" / "planning"
    planning.mkdir(parents=True)
    write_marker(planning, build_marker(**marker_kwargs))
    return tmp_path


def test_no_marker_fails(tmp_path):
    assert check_w5_external_review_marker(tmp_path)["status"] == STATUS_FAIL


def test_a_completed_review_whose_reviewers_agreed_passes(tmp_path):
    root = _project_with_marker(
        tmp_path, status="completed", provider="openrouter", verdicts=AGREEING
    )
    assert check_w5_external_review_marker(root)["status"] == STATUS_PASS


def test_an_unresolved_contradiction_fails(tmp_path):
    root = _project_with_marker(
        tmp_path, status="completed", provider="openrouter", verdicts=CONTRADICTING
    )
    finding = check_w5_external_review_marker(root)
    assert finding["status"] == STATUS_FAIL
    assert "disagreement" in finding["evidence"]
    assert "contradiction-resolution" in finding["remediation"]


def test_it_passes_once_the_disagreement_is_decided(tmp_path):
    root = _project_with_marker(
        tmp_path,
        status="completed",
        provider="openrouter",
        verdicts=CONTRADICTING,
        contradiction_resolution="sided with reject; split 03-api in two",
    )
    assert check_w5_external_review_marker(root)["status"] == STATUS_PASS


def test_a_stored_block_claiming_agreement_cannot_override_the_verdicts(tmp_path):
    """W5 derives the disagreement from the verdicts rather than believing the
    marker's own summary of them."""
    root = _project_with_marker(
        tmp_path,
        status="completed",
        provider="openrouter",
        verdicts=CONTRADICTING,
        contradiction={"detected": False, "comparable": True,
                       "requires_resolution": False, "reason": "all fine, honest"},
    )
    assert check_w5_external_review_marker(root)["status"] == STATUS_FAIL


def test_a_marker_predating_verdicts_warns_rather_than_failing(tmp_path):
    """W5 audits plans of any age; one written before per-reviewer verdicts
    existed is flagged, not failed. The in-session gate blocks on the same
    state, because the marker it reads was written moments ago."""
    root = _project_with_marker(tmp_path, status="completed", provider="openrouter")
    finding = check_w5_external_review_marker(root)
    assert finding["status"] == STATUS_WARN
    assert "no reviewer verdicts" in finding["evidence"]
    assert "--verdict" in finding["remediation"]


def test_a_malformed_marker_fails(tmp_path):
    planning = tmp_path / ".shipwright" / "planning"
    planning.mkdir(parents=True)
    (planning / "external_review_state.json").write_text("{ not json", encoding="utf-8")
    assert check_w5_external_review_marker(tmp_path)["status"] == STATUS_FAIL


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"status": "skipped_user_opt_out", "reason": "offline"}, STATUS_PASS),
        ({"status": "skipped_user_opt_out"}, STATUS_FAIL),
        ({"status": "skipped_config_disabled", "reason": "feedback_iterations=0"}, STATUS_PASS),
        ({"status": "completed", "reason": ""}, STATUS_WARN),
    ],
)
def test_skip_handling_is_unchanged(tmp_path, kwargs, expected):
    """A skipped review has no reviewers, so it is judged exactly as before —
    the verdict machinery must not have changed the opt-out routes."""
    root = _project_with_marker(tmp_path, **kwargs)
    assert check_w5_external_review_marker(root)["status"] == expected
