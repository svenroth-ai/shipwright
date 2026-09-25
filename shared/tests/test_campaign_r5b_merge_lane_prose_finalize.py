"""Prose guards for campaign-dag-scheduler R5b step 4 (Finalize)'s
held-merge reconciliation pass (third- and fourth-round external-review
fixes). Split out of `test_campaign_r5b_merge_lane_prose_drain.py` when it
crossed the 300-line guideline (round 5) — that file keeps AC5/AC6 and the
second-round fixes; this file covers only step 4's reconciliation, reusing
the same harness. `_step_4` is duplicated rather than imported, matching
this suite's own convention (e.g. `test_check_review_attribution_
composition.py`'s duplicated helpers) since sharing it would need a new
module neither sibling otherwise requires.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _campaign_prose_harness import CAMPAIGN_DOC, norm  # noqa: E402


def _step_4() -> str:
    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    start = re.search(r"(?m)^4\. \*\*Finalize:\*\*", text)
    assert start, "campaign-mode.md must define step 4 (Finalize)"
    body = text[start.start():]
    end = re.search(r"(?m)^5\. \*\*Release prompt", body)
    return norm(body[:end.start()] if end else body)


# --- Third-round external review fixes (R5b round 3, Tier-3 BLOCK) ---


def test_held_merge_reconciliation_runs_between_drain_and_finalize():
    """Tier-3 review, R5b round 3: closes the live-reconciliation gap
    `campaign_drain.py`'s own module docstring named as an unbuilt follow-up
    — a `drain_timeout`-held unit's own in-flight merge may have completed
    genuinely after the forced transition, so finalize must never run
    before this check corrects the record."""
    step = _step_4()
    drain_at = step.index("campaign_drain.py")
    reconcile_at = step.index("reconcilable_held")
    finalize_at = step.index("finalize --state")
    assert drain_at < reconcile_at < finalize_at, (
        "the held-merge reconciliation must run strictly between "
        "campaign_drain.py's own drain and cmd_finalize"
    )


def test_held_merge_reconciliation_verifies_merged_state_before_correcting():
    """A `gh` failure or a genuinely-still-open PR must leave the row exactly
    as recorded -- this pass only ever corrects a stale `held` into
    `merged`, never blocks finalize on a best-effort check."""
    step = _step_4()
    reconcile_at = step.index("reconcilable_held")
    window = step[reconcile_at:reconcile_at + 1200]
    assert "gh pr view" in window
    assert '"merged"' in window
    assert "mergecommit.oid" in window
    assert "|| continue" in window


def test_held_merge_reconciliation_marks_merged_via_forced_operator_override():
    step = _step_4()
    reconcile_at = step.index("reconcilable_held")
    window = step[reconcile_at:reconcile_at + 1600]
    mark_at = window.index('loop_claim.py" mark ')
    tail = window[mark_at:mark_at + 400]
    assert "--status merged" in tail
    assert "--campaign-worktree" in tail
    assert "--merged-commit" in tail
    assert "held_merge_reconciled" in tail
    assert "|| strict-stop" in tail


# --- Fourth-round external review fixes (R5b round 4, Tier-3 BLOCK) ---


def test_held_merge_reconciliation_covers_both_drain_timeout_and_confirmation_timeout():
    """Tier-3 review, R5b round 4: round 3's reconciliation scoped to
    `drain_timeout` alone left a `merge_confirmation_timeout` row -- whose PR
    3g's own poll already confirmed MERGED, only the SHA confirmation timed
    out -- with no path back to `merged`, mapping it to a permanent, false
    `failed` at step 3h. Both `reason_code`s need the identical correction,
    so one filter must cover both."""
    step = _step_4()
    reconcile_at = step.index("reconcilable_held")
    window = step[reconcile_at:reconcile_at + 300]
    assert '.status == "held"' in window
    assert '.reason_code == "drain_timeout"' in window
    assert '.reason_code == "merge_confirmation_timeout"' in window
