"""Prose guards for campaign-dag-scheduler R5b step 4 (Finalize)'s
held-merge reconciliation pass (third-, fourth- and seventh-round external-
review fixes). Split out of `test_campaign_r5b_merge_lane_prose_drain.py`
when it crossed the 300-line guideline (round 5) — that file keeps AC5/AC6
and the second-round fixes; this file covers only step 4's reconciliation,
reusing the same harness. `_step_4` is duplicated rather than imported,
matching this suite's own convention (e.g. `test_check_review_attribution_
composition.py`'s duplicated helpers) since sharing it would need a new
module neither sibling otherwise requires.

Round 7 (Tier-3 review: "add executable integration coverage ... including
... held-merge reconciliation") moved the actual reconciliation logic out of
this doc's inline jq/bash and into `lib.held_merge_reconciliation` — real,
directly-executable Python covered by `test_held_merge_reconciliation.py`.
What remains here is narrower by design: confirming the doc invokes that
script in the right place with the right arguments, and that the round-6
disclosure text survives — not re-deriving the reconciliation logic itself
by string-matching bash that no longer exists.
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
    reconcile_at = step.index("held_merge_reconciliation.py")
    finalize_at = step.index("finalize --state")
    assert drain_at < reconcile_at < finalize_at, (
        "the held-merge reconciliation must run strictly between "
        "campaign_drain.py's own drain and cmd_finalize"
    )


def test_held_merge_reconciliation_is_invoked_with_state_and_roots():
    step = _step_4()
    invoke_at = step.index("held_merge_reconciliation.py")
    window = step[invoke_at:invoke_at + 400]
    assert "--state" in window
    assert "--project-root" in window
    assert "--shared-root" in window
    assert "|| strict-stop" in window


def test_held_merge_reconciliation_is_invoked_with_plugin_root_and_campaign_dir():
    """Tier-3 review, R5b round 12, blocking: this pass now also corrects
    campaign_progress.json for a reconciled unit, which needs the plugin
    root (where campaign_progress.py lives) and the campaign directory --
    without both, held_merge_reconciliation.py's own argparse would refuse
    to start at all (both are required arguments)."""
    step = _step_4()
    invoke_at = step.index("held_merge_reconciliation.py")
    window = step[invoke_at:invoke_at + 400]
    assert "--plugin-root" in window
    assert "--campaign-dir" in window


def test_held_merge_reconciliation_corrects_the_local_board_too():
    """Round 12: step 3h maps a reconciled unit to `failed` on the board
    WHILE it is still `held`, before this pass ever runs -- left alone, the
    board would show `failed` forever. The doc must disclose that this pass
    also corrects that board entry, not just loop_state.json."""
    step = _step_4()
    assert "campaign_progress.json" in step
    assert "update-status" in step
    assert "--status complete" in step
    assert "local-board convenience" in step, (
        "the correction must be framed as best-effort, matching 3h's own "
        "established convention for this same board"
    )


def test_held_merge_reconciliation_covers_both_reason_codes_in_prose():
    """The doc must still name both `reason_code`s this pass corrects, even
    though the filtering logic itself now lives in
    `lib.held_merge_reconciliation` (real tests: `test_held_merge_
    reconciliation.py::TestFindReconcilableHeld`)."""
    step = _step_4()
    assert "drain_timeout" in step
    assert "merge_confirmation_timeout" in step


def test_held_merge_reconciliation_is_extracted_not_reinlined():
    """Round 7 (Tier-3 review): guards against a future edit silently
    reintroducing the inline jq/bash loop this round replaced."""
    step = _step_4()
    assert "lib.held_merge_reconciliation" in step or "held_merge_reconciliation.py" in step
    assert "jq -r '.units[]" not in step, (
        "the reconciliation pass must stay extracted into "
        "lib.held_merge_reconciliation, not re-inlined as bash/jq"
    )


# --- Sixth-round external review fixes (R5b round 6, Tier-3 BLOCK) ---


def test_held_merge_reconciliation_race_narrowing_is_disclosed_not_claimed_closed():
    """Tier-3 review, R5b round 6: a timed-out worker's own UNBOUNDED step
    (`gh pr checks --watch` waiting on slow CI) can outlive even the bounded
    reconciliation poll above -- no fixed window can guarantee catching
    every case without a Task-cancellation primitive this framework does
    not have. This disclosure must say so plainly, not imply the race is
    fully closed."""
    full = " ".join(CAMPAIGN_DOC.read_text(encoding="utf-8").lower().split())
    assert "narrows the race, it does not close it" in full
    assert "task-cancellation primitive this framework does not have" in full
