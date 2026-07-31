"""Guards for campaign loop step `3f-bis` — the delegated review cascade.

Split out of `test_campaign_review_contract_prose.py`, which reached 354 lines
against a 300-line limit when these were added. They are a cohesive group with
their own subject: the step the campaign orchestrator runs between recording a
sub-iterate's result and merging its PR.

What they exist to stop is specific. Every assertion below was VACUOUS in the
first draft, because the step body was located by matching a prose mention of
"3f-bis" rather than the step label — `--force` was satisfied by the header
note and `STRICT-STOP` by step 3f's own. Each guard here has been
mutation-probed: delete its subject from the step and it fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _campaign_prose_harness import (  # noqa: E402
    CAMPAIGN_DOC,
    REPO_ROOT,
    step_3f_bis as _step_3f_bis,
)


def test_step_3f_bis_runs_the_cascade_in_the_order_the_gate_enforces():
    """`spec` is the HARD-GATE: a completed `code` over a non-completed `spec`
    FAILS `check_review_record` (proved in
    `test_campaign_cascade_record_roundtrip.py`). So the step must name Stage 1
    first — otherwise it prescribes a sequence that reds its own sub-iterate."""
    step = _step_3f_bis()
    spec_at, code_at = step.find("spec-reviewer"), step.find("code-reviewer")
    doubt_at = step.find("doubt-reviewer")
    assert min(spec_at, code_at, doubt_at) >= 0, (
        "3f-bis must name all three cascade stages"
    )
    assert spec_at < code_at < doubt_at, (
        "3f-bis must run spec-reviewer (HARD-GATE) before code-reviewer, and "
        "doubt-reviewer last — the gate rejects any other order"
    )


def test_step_3f_bis_promotes_with_force():
    """The runner already closed those rows and a closed row is immutable, so
    without `--force` every promotion exits 3."""
    assert "--force" in _step_3f_bis(), (
        "3f-bis must tell the orchestrator to use --force"
    )


def test_step_3f_bis_routes_a_reject_to_the_existing_non_delivery_path():
    """A Stage-1 REJECT must STRICT-STOP, not merge anyway. The loop already
    has one way to express non-delivery (3f exit 3 / a failed check at 3g);
    3f-bis reuses it rather than inventing a second."""
    assert "strict-stop" in _step_3f_bis(), (
        "a rejected spec-compliance verdict is a non-delivery and must "
        "STRICT-STOP the loop"
    )


def test_step_3f_bis_does_not_break_delivery_when_the_cascade_is_skipped():
    """A below-threshold sub-iterate must still DELIVER.

    3f-bis is conditional, so on the skip path it pushes nothing. An
    unconditional head pin in 3g therefore refused the merge, which 3g
    classifies as non-delivery — every below-threshold sub-iterate would have
    STRICT-STOPped the campaign it used to deliver (Stage-1 re-gate REJECT).
    The pin must be conditional on 3f-bis having actually pushed.
    """
    raw = CAMPAIGN_DOC.read_text(encoding="utf-8")
    assert '[ -f "$run_dir/reviewed_head" ]' in raw, (
        "3g must pin the merge head ONLY when 3f-bis recorded one; an "
        "unconditional pin kills every sub-iterate that skips the cascade"
    )
    assert "write no `reviewed_head`" in _step_3f_bis() or (
        "write no reviewed_head" in _step_3f_bis()
    ), "the skip branch must say it records no head, so 3g stays unpinned"


def test_the_head_pin_crosses_steps_in_a_file_not_a_shell_variable():
    """3f-bis and 3g are separate steps, so a fresh Bash call starts with an
    empty environment. A `$sha` set in 3f-bis expands to "" in 3g, which
    silently UNPINS the merge in the exact window the step calls dangerous —
    and skip-path and failure-path become indistinguishable (Stage-3 doubt).
    """
    raw = CAMPAIGN_DOC.read_text(encoding="utf-8")
    assert "reviewed_head" in raw, "the pin must cross steps as a file"
    assert 'sha=""' not in raw, (
        "the head pin must not rely on a shell variable surviving between steps"
    )
    assert "${sha:+" not in raw, (
        "conditional expansion of a cross-step shell variable is the bug, not "
        "the fix — it silently yields 'unpinned' when the variable is gone"
    )


def test_step_3f_bis_fails_closed_when_the_promotion_does_not_ship():
    """An unchecked `git commit` that the pre-commit hook blocks leaves the
    local record saying `completed` while main still says `not_run` — the
    cascade silently un-shipped, and the loop merging anyway (Stage-3 doubt)."""
    step = _step_3f_bis()
    # Anchor on the COMMAND forms, not the prose that explains the hazard —
    # matching a bare "git commit" found the explanatory sentence first and
    # reported the guarded command as unguarded.
    assert "git push || strict-stop" in step, (
        "`git push` in 3f-bis must be checked — a promotion that does not "
        "reach the remote must STOP the loop, not shorten it"
    )
    commit_at = step.index("git commit -m")
    assert "|| strict-stop" in step[commit_at:commit_at + 160], (
        "`git commit` in 3f-bis must be checked — a commit the pre-commit "
        "hook blocks would leave the record un-shipped and the loop merging on"
    )


def test_step_3f_bis_bounds_its_wait():
    """An unbounded `until` loop is a third outcome the campaign has no name
    for: neither delivered nor stopped, and the state an operator is least
    likely to notice (Stage-3 doubt)."""
    step = _step_3f_bis()
    assert "until [" not in step, "the head-catch-up wait must not be unbounded"
    assert "seq 1" in step, "the wait must have an attempt cap"


def test_step_3f_bis_computes_its_own_trigger_from_the_diff():
    """The runner has no Stage-2 Repo Scout — it classifies from its spec text,
    so diff-driven flags (`cross_component`, `touches_*`) are structurally never
    set for it. Inheriting that verdict would make this gate NARROWEST on the
    framework surface it exists to protect (Stage-3 doubt)."""
    step = _step_3f_bis()
    assert "merge-base" in step, "the trigger must be computed from the diff"
    assert "repo scout" in step, (
        "the step must say WHY it recomputes rather than inheriting — the "
        "reason is the runner's missing Stage-2 scout"
    )


def test_a_stage_1_reject_is_not_recorded_as_completed():
    """The native Stage-1 payload stores `spec_citations` and drops `verdict`,
    so a `completed` REJECT is byte-indistinguishable from a PASS to the next
    reader. The PR is left OPEN for a human — who would see a green record
    (Stage-3 doubt)."""
    step = _step_3f_bis()
    tail = step[step.index("reject"):] if "reject" in step else ""
    assert "not_run" in tail, (
        "a Stage-1 REJECT must be recorded not_run with a disposition naming "
        "the rejection, never `completed`"
    )


def test_no_doc_still_calls_browser_verify_f2():
    """`F2` means `architecture.md`. The runner reused the label for Browser
    Verify, which hid F2's absence for as long as it did; `hooks-and-pipeline.md`
    is the repo's SSoT for what fires when and carried the same collision in
    four rows (Stage-2 review). Fixing one surface and leaving the other makes
    the repo assert both readings at once.
    """
    docs = REPO_ROOT / "docs" / "hooks-and-pipeline.md"
    text = docs.read_text(encoding="utf-8")
    assert "F2 Browser Verify" not in text, (
        "hooks-and-pipeline.md still calls Browser Verify F2"
    )
    assert "sub-iterate-runner F2" not in text, (
        "hooks-and-pipeline.md still labels the runner's Browser Verify as F2"
    )
