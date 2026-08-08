"""Prose guards for the CAMPAIGN review contract — the runner and its schema.

Split from the standalone half by ARTIFACT (external plan review, gemini #2).
These pin that the runner records each pass under the name of whoever
performed it, and that `delegated_to_skill` is deprecated rather than deleted.

The step-3f-bis guards live in `test_campaign_step_3f_bis.py`; shared helpers
in `_campaign_prose_harness.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _campaign_prose_harness import (  # noqa: E402
    CAMPAIGN_DOC,
    REVIEWS_DOC,
    RUNNER_DOC,
    RUNNER_SCHEMA,
    norm as _norm,
    section as _section,
)

# --- AC4: the runner records under the right name ---------------------------


def test_runner_assigns_the_external_run_and_the_internal_pass_to_different_rows():
    """Step 3.7 closed `code` as completed for what item 2 (the EXTERNAL
    review) had just done, so the record claimed the internal pass happened.

    The actor table is the runner's own contract; the exact commands live in
    `iteration-reviews.md` (the runner doc is a runtime-prompt under a 400-line
    cap, so the four command blocks sit in their canonical home instead).
    """
    body = _norm(_section(RUNNER_DOC, "### Step 3.7:"))
    assert "| external_code | runner" in body, (
        "the actor table must assign external_code to the runner"
    )
    assert "| spec (stage 1), code, doubt | orchestrator - not the runner |" in body, (
        "the actor table must assign the three internal rows away from the "
        "runner — it performs none of them"
    )
    assert "not_run only" in body, (
        "the internal rows must be writable by the runner ONLY as not_run"
    )


def test_runner_never_marks_internal_code_completed_from_an_external_run():
    body = _norm(_section(RUNNER_DOC, "### Step 3.7:"))
    assert "--review-type code --status completed" not in body, (
        "the runner performs no internal cascade, so it may never write "
        "code=completed; that is the mislabelling this fix removes"
    )
    assert "may never write code or doubt as completed" in body


def test_the_campaign_recording_commands_exist_where_the_runner_is_sent():
    """The pointer must not dangle — the runner is told to go read these.

    Pointer AND target are pinned as a pair: asserting only the target would
    leave both guards green if the pointer line were deleted, stranding the
    runner with an actor table and no commands. That dangling-pointer shape is
    defect (A) itself, so it must not be reintroduced by the relocation that
    kept this file under its size cap.
    """
    runner_step = _norm(_section(RUNNER_DOC, "### Step 3.7:"))
    assert "campaign sub-iterate rows" in runner_step, (
        "Step 3.7 must point at the section that holds the commands"
    )

    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "campaign sub-iterate rows" in norm, (
        "iteration-reviews.md must carry the section the runner points at"
    )
    assert "--review-type external_code" in norm, (
        "the external review must be recorded under external_code"
    )
    assert "--review-type code --status not_run" in norm, (
        "the delegated internal pass must be recorded not_run with a "
        "disposition naming the capability limit"
    )
    assert "--review-type doubt --status not_run" in norm
    assert "--review-type plan_internal --status not_run" in norm, (
        "the internal plan-review arm must be recorded not_run with a "
        "disposition naming the documented gap — it is never promoted at "
        "3f-bis, unlike spec/code/doubt above"
    )


def test_runner_carries_a_status_transition_table():
    """External plan review (openai #5): naming which rows to record without
    saying who may set which status reproduces the original bug."""
    body = _norm(_section(RUNNER_DOC, "### Step 3.7:"))
    assert "actor" in body, (
        "Step 3.7 must carry a status-transition table naming the actor per "
        "review type"
    )
    for review_type in ("self", "code", "doubt", "external_code"):
        assert review_type in body, f"the table must cover {review_type}"


# --- AC5: the enum value is deprecated, not deleted -------------------------


def test_delegated_to_skill_is_retained_for_backward_compatibility():
    """External plan review (gemini #1, openai #4): removing an enum value
    invalidates historical result.json artifacts."""
    schema = json.loads(RUNNER_SCHEMA.read_text(encoding="utf-8"))
    blob = json.dumps(schema)
    assert "delegated_to_skill" in blob, (
        "the value must stay readable for historical runs — deprecate, do not "
        "delete"
    )


def test_delegated_statuses_are_documented_with_their_scope():
    schema = json.loads(RUNNER_SCHEMA.read_text(encoding="utf-8"))
    description = json.dumps(schema).lower()
    assert "deprecated" in description, (
        "delegated_to_skill must be marked deprecated — standalone runs have "
        "no delegate"
    )
    assert "campaign" in description, (
        "delegated_to_orchestrator must be documented as campaign-only"
    )


# --- AC7: campaign-mode.md stops describing a step that cannot run ----------


def test_campaign_doc_drops_the_impossible_parallel_claim():
    """The orchestrator blocks at 3d on the runner's TERMINAL marker, which the
    runner emits only after F6 commit and Step 5 push. 'In parallel with the
    runner, after Build' names a window that does not exist."""
    norm = _norm(CAMPAIGN_DOC.read_text(encoding="utf-8"))
    assert "spawns it in parallel with the runner" not in norm, (
        "the orchestrator cannot spawn anything while blocked on DONE"
    )


def test_campaign_doc_no_longer_declares_the_cascade_absent():
    """The gap this used to pin is CLOSED by step 3f-bis.

    Until `iterate-2026-07-31-it7b-campaign-cascade` this module asserted the
    OPPOSITE — that campaign-mode.md said "the internal cascade does not run"
    and that the external review "carries the code pass alone". Both were true
    and both had to be stated, because a doc implying coverage it did not have
    is worse than one admitting the hole. Now the delegate ADR-029 named has a
    step, so the same honesty requirement inverts: the doc must not keep
    telling readers the cascade is absent when it runs at 3f-bis.
    """
    norm = _norm(CAMPAIGN_DOC.read_text(encoding="utf-8"))
    assert "the internal cascade does not run" not in norm, (
        "campaign-mode.md still declares the internal cascade absent, but "
        "3f-bis runs it — a reader would skip the step they are owed"
    )
    assert "carries the code pass alone" not in norm, (
        "the external review no longer carries the code pass alone; "
        "code-reviewer runs at 3f-bis"
    )


def test_campaign_doc_names_where_the_delegated_cascade_runs():
    """ADR-029 named the orchestrator the delegate on 2026-05-04 and gave it no
    step for three months. The doc must say WHERE the delegate acts, not merely
    that one exists — naming a delegate without a step IS the original defect.
    """
    norm = _norm(CAMPAIGN_DOC.read_text(encoding="utf-8"))
    assert "3f-bis" in norm, (
        "campaign-mode.md must name the step where the delegated cascade runs"
    )
    for role in ("spec-reviewer", "code-reviewer", "doubt-reviewer"):
        assert role in norm, f"the cascade step must name {role}"


