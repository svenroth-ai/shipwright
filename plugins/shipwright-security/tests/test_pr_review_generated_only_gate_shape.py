"""Shape assertions for the all-generated PR-review carve-out
(iterate-2026-09-10-pr-review-generated-only), split out of
test_pr_review_workflow_shape.py to keep that file under the size guideline.

See that module's docstring for the two-stage workflow background. These
tests cover ONLY the new wiring: the tier step's classifier outputs, the
review step's tightened gating `if:`, and the verdict step's crash-safety
guard around the gate-decision script call.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE2_PATH = REPO_ROOT / ".github" / "workflows" / "pr-review-run.yml"


def _read(path: Path) -> str:
    assert path.exists(), f"missing workflow: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def stage2() -> str:
    return _read(STAGE2_PATH)


def test_generated_only_gate_derived_from_api_changed_paths(stage2):
    """FR-01.17 (E)7: the all-generated carve-out must be trusted-source-derived."""
    assert "review_record_tier.py" in stage2
    assert "steps.tier.outputs.all_generated" in stage2
    assert 'ALL_GENERATED: ${{ steps.tier.outputs.all_generated }}' in stage2
    assert 'ALL_GENERATED_REASON: ${{ steps.tier.outputs.all_generated_reason }}' in stage2
    # A sensitive path must still force the review step to run even when
    # every OTHER changed path is generated — enforced by the classifier
    # itself (see test_review_record_tier.py), not by this workflow text,
    # but the wiring must at least gate the model call on it.
    review_step_if = re.search(
        r"name: Run Tier-3 PR review\n\s*id: review\n\s*if: >-\n([\s\S]{0,300}?)\n\s*env:",
        stage2,
    )
    assert review_step_if, "could not locate the Run Tier-3 PR review step's `if:`"
    # All three conditions, not just the new one — a future edit dropping
    # either pre-existing clause would otherwise still pass this test
    # (external code-review finding).
    condition = review_step_if.group(1)
    assert "github.event.workflow_run.conclusion == 'success'" in condition
    assert "steps.tier.outputs.needs_review == 'true'" in condition
    assert "steps.tier.outputs.all_generated != 'true'" in condition


def test_gate_decision_script_failure_still_posts_a_status(stage2):
    """External code-review finding: under this step's `set -e`, a bare
    `gate_out=$(failing_cmd)` aborts the step before the `gh api
    .../statuses` call ever runs — the `|| gate_out=""` guard is what keeps
    the existing empty-state fallback reachable."""
    assert "decide_pr_review_gate.py \\" in stage2
    assert '--tier-reason "$TIER_REASON") || gate_out=""' in stage2
