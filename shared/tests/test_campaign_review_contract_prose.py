"""Prose guards for the CAMPAIGN review contract — the runner, its schema, `campaign-mode.md`.

Split from the standalone half by ARTIFACT (external plan review, gemini #2).
These pin that the runner records each pass under the name of whoever
performed it, that `delegated_to_skill` is deprecated rather than deleted, and
that `campaign-mode.md` describes a step that can actually happen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_ITERATE = REPO_ROOT / "plugins" / "shipwright-iterate"
_SKILL_DIR = _ITERATE / "skills" / "iterate"

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
