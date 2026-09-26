"""Prose guards for campaign-dag-scheduler R5b ("serial merge lane: review
pinning, staleness cascade, STRICT-STOP") — the drain sweep (AC5) and
step-3h status mapping (AC6). Split out of `test_campaign_r5b_merge_lane_
prose.py` when it crossed the 300-line guideline (round 2) — AC1-AC4
(3f-bis/3g core) stay there; this file covers AC5/AC6, reusing the same
harness. Step 4's own held-merge reconciliation pass (round 3-4) split
further, into the sibling `test_campaign_r5b_merge_lane_prose_finalize.py`,
when this file itself crossed the guideline (round 5); the second-round
external-review fixes (glm + openai) split out again, into the sibling
`test_campaign_r5b_merge_lane_prose_review_fixes.py`, when this file
crossed the guideline a second time (round 19)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _campaign_prose_harness import CAMPAIGN_DOC  # noqa: E402


def _step_3h() -> str:
    """Mirrors `_campaign_prose_harness.step_3g` — from `3h.` to `3i.`."""
    import re

    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    start = re.search(r"(?m)^\s*3h\.", text)
    assert start, "campaign-mode.md must define loop step `3h.`"
    body = text[start.start():]
    end = re.search(r"(?m)^\s*3i\.", body)
    from _campaign_prose_harness import norm
    return norm(body[:end.start()] if end else body)


def _step_4() -> str:
    import re

    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    start = re.search(r"(?m)^4\. \*\*Finalize:\*\*", text)
    assert start, "campaign-mode.md must define step 4 (Finalize)"
    body = text[start.start():]
    end = re.search(r"(?m)^5\. \*\*Release prompt", body)
    from _campaign_prose_harness import norm
    return norm(body[:end.start()] if end else body)


# --- AC5: STRICT-STOP sweep + max_drain_seconds + guaranteed lock release ---


def test_strict_stop_is_redefined_to_drain_before_finalize():
    norm = CAMPAIGN_DOC.read_text(encoding="utf-8").lower()
    assert "campaign_drain.py" in norm
    assert "swept_never_started" in norm
    assert "swept_after_build" in norm
    assert "lease_expired_during_drain" in norm
    assert "drain_timeout" in norm


def test_strict_stop_definition_never_claims_a_per_unit_exception():
    """Tier-3 review, R5b round 19, blocking: the loop-wide STRICT-STOP
    definition itself said "A STRICT-STOP inside 3f-bis/3g for the unit
    currently mid-drain is narrower still ... those do NOT stop the whole
    wave" -- directly contradicting its own opening sentence that every bare
    STRICT-STOP in 3f-bis/3g means the full whole-wave procedure. The fix
    renames the per-unit case to a distinct term (HOLD demotion) and states,
    in the definition itself, that no per-unit exception to STRICT-STOP
    exists anywhere in this loop. Guard both halves so neither regresses."""
    from _campaign_prose_harness import norm as _norm

    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    definition_at = text.index("STRICT-STOP, defined once for the whole loop")
    window = _norm(text[definition_at:definition_at + 2600])
    assert "no per-unit exception anywhere" in window, (
        "the loop-wide definition must state there is no per-unit exception"
    )
    assert "is narrower still" not in window, (
        "must not reintroduce a STRICT-STOP variant described as narrower "
        "than the whole-wave halt"
    )
    assert "per-unit hold demotions are a different, narrower outcome" in window
    assert "must never be called a strict-stop" in window
    never_at = window.index("must never be called a strict-stop")
    no_exception_at = window.index("no per-unit exception anywhere")
    assert no_exception_at < never_at, (
        "the whole-loop, no-exception statement must precede the per-unit "
        "HOLD clarification, not follow a claimed exception"
    )


def test_step_4_drains_before_finalize_and_releases_after():
    step = _step_4()
    drain_at = step.index("campaign_drain.py")
    finalize_at = step.index("finalize --state")
    release_at = step.index("check_campaign_session_lock.py\" release")
    assert drain_at < finalize_at < release_at, (
        "step 4 must run drain, then finalize, then release the session lock "
        "-- in that order"
    )


def test_exit_4_sweeps_and_finalizes_instead_of_stopping_without_finalize():
    section = CAMPAIGN_DOC.read_text(encoding="utf-8")
    at = section.find("exit 4 →")
    assert at >= 0, "step 3a must document exit 4"
    window = section[at:at + 700].lower()
    assert "swept_never_started" in window
    assert "finalize" in window


# --- AC6: step 3h status-vocabulary mapping ---


def test_step_3h_maps_merged_to_complete_failed_to_failed():
    step = _step_3h()
    assert "merged" in step and "complete" in step
    assert "failed" in step


def test_step_3h_maps_swept_reason_codes_to_pending_not_failed():
    step = _step_3h()
    assert "swept_never_started" in step
    assert "swept_after_build" in step
    assert "pending" in step


def test_step_3h_does_not_change_campaign_progress_enum():
    step = _step_3h()
    assert "no new token added" in step or "unchanged by this" in step
