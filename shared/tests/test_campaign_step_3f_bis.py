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
    assert "fires=<1 or 0>" in step[max(0, fires_write_at - 120):fires_write_at], (
        "the literal fires=<1 or 0> assignment must immediately precede "
        "the dual-write, not float disconnected from it"
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
    assert len(positions_3g) >= 3, (
        f"expected at least 3 $run_dir/-prefixed usages in 3g — got "
        f"{len(positions_3g)}, which means the scan itself is broken, not "
        "that the step shrank"
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
