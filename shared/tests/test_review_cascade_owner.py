"""The internal reviewer cascade must name an actor, not a forwarding address.

`constitution.md` states the three-stage review as an ALWAYS rule and names the
iterate review-record as one of its two implementations. The lifecycle did not
implement it: every artifact on the *deciding* side (trigger rules, phase
matrix, F11 floor, record schema) was correct, while every artifact on the
*performing* side named a different document as the actor —

- `SKILL.md` Step 8 pointed at `iteration-reviews.md` for "trigger rules",
- `iteration-reviews.md` described the cascade as something that happens *when
  the runner contract delegates it*,
- the runner contract delegated standalone runs to "the parent SKILL.md
  lifecycle Step 8".

A closed loop with nobody inside it. These guards pin the prose, because the
prose is what an agent follows at runtime; `review_record_check.py` catches the
outcome only after a run has already shipped without a review.

Companion to `test_review_cascade_decoupled.py` (#476), which pinned that the
external route is independent. This one pins that the *internal* route has an
owner. Asserted on normalised text so reflowing a paragraph does not fail the
suite while a changed rule does.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_ITERATE = REPO_ROOT / "plugins" / "shipwright-iterate"
_SKILL_DIR = _ITERATE / "skills" / "iterate"

SKILL_DOC = _SKILL_DIR / "SKILL.md"
REVIEWS_DOC = _SKILL_DIR / "references" / "iteration-reviews.md"
CAMPAIGN_DOC = _SKILL_DIR / "references" / "campaign-mode.md"
RUNNER_DOC = _ITERATE / "agents" / "sub-iterate-runner.md"
RUNNER_SCHEMA = _ITERATE / "agents" / "sub_iterate_runner_contract.schema.json"


def _norm(text: str) -> str:
    """Normalise markdown so wording is asserted, not layout.

    Unlike the sibling helper in `test_review_cascade_decoupled.py`, underscores
    are PRESERVED: half of what this module asserts is CLI flags
    (`--review-type external_code`), and stripping `_` as markdown emphasis
    silently turned every such assertion into one that could never match.
    """
    text = text.replace("—", "-").replace("’", "'").replace("§", "")
    text = re.sub(r"^[ \t]*>[ \t]?", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[*`]+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _section(doc: Path, heading: str, *, stop: str = "\n### ") -> str:
    """The body of one `###` section, up to the next same-level heading."""
    text = doc.read_text(encoding="utf-8")
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find(stop)
    return heading + (rest if end < 0 else rest[:end])


# --- AC1: standalone has an owner -------------------------------------------


def test_step_8_says_this_session_spawns_the_cascade():
    """Step 8 was two lines of pointer. It must name the actor.

    The defect this pins: a standalone run read the runner contract's
    "delegated to the parent SKILL.md lifecycle Step 8", arrived at Step 8, and
    found only "see the reference for trigger rules" — so nobody spawned.
    """
    body = _norm(_section(SKILL_DOC, "### Step 8: Full Code Review"))
    assert "this session" in body, (
        "Step 8 must name the actor — the standalone iterate session itself "
        "spawns the cascade, because it HAS the Agent tool"
    )
    assert "spawn" in body, "Step 8 must say the cascade is spawned, not delegated"


def test_step_8_names_all_three_stages():
    """A cascade named only as 'Full Code Review' loses two of its stages."""
    body = _norm(_section(SKILL_DOC, "### Step 8: Full Code Review"))
    for stage in ("spec-reviewer", "code-reviewer", "doubt-reviewer"):
        assert stage in body, f"Step 8 must name the {stage} stage"


def test_step_8_states_the_stage_1_block_and_pre_commit_placement():
    """Stage 1 is a HARD-GATE and the whole cascade precedes the commit.

    Raised by the external plan review (openai #2): giving Step 8 an owner
    without pinning *when* it runs leaves a pushed commit possible before any
    review.
    """
    body = _norm(_section(SKILL_DOC, "### Step 8: Full Code Review"))
    assert "hard-gate" in body or "hard gate" in body, (
        "Step 8 must state that spec-reviewer is a HARD-GATE blocking stage 2"
    )
    assert "f6" in body, "Step 8 must state it runs before F6 (commit)"


def test_skill_campaign_paragraph_scopes_the_adr_029_sentence():
    """The 'no Agent tool' sentence must not read as a general rule.

    It is campaign-scoped — it describes the sub-iterate-runner, which really
    lacks the tool. Lifted out of that context it tells every iterate not to
    spawn subagents, which is how this defect reached production.
    """
    norm = _norm(SKILL_DOC.read_text(encoding="utf-8"))
    assert "the runner has no agent tool" in norm, "sentence should still exist"
    idx = norm.index("the runner has no agent tool")
    window = norm[max(0, idx - 400):idx + 200]
    assert "campaign" in window, (
        "the 'no Agent tool' sentence must carry an explicit campaign-only "
        "marker within its own sentence or the one before it"
    )


# --- AC2: the reference stops routing through the runner contract -----------


def test_cascade_section_is_not_conditioned_on_the_runner_contract():
    """`When the runner contract delegates …, all three stages run` made the
    cascade's execution a consequence of a contract a standalone run never
    invokes."""
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "when the sub-iterate-runner contract" not in norm, (
        "the cascade description must not be conditioned on the runner "
        "contract delegating it — standalone runs have no runner"
    )


def test_cascade_section_names_the_standalone_owner_explicitly():
    """Stating who runs it must not be left to inference from a delegation."""
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "a standalone iterate spawns the cascade itself" in norm, (
        "the reference must say plainly that a standalone iterate spawns the "
        "cascade itself — it has the Agent tool"
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
    assert "| code, doubt | orchestrator - not the runner |" in body, (
        "the actor table must assign the two internal rows away from the "
        "runner — it performs neither"
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


def test_campaign_doc_states_the_residual_gap_honestly():
    """Until the before-merge cascade lands, campaign sub-iterates get the
    external review only. The doc must say so rather than imply coverage."""
    norm = _norm(CAMPAIGN_DOC.read_text(encoding="utf-8"))
    assert "the internal cascade does not run" in norm, (
        "campaign-mode.md must state that the internal cascade does not "
        "currently run for sub-iterates"
    )
    assert "carries the code pass alone" in norm, (
        "…and that the external review carries it alone. The earlier "
        "assertion (`\"external\" in norm`) was true before this change too — "
        "campaign-mode.md has always mentioned the External Plan Review."
    )



# --- Stage 1 has no row, and the docs say so plainly ------------------------


def test_the_code_row_is_stage_2s_and_stage_1_has_none():
    """Carrying the Stage-1 verdict in the `code` row was tried and reverted.

    Three independent reviewers converged on it: `completed` let a
    Stage-1-only row satisfy the medium+ code-quality floor although Stage 2
    provably had not run, `not_run` discards the findings, and the write
    ordering was unknowable at write time (a REJECT you intend to fix is not
    terminal). Since a REJECT loops until PASS and an unresolved REJECT never
    reaches F6, every shipping run ends at Stage 2 — so the row is Stage 2's.
    """
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "the code row belongs to stage 2, and stage 1 has no row at all" in norm, (
        "iteration-reviews.md must say plainly whose row it is"
    )
    assert "record code from stage 2" in norm


def test_the_stage_1_evidence_gap_is_stated_as_correctness_not_cosmetic():
    """The record cannot prove Stage 1 ran. Saying so is the honest half.

    A `code` row sourced `code-reviewer` is byte-identical whether Stage 1
    passed first or was never spawned — the not-run-versus-not-recorded
    distinction this artifact exists to abolish, at the HARD-GATE.
    """
    norm = _norm(REVIEWS_DOC.read_text(encoding="utf-8"))
    assert "known gap" in norm and "cannot evidence stage 1" in norm, (
        "the gap must be flagged where the recording rule is read"
    )
    assert "correctness" in norm, (
        "it must be named a correctness gap — an earlier draft called it a "
        "visibility gap, which is what justified deferring it"
    )
    assert "--recorded-by` is prose, not proof" in norm or            "recorded-by is prose, not proof" in norm


def test_skill_step_8_does_not_promise_more_than_the_cascade_sees():
    """`before F6` buys *not after*, not *reviews everything that ships*."""
    body = _norm(_section(SKILL_DOC, "### Step 8: Full Code Review"))
    assert "unreviewed" in body, (
        "Step 8 must state that artifacts written after it ship unreviewed in "
        "the same commit"
    )
