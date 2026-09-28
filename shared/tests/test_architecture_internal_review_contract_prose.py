"""Prose guards for the internal architecture-review arm — AC1-AC4.

Sibling of `test_campaign_review_contract_prose.py`: mechanical, anchor-based
assertions against the actual skill prose rather than a hand-summary of it, so
a future edit that silently drops the ordering, the spawn, or the brief
hand-off is caught here instead of only in a human re-read.

Covers `iterate-2026-09-28-architecture-review-internal-arm`'s AC1 (plan Step
5-int-arch, incl. the agent prompt's anchoring-defense prohibitions), AC2
(plan.md section + triage + gate), AC3 (iterate's mirror sub-step, medium+
gated), AC4 (the external calls re-read rather than re-author the brief).
AC5-AC8 are covered by their own existing suites (review-record schema tests,
the gate-catalog tests, the model-tier/spawn integration tests, and this
file's sibling `test_campaign_cascade_record_roundtrip.py` for the campaign
exclusion; `test_campaign_review_contract_prose.py` for AC8's
`architecture_internal` not_run wiring).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PLAN_STEP5_DOC = (
    REPO_ROOT / "plugins" / "shipwright-plan" / "skills" / "plan" / "references"
    / "step-5-external-review.md"
)
#: Step 5-int-arch's full procedure moved to its own reference file — the
#: 400-LOC runtime-prompt budget on step-5-external-review.md left no room
#: for it inline (same split pattern as build's SKILL.md -> references/*.md).
PLAN_STEP5_INT_ARCH_DOC = (
    REPO_ROOT / "plugins" / "shipwright-plan" / "skills" / "plan" / "references"
    / "step-5-int-arch.md"
)
ITERATION_PLANNING_DOC = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "references"
    / "iteration-planning.md"
)
AGENT_PROMPT_DOC = (
    REPO_ROOT / "plugins" / "shipwright-plan" / "agents"
    / "architecture-internal-reviewer.md"
)


def _norm(text: str) -> str:
    text = text.replace("—", "-").replace("’", "'")
    text = re.sub(r"[*`]+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _section(text: str, heading: str, *, stop: str = "\n---") -> str:
    """The body from `heading` up to the next `---` rule.

    Not the next `## `/numbered-step marker: the markdown template each
    section writes (`## Internal Architecture Review (...)`) starts with its
    own `## ` line, so stopping there truncates the section at its own
    template block instead of at the real next section. Every section in
    these two files is separated by a `---` rule instead, which the
    templates never contain.
    """
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find(stop)
    return heading + (rest if end < 0 else rest[:end])


def _plan_step_5_int_arch() -> str:
    return _norm(PLAN_STEP5_INT_ARCH_DOC.read_text(encoding="utf-8"))


def _plan_step_5a() -> str:
    text = PLAN_STEP5_DOC.read_text(encoding="utf-8")
    return _norm(_section(text, "## Step 5a"))


def _iterate_step_0b() -> str:
    text = ITERATION_PLANNING_DOC.read_text(encoding="utf-8")
    return _norm(_section(text, "0b. **Internal Architecture Review", stop="\n1. "))


def _iterate_step_2a() -> str:
    text = ITERATION_PLANNING_DOC.read_text(encoding="utf-8")
    return _norm(_section(text, "2a. **Architecture Review", stop="\n3. "))


# --- AC1: plan Step 5-int-arch ------------------------------------------------


def test_plan_step_5_external_review_points_at_the_int_arch_reference() -> None:
    """The pointer AND target are pinned as a pair (same reasoning as
    `test_campaign_review_contract_prose.py`'s dangling-pointer guard) — a
    dropped link would leave every assertion below green while stranding a
    reader at step-5-external-review.md's short summary."""
    text = PLAN_STEP5_DOC.read_text(encoding="utf-8")
    body = _norm(_section(text, "## Step 5-int-arch"))
    assert "step-5-int-arch.md" in body
    assert PLAN_STEP5_INT_ARCH_DOC.is_file()


def test_plan_step_5_int_arch_runs_always_right_after_5_int() -> None:
    body = _plan_step_5_int_arch()
    assert "runs exactly once, before branch a/b/c" in body
    assert "separate fresh-context pass from step 5-int" in body


def test_plan_step_5_int_arch_authors_the_brief_first() -> None:
    body = _plan_step_5_int_arch()
    assert "write the brief first" in body
    assert "architecture_brief.md" in body
    assert "step 5a, which used to author the brief" in body


def test_plan_step_5_int_arch_spawns_a_separate_agent_over_brief_and_spec() -> None:
    body = _plan_step_5_int_arch()
    assert "spawn shipwright-plan:architecture-internal-reviewer" in body
    assert "never plan.md" in body
    assert "same plan_review role" in body


def test_agent_prompt_carries_both_anchoring_defense_prohibitions() -> None:
    """Mini-plan item 1 'Anchoring defense', sharpened by this run's own
    external Branch A finding (OpenAI #3): the prompt must both name the
    forbidden files AND instruct the reviewer to ignore any prior-review
    section already present in the spec file it is handed — the second half
    is the actual fix, since the reviewer is spawned over the real spec file,
    which by the time step 0b/Step 5-int-arch runs already carries a
    populated `## Internal Plan Review` (and, at medium+, `## Self-Review`)
    section."""
    body = _norm(AGENT_PROMPT_DOC.read_text(encoding="utf-8"))
    assert (
        "do not read plan.md, any -miniplan.md file, decision_log.md, or any adr"
        in body
    ), (
        "the prompt must name plan.md/miniplan/decision_log.md/ADRs as "
        "forbidden reading, not just plan/mini-plan"
    )
    assert (
        "if the spec file you are handed already contains a "
        "## internal plan review, ## self-review, or any other prior-review "
        "section, ignore that section's content entirely" in body
    ), (
        "the prompt must instruct the reviewer to ignore a prior-review "
        "section's content already present in the spec file it is handed — "
        "naming the forbidden files alone leaves the anchoring hole open, "
        "since the spec IS the file it reads"
    )


def test_plan_step_5_int_arch_reuses_the_already_resolved_tier() -> None:
    """AC1: 'no second resolve_model_tier.py call' — the section must point
    back at Step 5-int's resolution rather than invoking the CLI a second
    time within its own body."""
    body_raw = PLAN_STEP5_INT_ARCH_DOC.read_text(encoding="utf-8")
    assert "uv run" not in body_raw, (
        "Step 5-int-arch must reuse the tier Step 5-int already resolved, "
        "not invoke resolve_model_tier.py (or any other CLI) a second time — "
        "plan.md has no run_id, so this section has no `uv run` call at all"
    )
    assert "reuse the tier step 5-int already resolved" in _norm(body_raw)


# --- AC2: plan.md section, triage, gate ---------------------------------------


def test_plan_internal_architecture_review_section_shape() -> None:
    body = _plan_step_5_int_arch()
    assert "## internal architecture review (architecture-internal-reviewer)" in body
    assert "ran:" in body
    assert "overwriting the existing section in place" in body


def test_plan_internal_architecture_review_triage_and_gate() -> None:
    body = _plan_step_5_int_arch()
    assert "fix" in body and "disclose" in body and "decline" in body
    assert "scope-ratchet guard" in body
    assert "stops and asks the user" in body
    assert "plan.architecture-internal-review-high-severity-declined" in body


def test_plan_internal_architecture_review_logs_its_own_decision_log_section() -> None:
    body = _plan_step_5_int_arch()
    assert "internal architecture review - {split_name}" in body


# --- AC3: iterate's mirror sub-step, medium+ gated ----------------------------


def test_iterate_step_0b_runs_right_after_the_plan_review_substep_medium_plus() -> None:
    body = _iterate_step_0b()
    assert "medium+ only" in body
    assert "never runs for trivial/small" in body
    assert "immediately after step 0" in body


def test_iterate_step_0b_writes_the_brief_and_the_spec_section() -> None:
    body = _iterate_step_0b()
    assert "architecture_brief.md" in body
    assert "## internal architecture review" in body
    assert "iterate adr" in body


def test_iterate_step_0b_reconciles_the_pending_row_before_skipping(
) -> None:
    """F11 local PR-review preflight BLOCK: a crash between writing the
    spec section (`Ran: yes`) and recording the architecture_internal row
    left an early 'skip straight to step 1' rule reachable BEFORE a
    separately-stated resume-reconciliation rule, so a resumed run could
    skip past step 1 with the row still pending -- and check_review_record
    (F11) fails closed on that. The reconciliation must be stated as part
    of the same rule, ordered before the skip, not as a later paragraph a
    model already committed to skipping might never reach."""
    body = _iterate_step_0b()
    reconcile_idx = body.index("reconcile the review-record row first")
    skip_idx = body.index("skip straight to step 1")
    assert reconcile_idx < skip_idx, (
        "reconciling the pending row must be ordered BEFORE the skip "
        "instruction, not stated afterward where a model already "
        "following the skip could miss it"
    )
    assert "crash between writing the spec section" in body
    assert "do not re-spawn" in body


def test_iterate_step_0b_spawns_the_agent_over_a_sanitized_spec_copy() -> None:
    """The iterate spec is the ONE document that carries `## Internal Plan
    Review` by the time this step runs (unlike the plan side, where that
    section only ever lands in plan.md) — handing the agent that raw path
    would leak the rationale its fresh-context design exists to withhold.
    The fix is code, not prose: `prepare_architecture_internal_spec.py`
    must run before the spawn, and the spawn must name its output, never
    `{iterate_spec_path}`, as the agent's input."""
    body = _iterate_step_0b()
    assert "prepare_architecture_internal_spec.py" in body
    assert "over the architecture brief + that sanitized copy" in body
    assert "never the real iterate spec" in body


def test_iterate_step_0b_never_writes_decision_log_directly() -> None:
    """Iterate defers all decision logging to F3's decision-drop mechanism —
    unlike the plan side, step 0b must not name a direct decision_log.md
    write of its own."""
    text = ITERATION_PLANNING_DOC.read_text(encoding="utf-8")
    body_raw = _section(text, "0b. **Internal Architecture Review", stop="\n1. ")
    assert "decision_log.md" not in body_raw, (
        "iterate's internal architecture review sub-step must not write "
        "decision_log.md directly — outcomes go through the ADR + F3's "
        "decision-drop mechanism"
    )


# --- AC4: the external calls re-read, not re-author, the brief ---------------


def test_plan_step_5a_re_reads_the_brief_instead_of_authoring_it() -> None:
    body = _plan_step_5a()
    assert "re-read the brief step 5-int-arch already wrote" in body
    assert "--plan-file" in body and "usage error" in body


def test_iterate_step_2a_re_reads_the_brief_instead_of_authoring_it() -> None:
    body = _iterate_step_2a()
    assert "re-read the brief step 0b already wrote" in body
    assert "--plan-file" in body and "usage error" in body
