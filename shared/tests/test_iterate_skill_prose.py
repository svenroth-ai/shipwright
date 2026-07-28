"""Prose guards for the iterate SKILL's own phase text — `SKILL.md` + `F12.md`.

Third split of this suite, kept consistently **by artifact**: these are the
documents the session executes as it moves through the lifecycle. The review
CONTRACT they defer to (`iteration-reviews.md`) is guarded in
`test_iteration_reviews_prose.py`; the campaign-side contract in
`test_campaign_review_contract_prose.py`.

What these pin: Step 8 names an actor (this session), states the Stage-1
HARD-GATE and its pre-F6 placement, does not overpromise what the cascade sees,
scopes ADR-029's "no `Agent` tool" to campaign mode — and, since a session
policy can gate subagent spawning, ASKS for the go-ahead before Stage 1 rather
than lapsing into `not_run` at F11. F12's banner must actually carry the
missing pass, because that is the surface Step 8 promises it on.
"""


from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_ITERATE = REPO_ROOT / "plugins" / "shipwright-iterate"
_SKILL_DIR = _ITERATE / "skills" / "iterate"

SKILL_DOC = _SKILL_DIR / "SKILL.md"
REVIEWS_DOC = _SKILL_DIR / "references" / "iteration-reviews.md"


def _norm(text: str) -> str:
    """Normalise markdown so wording is asserted, not layout.

    Kept byte-identical to its campaign-side sibling so both files normalise the
    same way. Underscores are PRESERVED because the sibling asserts CLI flags
    (`--review-type external_code`); stripping `_` as markdown emphasis once
    turned every such assertion into one that could never match.
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
    # One operand only: `_norm` strips backticks, so the backticked variant
    # this inherited from #482 could never be true (Stage-3 doubt).
    assert "recorded-by is prose, not proof" in norm


def test_skill_step_8_does_not_promise_more_than_the_cascade_sees():
    """`before F6` buys *not after*, not *reviews everything that ships*."""
    body = _norm(_section(SKILL_DOC, "### Step 8: Full Code Review"))
    assert "unreviewed" in body, (
        "Step 8 must state that artifacts written after it ship unreviewed in "
        "the same commit"
    )


# --- "cannot run" must not mean "was never asked" ---------------------------


def test_step_8_asks_for_the_go_ahead_before_stage_1():
    """The question has to come FIRST, or it buys nothing.

    The session directive that gates subagent spawning is conditional — one
    sentence from the operator lifts it for the rest of the session. Four
    recorded runs instead booked `code = not_run` and shipped; a fifth
    (`209a092a`) did ask, but only after F0, eight hours in, by which time
    everything had been built unreviewed.
    """
    body = _norm(_section(SKILL_DOC, "### Step 8: Full Code Review"))
    # Anchor on the OBLIGATION. Anchoring on "first action" was breakable while
    # green: open Step 8 with "Your first action here is Stage 1" and .index()
    # returns that occurrence instead (Stage-3 doubt T1).
    assert "ask for the go-ahead" in body, (
        "Step 8 must contain the obligation itself, not merely words near it"
    )
    assert "first action" in body, "…and mark it as the first action"

    ask_at = body.index("ask for the go-ahead")
    stage1_at = body.index("spec-reviewer (stage 1")
    assert ask_at < stage1_at, (
        "the ask-first instruction must appear BEFORE the Stage-1 chain in "
        f"Step 8 (ask at {ask_at}, stage 1 at {stage1_at}) — a question that "
        "comes after the cascade description reads as an afterthought"
    )


def test_step_8_guards_the_question_so_it_is_not_pointless():
    """Three guards, each from a real failure mode raised in plan review:
    no cascade required (nothing to ask about), no `Agent` tool in this agent's
    capabilities (gemini #1 — you win a 'yes' and fail anyway), permission
    already granted earlier in the session (openai #2 — do not re-ask)."""
    body = _norm(_section(SKILL_DOC, "### Step 8: Full Code Review"))
    # Deliberately exact: the loose version of this guard ("already" / "agent
    # tool" anywhere in Step 8) was already true before the fix and pinned
    # nothing.
    assert "ask only when all three hold" in body, (
        "the three conditions must be a CONJUNCTION under an imperative — "
        "'consider whether any of these apply' keeps every phrase and deletes "
        "the rule (Stage-3 doubt T2)"
    )
    assert "this agent's capabilities" in body, (
        "the question is pointless without the Agent tool in capabilities — "
        "gemini #1: you win a yes and fail anyway"
    )
    assert "already given earlier in this session" in body, (
        "openai #2: permission granted earlier in the session holds for the "
        "whole session and must not be re-requested"
    )
    assert "required for this diff" in body, (
        "no cascade required means nothing to ask about"
    )


def test_step_8_names_the_autonomous_exception_and_its_limit():
    """`--autonomous` cannot block to ask — but it only blocks ACQUIRING
    permission, not using permission the session already has (openai #3)."""
    body = _norm(_section(SKILL_DOC, "### Step 8: Full Code Review"))
    # Exact strings, no `or`. The first version read
    # `"run summary" in body or "summary" in body` — the second disjunct
    # subsumes the first, so it degraded to "the word summary appears
    # somewhere". Caught by Stage 2 on this run.
    assert "under --autonomous you cannot block to ask" in body, (
        "the clause needs its subject; deleting it left both asserted "
        "fragments in place but subject-less (Stage-3 doubt T3)"
    )
    assert "not using permission already held" in body, (
        "openai #3: --autonomous blocks ACQUIRING permission, not USING "
        "permission the session already holds — pin the limit, not the word"
    )
    assert "closing run summary (f12)" in body, (
        "the ungated pass must be surfaced on a NAMED artifact; 'run summary' "
        "alone collides with Step F's Planned Run Summary, printed before "
        "Step 8"
    )


def test_the_f12_banner_actually_carries_the_missing_pass():
    """SKILL.md Step 8 promises the ungated pass appears in the closing summary.

    Stage-3 doubt: the guard pinned the POINTER while the TARGET stayed silent.
    F12's banner is a fixed template with no review field, and the F12 actor
    never reads Step 8 — so an operator reading the banner learned nothing,
    which is exactly the half of AC3 that matters ("so the operator can lift it
    for the next run").
    """
    f12 = _SKILL_DIR / "references" / "F12.md"
    norm = _norm(f12.read_text(encoding="utf-8"))
    assert "internal cascade not run" in norm, (
        "the F12 banner must carry a conditional Reviews row naming the "
        "missing pass"
    )
    assert "omit it entirely when the cascade ran" in norm, (
        "a row that always appears stops being read — it must be conditional"
    )
