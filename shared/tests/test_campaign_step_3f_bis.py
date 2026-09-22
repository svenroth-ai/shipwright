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
    step_3g as _step_3g,
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

    Pre-R3, 3f-bis was conditional end to end: the skip path recorded no
    `reviewed_head` at all, and 3g's pin was conditional on 3f-bis having
    actually pushed one. R3 (unit-scoped attribution) made the pin itself
    UNCONDITIONAL — it runs at the top of 3f-bis regardless of the trigger,
    passing `--review-skipped` on the skip path — specifically so a
    below-threshold unit still gets a `reviewed_head` file for 3g to check.

    3g's `[ -f ... ]` read is now the MECHANISM, not defensive tolerance
    (doubt-round, high): the prior wording — "tolerate a missing legacy file"
    — described a gap the doubt-reviewer disproved directly, citing a
    "no PR merges unpinned" `references/iteration-reviews.md` acceptance
    rule that does not exist in that file. Since the unconditional pin at
    3f-bis is itself `|| STRICT-STOP`-guarded, every unit that reaches this
    line in 3g already has a pin, reviewed or skipped; an absent file now
    means an earlier guard should already have stopped the loop, so 3g
    STOPS rather than merging unpinned.
    """
    raw = CAMPAIGN_DOC.read_text(encoding="utf-8")
    assert 'iteration-reviews.md' not in raw or "no PR merges unpinned" not in raw, (
        "must not cite a 'no PR merges unpinned' acceptance rule in "
        "iteration-reviews.md that does not exist there"
    )
    step_3g = _step_3g()
    assert '[ -f "$run_dir/reviewed_head" ] || strict-stop' in step_3g, (
        "3g must fail closed (STRICT-STOP) when the pin file is absent, not "
        "silently merge with an empty head_pin"
    )
    step = _step_3f_bis()
    assert "--review-skipped" in step, (
        "the skip branch must pass --review-skipped to the unconditional pin, "
        "so a below-threshold unit still gets a reviewed_head file (R3)"
    )
    assert "still deliver" in step, (
        "the skip branch must say a below-threshold sub-iterate still delivers"
    )


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
    # reported the guarded command as unguarded. R3 scoped every git call
    # here with an explicit `-C "{project_root}"` (campaign-mode.md must
    # never rely on an unstated cwd once R5a gives each unit its own
    # worktree), so the literal command form gained that prefix too.
    assert 'push || strict-stop' in step, (
        "`git push` in 3f-bis must be checked — a promotion that does not "
        "reach the remote must STOP the loop, not shorten it"
    )
    push_at = step.index("push || strict-stop")
    assert 'git -c "{project_root}"' in step[max(0, push_at - 40):push_at], (
        "the push must be explicitly scoped to {project_root}, not an "
        "unstated cwd (R3)"
    )
    commit_at = step.index('commit -m "chore(review): record the delegated cascade')
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


def test_run_dir_and_gh_pr_view_are_unit_scoped_in_3f_bis_and_3g():
    """External plan review (openai high / glm medium): R3's spec names
    `run_dir` and "the `gh pr view` branch resolution" among the exact call
    sites that must become unit-scoped (`{project_root}`), same set for 3g.
    Every OTHER call in this step already got `git -C "{project_root}"`; these
    two used a bare relative path / a bare `gh pr view` that resolves from
    cwd, which is exactly the unstated-cwd assumption the spec forbids."""
    scoped_run_dir = 'run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"'
    scoped_gh = 'cd "{project_root}" && gh pr view "{branch}"'
    for step, label in ((_step_3f_bis(), "3f-bis"), (_step_3g(), "3g")):
        assert scoped_run_dir in step, f"{label} must scope run_dir to {{project_root}}"
        assert scoped_gh in step, (
            f"{label}'s `gh pr view \"{{branch}}\"` must not rely on an unstated cwd"
        )


def test_step_3f_bis_pin_invocation_is_checked_not_prose_only():
    """Doubt-round, high: the unit-scoped pin invocation was the only checked
    command in 3f-bis with no inline `|| STRICT-STOP` — prose discipline
    alone is not a guard. Mutation-probed: delete the trailing guard from the
    pin call and this fails."""
    step = _step_3f_bis()
    assert "pin_json=$(uv run" in step, (
        "the pin call must capture its --json output for the diff_head "
        "equality check below"
    )
    pin_json_at = step.index("pin_json=$(uv run")
    close_at = step.index(")) || strict-stop", pin_json_at)
    assert close_at > pin_json_at, (
        "the pin invocation must be checked inline (`|| STRICT-STOP`), not "
        "left to prose discipline alone"
    )


def test_step_3f_bis_asserts_the_pin_certifies_the_diff_that_was_reviewed():
    """Doubt-round, medium: the diff 3f-bis reviews and the tree pin()
    certifies were resolved independently, with no equality check between
    them — a divergence would let the pin certify a diff nobody reviewed."""
    step = _step_3f_bis()
    assert "diff_head=$(git" in step, (
        "3f-bis must capture diff_head at the point the diff is computed"
    )
    assert '.reviewed_head <<<"$pin_json")" = "$diff_head"' in step, (
        "3f-bis must assert the pin's reviewed_head equals diff_head before "
        "trusting the review as attributed to this diff"
    )


def test_step_3f_bis_records_shipped_head_after_the_record_commit_lands():
    """Doubt-round, high: `shipped_head` must be recorded into the pin once
    the reviews.json commit is actually pushed — otherwise `verify --against
    shipped_head` has nothing to check but a null field."""
    step = _step_3f_bis()
    assert "--mode ship" in step, (
        "3f-bis must call check_review_attribution.py --mode ship after the "
        "reviews.json push"
    )
    # "--mode ship" is also named in explanatory prose both before AND after
    # the actual invocation — anchor on the unique CLI-invocation prefix
    # (the command form itself), not the bare flag text.
    invocation = 'check_review_attribution.py" --mode ship'
    assert invocation in step, (
        "the actual --mode ship command invocation must be present"
    )
    ship_at = step.index(invocation)
    assert "--shipped-head" in step[ship_at:ship_at + 400], (
        "the ship call must pass --shipped-head"
    )
    assert "|| strict-stop" in step[ship_at:ship_at + 400], (
        "the ship call must be checked, not left unguarded"
    )


def test_step_3f_bis_rederives_run_dir_and_pr_url_after_the_cascade_spawns():
    """Doubt-round, round 2, medium: `run_dir` and `pr_url` were set BEFORE
    the a/b/c review-cascade spawns and this block runs AFTER them — the ONLY
    two values in this step that genuinely cross a spawn boundary. Shell
    variables do not survive across separate tool calls, so this block must
    re-derive both explicitly rather than trust the earlier assignment."""
    step = _step_3f_bis()
    assert 'run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"' in step, (
        "3f-bis must re-derive run_dir after the cascade spawns, not reuse a "
        "shell variable set before them"
    )
    assert 'pr_url=$(cd "{project_root}" && gh pr view "{branch}" --json url -q .url)' in step, (
        "3f-bis must re-derive pr_url after the cascade spawns, not reuse a "
        "shell variable set before them"
    )


def test_step_3f_bis_ships_before_writing_the_legacy_reviewed_head_file():
    """Doubt-round, round 2, medium: ship-then-write, not write-then-ship — a
    STRICT-STOPped ship must never leave the legacy `reviewed_head` file
    holding a SHA the guard refused, which a human resuming at 3g would
    otherwise `--match-head-commit` on."""
    step = _step_3f_bis()
    invocation = 'check_review_attribution.py" --mode ship'
    legacy_write = 'echo "$shipped_head" > "$run_dir/reviewed_head"'
    assert invocation in step and legacy_write in step
    assert step.index(invocation) < step.index(legacy_write), (
        "the --mode ship call must run BEFORE the legacy reviewed_head file "
        "is written"
    )


def test_step_3g_never_merges_without_a_pin_file():
    """The spec's acceptance criterion: no PR merges unpinned. Mutation-probed
    against 3g's own text — delete the STRICT-STOP guard or the merge's use
    of `$head_pin` and this fails."""
    step = _step_3g()
    assert '[ -f "$run_dir/reviewed_head" ] || strict-stop' in step, (
        "3g must STRICT-STOP when no pin file exists, not merge with an "
        "empty --match-head-commit"
    )
    merge_at = step.index("gh pr merge")
    assert "$head_pin" in step[merge_at:merge_at + 120], (
        "the merge command must actually use $head_pin — a merge call that "
        "dropped it would merge unpinned even with the guard above intact"
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
