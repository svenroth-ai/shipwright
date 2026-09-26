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

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _campaign_prose_harness import (  # noqa: E402
    CAMPAIGN_DOC,
    REPO_ROOT,
    step_3f_bis as _step_3f_bis,
    step_3g as _step_3g,
)

# `norm()` (in `_campaign_prose_harness.py`) lowercases the whole step body, so
# every assertion below reads `-c` where the doc itself writes `-C` (`git -C`,
# a real and DIFFERENT git flag from `git -c key=val`) and `headrefname` where
# the doc writes `headRefName`. This is a normalisation artifact of the
# harness, not a typo in either the doc or the tests (code-review round 4).


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


def test_pin_still_valid_is_persisted_to_a_file_not_a_bare_shell_variable():
    """Tier-3 review, R5b round 18, blocking: `pin_still_valid` was set at
    the top of the HEAD-check block and read again at the `built ->
    reviewed` promotion gate ~35 lines of prose later, as a bare shell
    variable -- unlike every other value that crosses a comparable distance
    in this step (`shipped_head`, `diff_head`, `fires`, `unit_wt`), it had
    never been given the `$run_dir`-backed dual-write treatment, so it was
    not provably same-call over that gap. Every write must also persist to
    `$run_dir/pin_still_valid`, and the gate must re-read from that file."""
    step = _step_3f_bis()
    assert step.count('echo true > "$run_dir/pin_still_valid"') == 1, (
        "the initial pin_still_valid=true assignment must also be persisted "
        "to $run_dir/pin_still_valid"
    )
    assert step.count('echo false > "$run_dir/pin_still_valid"') == 2, (
        "BOTH invalidate branches (HEAD-mismatch and commit-parent-mismatch) "
        "must persist pin_still_valid=false to $run_dir/pin_still_valid"
    )
    gate_at = step.index('pin_still_valid=$(cat "$run_dir/pin_still_valid"')
    if_at = step.index('if [ "$pin_still_valid" = "true" ]; then', gate_at)
    assert gate_at < if_at, (
        "the built -> reviewed promotion gate must re-read pin_still_valid "
        "from its file immediately before branching on it, not trust a bare "
        "shell variable carried from the earlier block"
    )


def test_step_3f_bis_fails_closed_when_the_promotion_does_not_ship():
    """An unchecked `git commit` that the pre-commit hook blocks leaves the
    local record saying `completed` while main still says `not_run` — the
    cascade silently un-shipped, and the loop merging anyway (Stage-3 doubt)."""
    step = _step_3f_bis()
    # Anchor on the COMMAND forms, not the prose that explains the hazard —
    # matching a bare "git commit" found the explanatory sentence first and
    # reported the guarded command as unguarded. R3 scoped every git call
    # here with an explicit `-C`, never a bare `git` relying on cwd
    # (campaign-mode.md must never rely on an unstated cwd once R5a gives
    # each unit its own worktree). A fresh spec-review round on this same
    # sub-iterate then found the scoping was fallback-only — every named
    # call site read the literal `{project_root}` template value, never a
    # genuinely resolved unit worktree — so it now reads `$unit_wt`,
    # resolved from `loop_state.json`'s row by 3f-bis's own jq lookup (pin
    # never writes this) and dual-written to a file for this exact
    # cross-spawn boundary.
    assert 'push || strict-stop' in step, (
        "`git push` in 3f-bis must be checked — a promotion that does not "
        "reach the remote must STOP the loop, not shorten it"
    )
    push_at = step.index("push || strict-stop")
    assert 'git -c "$unit_wt"' in step[max(0, push_at - 40):push_at], (
        "the push must be explicitly scoped to $unit_wt (this unit's own "
        "worktree), not the bare {project_root} fallback value (R3)"
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
    sites that must become unit-scoped, same set for 3g. Every OTHER call in
    this step already got an explicit `-C`; these used a bare relative
    path / a bare `gh pr view` that resolves from cwd, which is exactly the
    unstated-cwd assumption the spec forbids.

    `run_dir` itself is deliberately still anchored at `{project_root}` in
    BOTH steps — NOT because resolving it any other way would be circular
    ($unit_wt is provably resolvable from `loop_state.json` before anything
    else runs, per the round-3/round-4 fixes below), but because it is the
    campaign's own bookkeeping location: the runner writes `DONE`/`result.json`
    there (sub-iterate-runner.md steps 3d/3e) and `pin` roots its `runs/` tree
    there via `--project-root`, so a unit-scoped `run_dir` would split a
    single unit's artifacts across two directories depending on which step
    wrote them (code-review round 4, low — replaces a disproven rationale).
    A second fresh spec-review round
    found the round-1 fix incomplete: it scoped 3g's `gh pr view` but left
    BOTH of 3f-bis's own `gh pr view` calls (the pre-pin resolution and the
    post-cascade re-derivation) at `{project_root}` — the spec names "the
    `gh pr view` branch resolution" as a 3f-bis call site too, not only 3g's.
    Both are now unit-scoped."""
    scoped_run_dir = 'run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"'
    for step, label in ((_step_3f_bis(), "3f-bis"), (_step_3g(), "3g")):
        assert scoped_run_dir in step, f"{label} must scope run_dir to {{project_root}}"
    assert 'cd "$unit_wt" && gh pr view "{branch}" --json url,id,headrefname,baserefname' in _step_3f_bis(), (
        "3f-bis's pre-pin gh pr view must resolve $unit_wt (from the "
        "loop_state.json jq lookup), not rely on {project_root}"
    )
    assert 'cd "$unit_wt" && gh pr view "{branch}" --json url -q .url' in _step_3f_bis(), (
        "3f-bis's post-cascade gh pr view re-derivation must resolve "
        "$unit_wt, not stay anchored at {project_root}"
    )
    assert 'cd "$unit_wt" && gh pr view "{branch}"' in _step_3g(), (
        "3g's gh pr view branch resolution is a named unit-scoped call site "
        "and must resolve $unit_wt, not rely on an unstated cwd or the bare "
        "{project_root} fallback value"
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


def test_step_3f_bis_computes_the_diff_itself_against_unit_wt():
    """Code-review round 4, medium: the round-3 fix's headline change — scoping
    `diff_head`/`$diff` to `$unit_wt` instead of `{project_root}` — had no
    test guarding it. `test_step_3f_bis_asserts_the_pin_certifies_the_diff_...`
    only checked `"diff_head=$(git" in step`, satisfied verbatim by
    `git -C "{project_root}"` too; reverting the diff computation back to
    `{project_root}` left every prior test in this file green. This sub-iterate
    was REJECTed twice already for exactly this class of silent
    `{project_root}` call site, so the diff gets its own mutation-probed
    guard: delete `$unit_wt` from either the rev-parse or the diff line and
    this fails."""
    step = _step_3f_bis()
    assert 'diff_head=$(git -c "$unit_wt" rev-parse head)' in step, (
        "diff_head must be captured from $unit_wt, not {project_root}"
    )
    assert 'diff=$(git -c "$unit_wt" diff "$base"..."$diff_head")' in step, (
        "the diff itself must be computed against $unit_wt, not {project_root}"
    )


def test_step_3f_bis_resolves_unit_wt_before_pin_and_verifies_pins_agreement():
    """Spec-review round 2: the diff and the pre-pin `gh pr view` must not
    wait for pin's own answer, since `worktree` is independently readable
    from `loop_state.json` before pin ever runs. Comparing only `$unit_wt`'s
    HEAD sha against `diff_head` would let a pin that resolved a DIFFERENT
    worktree path to the same HEAD sha slip through unnoticed — the resolved
    PATH itself must be checked, not just its tip."""
    step = _step_3f_bis()
    resolve_at = step.find('unit_wt=$(jq -r --arg id "{id}"')
    pin_at = step.find("pin_json=$(uv run")
    assert resolve_at >= 0, (
        "3f-bis must resolve $unit_wt from loop_state.json via jq before pin runs"
    )
    assert resolve_at < pin_at, (
        "the pre-pin $unit_wt resolution must precede the pin invocation"
    )
    assert 'unit_wt="{project_root}"' in step[resolve_at:pin_at], (
        "the pre-pin resolution must fall back to {project_root} when the "
        "loop_state.json row carries no worktree field (a pre-R2 row, or a "
        "warned lease-touch failure)"
    )
    assert 'pin_wt=$(jq -r .worktree <<<"$pin_json")' in step, (
        "3f-bis must capture pin's own self-reported worktree"
    )
    assert '[ "$pin_wt" = "$unit_wt" ] || strict-stop' in step, (
        "3f-bis must STRICT-STOP when pin's self-reported worktree diverges "
        "from the $unit_wt already used for the pre-pin gh pr view and diff"
    )


def test_step_3f_bis_rederives_run_dir_before_each_boundary_crossing_read():
    """Spec-review round 4 (blocking): round 4's dual-write/re-read fix for
    `$unit_wt`/`$diff_head`/`$fires` was cosmetic — every re-read dereferenced
    `$run_dir` itself, a shell variable assigned only once, on the near side
    of the same spawn boundary the fix exists to survive. `run_dir` is a
    template-string rebuild, not a persisted value, so every block that reads
    one of the boundary-crossing files must re-derive it fresh first. This
    counts one `run_dir=` re-derivation immediately before EVERY `unit_worktree`
    read site in 3f-bis's own body (the pin-block re-read, the promote-rows
    block, the ship-path block, and the Stage-1-REJECT branch, which never
    reaches the ship path's own re-derivation) — delete any one of the
    matching `run_dir=` lines and this fails."""
    step = _step_3f_bis()
    rederive = 'run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"'
    read = 'cat "$run_dir/unit_worktree"'
    positions = []
    idx = 0
    while True:
        idx = step.find(read, idx)
        if idx < 0:
            break
        positions.append(idx)
        idx += len(read)
    assert len(positions) >= 4, (
        "3f-bis must have at least 4 unit_worktree read sites (pin block, "
        "promote-rows, ship-path, Stage-1-REJECT branch)"
    )
    for pos in positions:
        preceding = step[max(0, pos - 400):pos]
        assert rederive in preceding, (
            f"unit_worktree read at offset {pos} must be preceded by a fresh "
            "run_dir= re-derivation within the same block, not a bare read "
            "through a possibly-empty $run_dir"
        )


def test_step_3f_bis_merge_base_failure_is_checked():
    """Code-review round 4/5, low: an unchecked `merge-base` failure collapses
    the diff range to `...{sha}` — an EMPTY diff for `diff_head==HEAD` — which
    fails OPEN (fires=0, cascade skipped, unit merges unreviewed). Delete the
    `|| STRICT-STOP` and this fails."""
    step = _step_3f_bis()
    assert 'base=$(git -c "$unit_wt" merge-base origin/{default} "$diff_head") || strict-stop' in step, (
        "merge-base must be captured explicitly and STRICT-STOP-guarded "
        "before it is used to build the diff range"
    )


def test_step_3f_bis_fires_is_a_real_assignment_not_a_bare_variable_read():
    """Code-review round 5, CRITICAL: `echo "$fires" > "$run_dir/fires"`
    presupposed a shell variable `$fires` that no command in the step ever
    assigned — the fires decision is a model judgement read from the diff's
    own text, described only in prose ("set fires=1 ... else fires=0"), never
    a shell computation. The literal snippet therefore wrote an EMPTY file
    unconditionally, independent of any spawn-boundary issue — worse than the
    pre-fix behavior, where `fires` was a live, correctly-set variable. The
    doc's literal next command must be an ACTUAL assignment of the digit just
    decided, and the re-read must fail closed on anything else. Round 6:
    reworded the placeholder to `fires=<1 or 0>` so a reader following the
    snippet literally cannot default to always writing `1`."""
    step = _step_3f_bis()
    assert "fires=<1 or 0>" in step, (
        "the fires decision must be written as an explicit placeholder "
        "assignment substituting the judged digit, not a bare $fires with "
        "nothing upstream ever assigning it, and not a hardcoded fires=1 "
        "that a reader could apply unconditionally"
    )
    fires_write_at = step.find('echo "$fires" > "$run_dir/fires"')
    assert fires_write_at >= 0, "3f-bis must dual-write the fires decision"
    # Round 11 (D5) deliberately interposes the mechanical `-gt 100` floor
    # (`test_step_3f_bis_fires_line_count_is_computed_not_judged` asserts its
    # exact presence/order) between the judgement and the write, so the
    # window widens from 120 to 250 to admit that one tracked statement —
    # still tight enough that an untracked, silent interposition would fail.
    assert "fires=<1 or 0>" in step[max(0, fires_write_at - 250):fires_write_at], (
        "the literal fires=<1 or 0> assignment must precede the dual-write "
        "with nothing but the tracked mechanical floor between them, not "
        "float disconnected from it"
    )
    reread_at = step.find('fires=$(cat "$run_dir/fires"')
    assert reread_at >= 0, "3f-bis must re-read $fires from the dual-write file"
    assert '[ "$fires" = "1" ] || [ "$fires" = "0" ] || strict-stop' in step[reread_at:reread_at + 200], (
        "the fires re-read must fail closed (STRICT-STOP) when the value is "
        "neither 1 nor 0 -- anything else means the write above never "
        "happened, which must not silently read as 'did not fire'"
    )


def test_step_3f_bis_rederives_run_dir_before_the_fires_write():
    """Spec-review round 6 (blocking): round 5's run_dir re-derivation rule
    covered every READ site but not the fires WRITE site. The fires judgement
    itself is what forces the fresh Bash call the step's own top-of-block
    warning names, so `$run_dir` from the block that resolves `$unit_wt` and
    computes the diff is gone by the time `echo "$fires" > "$run_dir/fires"`
    runs too — the write silently targeted `/fires`, and the fail-closed
    re-read guard then STRICT-STOPped every unit on the happy path. Delete
    the run_dir= rebuild immediately preceding the fires write and this
    fails. Lookback window matches the sibling read-site test's 400 chars
    (code-review round 6-verify, low: this test's original 200-char window
    left only ~65 chars of slack before a comment-length change would
    spuriously redden it)."""
    step = _step_3f_bis()
    rederive = 'run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"'
    fires_write_at = step.find('echo "$fires" > "$run_dir/fires"')
    assert fires_write_at >= 0, "3f-bis must dual-write the fires decision"
    preceding = step[max(0, fires_write_at - 400):fires_write_at]
    assert rederive in preceding, (
        "the fires write must be preceded by a fresh run_dir= re-derivation "
        "within the same block, not a bare write through a possibly-empty "
        "$run_dir carried from an earlier shell call"
    )


def test_step_3f_bis_every_run_dir_use_opens_within_its_own_block():
    """Spec-review/code-review rounds 5-7: three consecutive rounds each
    fixed the one `$run_dir` use a reviewer had just named (the fires write,
    then the promote-rows/ship/REJECT-path re-reads), and each time a
    DIFFERENT use in a DIFFERENT contiguous block turned out to have the
    identical gap. Round 7 tried to close the class with a rule claiming NO
    site may rely on same-call reasoning — but 3f-bis genuinely has several
    reads sharing one opening rebuild within a single block (the pin-block
    re-read group; the bounded-wait loop), and 3g genuinely IS one block
    start to finish, so an unconditional per-site rule was never true of the
    doc it governed (round 8: reworded to the rule actually implemented —
    exactly one rebuild opens each contiguous block, a block ends only at a
    model judgement or an Agent-tool spawn).

    3f-bis's window is a short, tight lookback: a use far from its OWN
    block's opening rebuild is exactly the defect this test exists to
    catch. 3g needs a different check, not a wider window standing in for
    "no check at all": 3g's own governing rebuild sits up to ~1300
    normalized chars before its farthest use (measured directly, NOT the
    ~450 estimated when this test was first written — round 8 verified the
    real number before picking a window), so any window generous enough to
    pass today's genuine single-block text is too generous to catch
    anything. Instead, 3g is asserted to have EXACTLY ONE `run_dir=`
    rebuild, and it must precede every use — the moment a future edit adds
    a SECOND rebuild to 3g (the natural signal that a second block/boundary
    was recognized), this assertion breaks and forces a conscious decision
    about that block's own lookback, rather than silently staying vacuous
    forever the way an unconditional "unbounded from start" window did."""
    rederive = 'run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"'
    usage = re.compile(r'"\$run_dir/')

    # 3f-bis covers pin-scope writes, the pin-block re-read, promote-rows,
    # the ship block (incl. the bounded wait) and the REJECT path.
    step = _step_3f_bis()
    positions = [m.start() for m in usage.finditer(step)]
    assert len(positions) >= 8, (
        f"expected at least 8 $run_dir/-prefixed usages in 3f-bis — got "
        f"{len(positions)}, which means the scan itself is broken, not "
        "that the step shrank"
    )
    window = 500
    for pos in positions:
        preceding = step[max(0, pos - window):pos]
        assert rederive in preceding, (
            f"3f-bis: the $run_dir/-prefixed use at offset {pos} must be "
            "preceded within the same block by a fresh run_dir= "
            "re-derivation — a bare use through a possibly-stale $run_dir "
            "carried from an earlier shell call is exactly the defect "
            "class that drew three consecutive REJECTs on this step"
        )

    # 3g: a separate, much smaller step that is genuinely one continuous
    # Bash call — no model judgement, no Agent-tool spawn anywhere in its
    # body (round 9: `gh pr checks --watch` gained its own `|| STRICT-STOP`,
    # closing the last spot where a human/model had to read an exit code
    # and decide rather than the shell enforcing it mechanically). Enforced
    # structurally (one rebuild, opening the step) instead of via a lookback
    # window, so a future SECOND rebuild — the sign that 3g stopped being
    # one block — cannot slip past silently. Residual gap, accepted: a
    # future boundary added WITHOUT a second rebuild (careless, not the
    # "right" fix) is invisible to this assertion — it only catches the
    # case where an author does add the second rebuild.
    step_3g = _step_3g()
    positions_3g = [m.start() for m in usage.finditer(step_3g)]
    # R5b: floor 3 -> 2 (head_pin now reads verify's `.pin.shipped_head`).
    assert len(positions_3g) >= 2, (
        f"expected at least 2 $run_dir/-prefixed usages in 3g — got {len(positions_3g)}, "
        "which means the scan itself is broken, not that the step shrank"
    )
    rebuild_count = step_3g.count(rederive)
    assert rebuild_count == 1, (
        f"3g: expected exactly one run_dir= rebuild (the step is asserted "
        f"to be a single continuous Bash call) — found {rebuild_count}. "
        "If 3g now genuinely has more than one shell block, this test's "
        "single-rebuild assumption is stale and must be replaced with a "
        "real lookback window sized to the new block boundaries, not "
        "widened blindly."
    )
    rebuild_pos = step_3g.find(rederive)
    assert all(pos > rebuild_pos for pos in positions_3g), (
        "3g: every $run_dir/-prefixed use must come AFTER the step's one "
        "opening rebuild"
    )


def test_step_3f_bis_dual_writes_and_rereads_pr_json_across_the_boundary():
    """Spec-review round 4: `$pr_json` crosses the SAME spawn boundary as
    `$unit_wt`/`$diff_head`/`$fires` (it is captured before the `fires`
    judgement and consumed inside the pin block after it), but round 4 only
    added the other three to the dual-write set. Without this, the pin's
    `--pr-node-id`/`--pr-head-ref`/`--pr-base-ref` arguments silently resolve
    empty whenever the boundary is crossed."""
    step = _step_3f_bis()
    write_at = step.find('echo "$pr_json" > "$run_dir/pr_json"')
    assert write_at >= 0, "3f-bis must dual-write $pr_json alongside the other three values"
    capture_at = step.find("pr_json=$(cd \"$unit_wt\" && gh pr view")
    assert 0 <= capture_at < write_at, (
        "the pr_json dual-write must come after its initial capture"
    )
    reread_at = step.find('pr_json=$(cat "$run_dir/pr_json"')
    assert reread_at >= 0, "3f-bis must re-read $pr_json from the dual-write file"
    pin_at = step.find("pin_json=$(uv run")
    assert reread_at < pin_at, (
        "pr_json must be re-read before the pin block consumes it for the "
        "--pr-node-id/--pr-head-ref/--pr-base-ref arguments"
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
    the a/b/c review-cascade spawns and this block runs AFTER them, so they
    are re-derived from scratch here regardless of which boundary they
    crossed. `$diff_head`/`$fires`/`$pr_json` cross the earlier
    `fires`-judgement boundary and are handled by the dual-writes above;
    `$unit_wt` crosses BOTH (round 9 fix — it was previously miscategorized
    as fires-only here). Shell variables do not survive across separate tool
    calls, so this block must re-derive `run_dir`/`pr_url` explicitly rather
    than trust the earlier assignment."""
    step = _step_3f_bis()
    assert 'run_dir="{project_root}/.shipwright/runs/{loop_id}/{id}"' in step, (
        "3f-bis must re-derive run_dir after the cascade spawns, not reuse a "
        "shell variable set before them"
    )
    assert 'pr_url=$(cd "$unit_wt" && gh pr view "{branch}" --json url -q .url)' in step, (
        "3f-bis must re-derive pr_url (unit-scoped) after the cascade "
        "spawns, not reuse a shell variable set before them"
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


def test_step_3g_is_a_no_op_for_a_unit_3f_bis_did_not_promote_to_merging():
    """Tier-3 review, R5b round 14, blocking: 3f-bis's two review-pin-mismatch
    handlers (round 9) and its rebase cascade's exhausted/conflict branches
    (round 2) each demote the unit to `built`/`held` and say, in a COMMENT
    only, to "continue draining the rest of the wave at 3i" -- but this
    step's own governing rule (the 3f-bis..3h intro) runs 3g unconditionally
    for every unit that reached `built` at 3f, with no skip ever written.
    Left as prose alone, a demoted unit fell straight into 3g's unconditional
    `reviewed_head`/`shipped_head` checks, converting a per-unit demotion
    into a whole-wave STRICT-STOP -- the exact "comment is not control flow"
    bug class round 9 itself fixed one section up. 3g must read the unit's
    OWN current status fresh (shell state does not survive between steps, so
    3f-bis's own `pin_still_valid` is already gone here) and skip its entire
    body unless the unit was actually promoted to `merging`."""
    step = _step_3g()
    status_read = "unit_status=$(jq -r --arg id \"{id}\" '.units[] | select(.id == $id) | .status'"
    assert status_read in step, (
        "3g must read the unit's own status fresh from loop_state.json -- "
        "not a shell variable, which does not survive from 3f-bis"
    )
    status_at = step.index(status_read)
    guard = 'if [ "$unit_status" = "merging" ]; then'
    guard_at = step.find(guard, status_at)
    assert 0 <= guard_at - status_at < 200, (
        "the merging-status guard must open immediately after the fresh "
        "status read"
    )
    exists_at = step.index('[ -f "$run_dir/reviewed_head" ] || strict-stop')
    assert guard_at < exists_at, (
        "3g's unconditional reviewed_head/shipped_head checks must sit "
        "INSIDE the merging-status guard, not run regardless of it"
    )


def test_step_3g_guard_closes_after_the_confirmed_sha_branch():
    """The merging-status guard (round 14) must wrap 3g's ENTIRE body,
    including the final `merging -> merged` completion below the PR-merge
    wait -- not just the pin checks at the top, which would let a demoted
    unit skip the pin check but still fall into the merge itself."""
    step = _step_3g()
    guard_at = step.index('if [ "$unit_status" = "merging" ]; then')
    mark_merged_at = step.index("mark-merged")
    assert guard_at < mark_merged_at, (
        "the merging -> merged completion (loop_claim.py mark-merged) must "
        "be reached only from inside the round-14 guard"
    )


def test_step_3g_rechecks_unit_status_immediately_before_merging():
    """Tier-3 review, R5b round 15, blocking: `gh pr checks --watch` is
    UNBOUNDED -- campaign_drain.py's own bounded drain can force THIS unit
    `merging -> held` while a worker is still stuck waiting on slow/hung CI
    (the exact race this module's own accepted-risk disclosure already
    names, in `held_merge_reconciliation.py`'s own docstring: "narrows the
    race, it does not close it"). Without a fresh status re-check right
    before the merge itself, a worker whose watch outlives the drain would
    merge into a campaign that already force-terminaled this unit -- this
    does not close the race either (a TOCTOU gap remains between this check
    and the merge call itself), but it narrows the highest-risk window --
    the unbounded watch -- which had NO guard at all before this round."""
    step = _step_3g()
    watch_at = step.index('gh pr checks "$pr_url" --watch')
    merge_at = step.index("gh pr merge")
    assert watch_at < merge_at, "3g must check CI before merging"
    between = step[watch_at:merge_at]
    recheck_marker = 'unit_status_at_merge=$(jq -r --arg id "{id}"'
    assert recheck_marker in between, (
        "3g must re-read the unit's own status FRESH between the unbounded "
        "watch and the merge itself -- a concurrent drain can force this "
        "unit merging -> held while this worker is still watching CI"
    )
    assert '[ "$unit_status_at_merge" = "merging" ] || strict-stop' in between, (
        "a unit no longer at merging immediately before the merge call must "
        "STRICT-STOP, not merge into a campaign state a concurrent drain "
        "has already force-terminaled"
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


def test_step_3f_bis_bounded_wait_rechecks_after_the_loop_exhausts():
    """Stage-3 external review (openai/gpt-5.6-luna, PR #787): the bounded
    wait's `for i in $(seq 1 60); do ... break; sleep 5; done` only ever
    escapes early via `break` on a match — without an inline re-check right
    after the loop, exhausting the cap without ever matching fell through
    to 3g with a stale head instead of stopping. A trailing prose comment
    claiming "STRICT-STOP" is not a guard; this must be an executable
    statement. Mutation-probed: delete the re-check line and this fails."""
    step = _step_3f_bis()
    loop_at = step.index("seq 1 60")
    done_at = step.index("done", loop_at)
    recheck = step[done_at:done_at + 250]
    assert "|| strict-stop" in recheck, (
        "3f-bis's bounded wait must re-check the match and STRICT-STOP "
        "immediately after the loop, not rely on a trailing comment"
    )


def test_step_3g_bounded_wait_rechecks_after_the_loop_exhausts():
    """Same defect, same fix, at 3g's own bounded wait for PR state MERGED
    (Stage-3 external review, PR #787) — exhausting the cap without ever
    matching MERGED must not fall through to 3h with the PR still open."""
    step = _step_3g()
    loop_at = step.index("seq 1 60")
    done_at = step.index("done", loop_at)
    recheck = step[done_at:done_at + 250]
    assert "|| strict-stop" in recheck, (
        "3g's bounded wait must re-check for MERGED and STRICT-STOP "
        "immediately after the loop, not rely on a trailing comment"
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


def test_skill_iterate_docs_have_no_double_backslash_line_continuations():
    """Code-review round 6: `--force \\\\` / `--recorded-by spec-reviewer \\\\`
    in the Stage-1-REJECT `record` invocation used a DOUBLE backslash as a
    line continuation. In shell, `\\\\` is an escaped literal backslash, not a
    continuation — the newline then terminates the command, silently
    dropping `--recorded-by` and `--disposition` entirely, leaving a
    dispositionless `not_run` indistinguishable from "the cascade never ran".
    This bug class is invisible to every prose-matching assertion above
    (they all match substrings, not line endings), so it needs its own,
    doc-wide guard rather than a step-scoped one.

    Code-review round 6-verify, low: the original guard scoped to
    `campaign-mode.md` alone, but every runtime-prompt markdown file under
    `skills/iterate/references/` and `agents/` carries the same executable
    multi-line shell snippets and is equally invisible to substring
    assertions if this class recurs there. Widened to the whole tree; zero
    offenders exist today."""
    skill_dir = CAMPAIGN_DOC.parents[1]  # .../skills/iterate
    iterate_root = REPO_ROOT / "plugins" / "shipwright-iterate"
    offenders: dict[str, list[str]] = {}
    for pattern, base in (
        ("references/*.md", skill_dir),
        ("agents/*.md", iterate_root),
    ):
        for md in base.glob(pattern):
            bad = [
                line
                for line in md.read_text(encoding="utf-8").splitlines()
                if re.search(r"\\\\\s*$", line)
            ]
            if bad:
                offenders[str(md.relative_to(REPO_ROOT))] = bad
    assert not offenders, (
        "no skills/iterate references or agent doc may use a double "
        f"backslash as a line continuation (real continuation is a single "
        f"trailing \\): {offenders}"
    )


def test_step_3f_bis_record_calls_are_unit_scoped_and_checked():
    """R3 doubt-round, round 4, high: `record_review_pass.py`'s own
    `--project-root` was left at the `…` prefix's `{project_root}` default
    while `--payload-file` was unit-scoped — the same fallback-only
    exception class this step already forbids for `--payload-file`'s root,
    just not yet extended to `record`'s own root. Once R5a gives a unit a
    genuinely distinct worktree, `record` would write reviews.json into
    `{project_root}` while `git -C "$unit_wt" add` looks for it in
    `$unit_wt` — nothing to stage, a campaign-wide stall. Every `record`
    call in 3f-bis (promote-rows x3, not_applicable, REJECT-path) must
    override `--project-root` to `$unit_wt`, immediately before its own
    `--review-type` flag, and be checked (`|| STRICT-STOP`)."""
    step = _step_3f_bis()
    override = '--project-root "$unit_wt"'
    count = step.count(override)
    assert count >= 5, (
        f"expected at least 5 record calls overriding --project-root to "
        f"$unit_wt (3 promote-rows + not_applicable + REJECT-path) — found "
        f"{count}"
    )
    markers = (
        "--review-type spec --status completed",
        "--review-type code --status completed",
        "--review-type doubt --status completed",
        "--review-type doubt --status not_applicable",
        "--review-type spec --status not_run",
    )
    positions = []
    for marker in markers:
        at = step.find(marker)
        assert at >= 0, f"3f-bis must still contain the record call: {marker!r}"
        assert override in step[max(0, at - 40):at], (
            f"record call {marker!r} must have --project-root \"$unit_wt\" "
            "immediately before its --review-type flag"
        )
        positions.append((marker, at))
    # Each call's own guard must be checked WITHOUT bleeding into a
    # neighbour's OR into descriptive prose that happens to mention
    # "|| STRICT-STOP" in passing (code-review round 11, low: a fixed
    # 500-char window let a deleted guard on the spec/code row still pass on
    # its neighbour's; code-review round 12, medium, BLOCKING: bounding to
    # the NEXT record call's own marker position instead did not fix this —
    # the prose introducing the not_applicable call literally reads "...same
    # `--project-root "$unit_wt"` override, same `|| STRICT-STOP`):" right
    # before its marker, so the PRECEDING call's window still swallowed a
    # foreign match, and the not_applicable->REJECT-path gap is ~6000 chars
    # of unrelated content with many real STRICT-STOPs of its own). A FIXED,
    # narrow, empirically-verified window applied identically to every call
    # — not derived from any other call's position — closes both holes: each
    # call's own guard sits within ~220 normalized chars of its own marker
    # (measured directly against the current doc text), and deleting it
    # leaves nothing else, own-neighbour or prose, inside a 260-char window
    # for any of the five calls (verified by simulated deletion against the
    # live document, not assumed).
    WINDOW = 260
    for marker, at in positions:
        tail = step[at:at + WINDOW]
        assert "|| strict-stop" in tail, (
            f"record call {marker!r} must be checked (|| STRICT-STOP) within "
            f"{WINDOW} chars of its own marker, not rely on a neighbour's "
            "guard or a prose mention elsewhere in the step"
        )


def test_step_3g_verifies_shipped_state_not_just_pin_file_existence():
    """R3 doubt-round, round 4, medium: pin writes `reviewed_head`
    UNCONDITIONALLY and BEFORE the cascade even starts, so the file holds a
    SHA equal to the remote tip throughout the entire cascade window —
    including every STRICT-STOP inside it. File EXISTENCE alone cannot tell
    a completed review from an interrupted one; `verify --against
    shipped_head` additionally BLOCKs a reviewed (non-skipped) unit whose
    shipped_head was never recorded — which existence-of-file alone cannot
    distinguish from a genuine completed review."""
    step = _step_3g()
    exists_at = step.index('[ -f "$run_dir/reviewed_head" ] || strict-stop')
    verify_at = step.find('check_review_attribution.py" --mode verify', exists_at)
    assert verify_at > exists_at, (
        "3g must call check_review_attribution.py --mode verify AFTER the "
        "bare existence check, not rely on file existence alone"
    )
    window = step[verify_at:verify_at + 400]
    assert "--against shipped_head" in window, (
        "3g's verify call must check --against shipped_head, the mode that "
        "BLOCKs a reviewed unit whose cascade never actually shipped"
    )
    assert "|| strict-stop" in window, (
        "3g's verify call must be checked (|| STRICT-STOP)"
    )


def test_step_3f_bis_clears_all_handoff_files_on_reentry():
    """R3 doubt-round, round 4, medium: the top-of-step `rm -f` cleared only
    `reviewed_head`, leaving `unit_worktree`/`diff_head`/`fires`/`pr_json`
    from a prior attempt in place. `diff_head`/`unit_worktree` are
    cross-checked downstream so a stale value is caught there, but `fires`
    has NO such cross-check — a stale `fires=0` surviving a re-entry after
    new commits enlarged the diff could silently skip the cascade on the
    new, now-large diff using an old, no-longer-applicable verdict.
    `shipped_head`/`diff_lines` (code-review round 11, medium: the D4 fix's
    own test omitted the two files the round-11 fix itself added — reverting
    either from the `rm -f` line left this test green) share the same
    no-downstream-cross-check exposure as `fires` and must be cleared too.
    `pin_still_valid` (Tier-3 review, R5b round 18) joins the list for the
    identical reason once it moved from a bare shell variable to a
    `$run_dir`-backed file."""
    step = _step_3f_bis()
    rm_at = step.index("rm -f")
    line_end = step.find("\n", rm_at)
    rm_line = step[rm_at:line_end if line_end >= 0 else rm_at + 350]
    for name in (
        "reviewed_head", "unit_worktree", "diff_head", "fires", "diff_lines",
        "pr_json", "shipped_head", "pin_still_valid",
    ):
        assert f'"$run_dir/{name}"' in rm_line, (
            f"the re-entry cleanup must clear $run_dir/{name}, not just "
            "reviewed_head — a stale value with no downstream cross-check "
            "(fires, diff_lines) can silently misfire on re-entry"
        )


def test_step_3f_bis_review_record_commits_are_scoped_and_checked():
    """R3 doubt-round, round 4, low: `git commit` with no pathspec commits
    the WHOLE index, so any other pre-existing staged content rides along
    inside the commit whose entire purpose is to certify a review happened.
    Both the promote-path and REJECT-path commits must be scoped to
    reviews.json's own path, and both `git add` calls must be checked."""
    step = _step_3f_bis()
    add_marker = 'git -c "$unit_wt" add ".shipwright/planning/iterate/{run_id}/reviews.json"'
    add_positions = [m.start() for m in re.finditer(re.escape(add_marker), step)]
    assert len(add_positions) >= 2, (
        "expected at least 2 git add calls staging reviews.json (promote-path "
        f"+ REJECT-path) — found {len(add_positions)}"
    )
    for pos in add_positions:
        tail = step[pos:pos + len(add_marker) + 30]
        assert "|| strict-stop" in tail, (
            f"git add at offset {pos} must be checked (|| STRICT-STOP)"
        )
    for commit_marker in (
        'commit -m "chore(review): record the delegated cascade for {id}"',
        'commit -m "chore(review): record the stage-1 reject for {id}"',
    ):
        commit_at = step.index(commit_marker)
        tail = step[commit_at:commit_at + 300]
        assert '-- ".shipwright/planning/iterate/{run_id}/reviews.json"' in tail, (
            f"commit {commit_marker!r} must be scoped to reviews.json's own "
            "path with a pathspec, not commit the whole index"
        )
        assert "|| strict-stop" in tail, (
            f"commit {commit_marker!r} must be checked (|| STRICT-STOP)"
        )


def test_step_3f_bis_dual_writes_and_rereads_shipped_head():
    """R3 doubt-round, round 4, medium: unlike $unit_wt/$diff_head/$fires/
    $pr_json, $shipped_head crossed the ship-block's run_dir= rebuild with
    no dual-write of its own. Whether a genuine boundary separates the push
    from the --mode ship call is exactly the ambiguity that drew three
    consecutive REJECTs on this class in earlier rounds; closing it costs
    one file rather than arguing it in prose."""
    step = _step_3f_bis()
    write_at = step.find('echo "$shipped_head" > "$run_dir/shipped_head"')
    assert write_at >= 0, "3f-bis must dual-write $shipped_head"
    capture_at = step.find('shipped_head=$(git -c "$unit_wt" rev-parse head)')
    assert 0 <= capture_at < write_at, (
        "the shipped_head dual-write must come after its initial capture"
    )
    reread_marker = 'shipped_head=$(cat "$run_dir/shipped_head"'
    reread_positions = [
        m.start() for m in re.finditer(re.escape(reread_marker), step)
    ]
    assert len(reread_positions) >= 2, (
        "3f-bis must re-read $shipped_head from the dual-write file at "
        "least twice — once before the --mode ship call, once before the "
        f"legacy reviewed_head overwrite — found {len(reread_positions)}"
    )
    ship_invocation_at = step.index('check_review_attribution.py" --mode ship')
    legacy_write_at = step.index('echo "$shipped_head" > "$run_dir/reviewed_head"')
    assert reread_positions[0] < ship_invocation_at, (
        "shipped_head must be re-read before the --mode ship call consumes it"
    )
    assert any(pos < legacy_write_at for pos in reread_positions[1:]), (
        "shipped_head must be re-read again before the legacy reviewed_head "
        "overwrite"
    )


def test_step_3f_bis_fires_line_count_is_computed_not_judged():
    """R3 doubt-round, round 4, medium: the fires trigger's line-count clause
    was left entirely to model judgement despite being exactly computable,
    unlike the other two clauses (risk flags, medium+) which genuinely
    require reading the diff. `$diff_lines` must be computed mechanically
    from `$diff` right after it is captured, and `fires=1` must be MANDATORY
    once it exceeds 100 — not merely another factor a model weighs.

    code-review round 11, high: the first pass of this fix computed
    `$diff_lines` and asserted the word "mandatory" appeared nearby, but
    never surfaced the value anywhere a model or a shell statement could act
    on it — no `echo`, no dual-write, no re-read, and no executable `-gt`
    test tying it to `$fires`. The prose called the floor MANDATORY while
    nothing enforced it — a control that is documented and tested-for
    without being implemented, which is worse than not having the test.
    This now asserts the floor is an executable shell statement, not just a
    sentence: `$diff_lines` is dual-written, re-read through a re-derived
    `$run_dir` at the fires-assignment site, and combined with `fires` via a
    literal `-gt 100` comparison that can only RAISE `fires`, never lower a
    judgement that already decided 1."""
    step = _step_3f_bis()
    diff_capture_at = step.index('diff=$(git -c "$unit_wt" diff "$base"..."$diff_head") || strict-stop')
    compute_at = step.find("diff_lines=$(printf", diff_capture_at)
    assert 0 <= compute_at - diff_capture_at < 200, (
        "$diff_lines must be computed mechanically immediately after the "
        "diff itself is captured"
    )
    assert "wc -l" in step[compute_at:compute_at + 120], (
        "$diff_lines must be computed via a mechanical line count, not left "
        "to model judgement"
    )
    # code-review round 12, low: a bare "mandatory" substring search in this
    # window is satisfied by the ROUND-11 BUG-NARRATIVE text ("...added a
    # test asserting the word 'mandatory' appeared...", ~730 chars in) —
    # deleting the actual normative sentence still left the narrative's own
    # mention inside a 900-char window, so the assertion never exercised the
    # claim it named. Anchored to the normative wording itself instead.
    assert "fires=1 is mandatory whenever" in step[compute_at:compute_at + 1500], (
        "the doc must state that fires=1 is MANDATORY once $diff_lines "
        "exceeds 100, not merely another factor the judgement weighs, and "
        "not just mention the word in an unrelated bug-narrative aside"
    )
    write_marker = 'echo "$diff_lines" > "$run_dir/diff_lines"'
    write_at = step.find(write_marker, compute_at)
    # 90, not 60: code-review round 12's `| tr -d '[:space:]'` portability
    # fix (non-GNU `wc -l` leading blanks) lengthened the compute line by
    # ~20 chars; widened with margin rather than re-measured to the exact
    # new distance, so a future one-word rewording doesn't retrip this.
    assert 0 <= write_at - compute_at < 90, (
        "$diff_lines must be dual-written to $run_dir/diff_lines "
        "immediately after it is computed, so a value the model never "
        "observed is not the only carrier of the floor across the "
        "fires-judgement boundary"
    )
    assert "|| strict-stop" in step[write_at:write_at + len(write_marker) + 20], (
        "the $diff_lines dual-write must be checked (|| STRICT-STOP)"
    )
    reread_marker = 'diff_lines=$(cat "$run_dir/diff_lines"'
    reread_at = step.find(reread_marker, write_at)
    assert reread_at > write_at, (
        "$diff_lines must be re-read from its dual-write file at the "
        "fires-assignment site — the same treatment $unit_wt/$diff_head/"
        "$fires/$pr_json/$shipped_head already get"
    )
    fires_assign_at = step.find("fires=<1 or 0>", reread_at)
    assert 0 <= fires_assign_at - reread_at < 200, (
        "the $diff_lines re-read must sit immediately before the fires "
        "digit assignment, not somewhere unrelated in the step"
    )
    override_marker = '[ "$diff_lines" -gt 100 ] && fires=1'
    override_at = step.find(override_marker, fires_assign_at)
    assert 0 <= override_at - fires_assign_at < 200, (
        "the mechanical floor must be an EXECUTABLE statement — "
        f"{override_marker!r} — immediately after the judgement's own "
        "fires=<1 or 0> assignment, not merely asserted in prose"
    )
    fires_write_at = step.index('echo "$fires" > "$run_dir/fires"', override_at)
    assert fires_write_at > override_at, (
        "the mechanical -gt 100 override must run BEFORE $fires is written "
        "to its dual-write file, or a late judgement could still write a "
        "value the floor never had a chance to raise"
    )
