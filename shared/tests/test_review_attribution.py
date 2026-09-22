"""Per-unit review-diff attribution guard (campaign-dag-scheduler R3).

Lives under ``shared/tests`` (one-test-root-per-process rule) — matches
``test_r2_worktree_capability_integration.py``'s own placement, and reuses
its ``git_origin_repo`` fixture (identity-configured, offline-fetchable
origin) for real git plumbing rather than mocking it.

The reproduction case (spec "Work breakdown" step 1) is
``test_pin_resolves_each_units_own_worktree_not_the_caller_supplied_fallback``:
before this module existed, ``campaign-mode.md`` 3f-bis diffed a single,
implicit worktree with no per-unit resolution at all — a diff step
literally hardcoded to "the campaign worktree" cannot distinguish two
units' branches once R5a gives each its own worktree. There is no prior
CODE path to red/green over the resolver itself (the bug lived only in
unattributed bash prose), so that half is framed the other way: construct
two per-unit worktrees with genuinely different diffs and prove the
resolver picks each unit's OWN, never the other's or a shared fallback's.
The complementary half,
``test_the_old_single_worktree_diff_would_have_misattributed_units``,
reproduces the bug directly by running the OLD (pre-R3) diff command
against a single shared worktree and showing it returns the same
misattributed diff for a second unit's "turn."
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib.review_attribution import ReviewAttributionError, pin, resolve_unit_identity, ship, verify


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _write_loop_state(path: Path, units: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"loop_id": "r3-test", "units": units}), encoding="utf-8")


def _add_worktree(work: Path, dirname: str, branch: str) -> Path:
    wt = work / ".worktrees" / dirname
    subprocess.run(
        ["git", "-C", str(work), "worktree", "add", str(wt), "-b", branch, "main"],
        capture_output=True, text=True, check=True,
    )
    return wt


def _commit_file(repo: Path, name: str, content: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", name], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", f"add {name}"], check=True, capture_output=True,
    )
    return _git(repo, "rev-parse", "HEAD")


def test_pin_resolves_each_units_own_worktree_not_the_caller_supplied_fallback(git_origin_repo):
    work, _ = git_origin_repo
    wt_a = _add_worktree(work, "unit-a", "iterate/unit-a")
    wt_b = _add_worktree(work, "unit-b", "iterate/unit-b")
    head_a = _commit_file(wt_a, "a.txt", "unit A's own change\n")
    head_b = _commit_file(wt_b, "b.txt", "unit B's own change\n")
    assert head_a != head_b

    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [
        {"id": "A", "branch": "iterate/unit-a", "worktree": str(wt_a), "attempt": 0},
        {"id": "B", "branch": "iterate/unit-b", "worktree": str(wt_b), "attempt": 0},
    ])

    # Both pin against the SAME caller-supplied fallback (`campaign_worktree=wt_a`)
    # to prove resolution comes from the unit's OWN row, not the fallback.
    pin_a = pin(state_path, "A", project_root=str(work), campaign_worktree=str(wt_a),
                loop_id="r3-test")
    pin_b = pin(state_path, "B", project_root=str(work), campaign_worktree=str(wt_a),
                loop_id="r3-test")

    assert pin_a["reviewed_head"] == head_a
    assert pin_b["reviewed_head"] == head_b
    assert pin_a["reviewed_head"] != pin_b["reviewed_head"]
    assert pin_a["diff_sha256"] != pin_b["diff_sha256"]


def test_the_old_single_worktree_diff_would_have_misattributed_units(git_origin_repo):
    """The other reproduction half (spec Work breakdown step 1): simulate
    TODAY's (pre-R3) 3f-bis logic directly — one diff command run against a
    single shared worktree, with no per-unit resolution at all — and show it
    returns the SAME diff regardless of which unit is nominally under
    review, once a later unit's "turn" arrives with nothing on the shared
    worktree having changed. That is "computes the wrong one's diff": B's
    review would see A's diff. Contrast with the test above, where `pin()`'s
    per-unit resolver reads each unit's own row/worktree and never exhibits
    this."""
    work, _ = git_origin_repo

    def old_unscoped_diff() -> str:
        # TODAY's (pre-R3) campaign-mode.md 3f-bis: git -C "{project_root}"
        # diff merge-base(origin/main)...HEAD, with "{project_root}" always
        # the one shared worktree, whatever branch happens to be checked
        # out there — no unit-aware resolution at all.
        merge_base = _git(work, "merge-base", "main", "HEAD")
        return _git(work, "diff", f"{merge_base}...HEAD")

    # Unit A's turn: its branch is checked out and committed on the shared
    # worktree, and 3f-bis diffs it correctly (by accident, since it happens
    # to be checked out there right now).
    _git(work, "checkout", "-b", "iterate/unit-a-shared")
    _commit_file(work, "a-shared.txt", "unit A's own change (shared worktree)\n")
    diff_reviewed_as_a = old_unscoped_diff()
    assert "unit A's own change" in diff_reviewed_as_a

    # Unit B's turn: nothing in the old prose is unit-aware, so re-running
    # the SAME diff command against the SAME shared worktree — without any
    # commit of B's own having landed there — returns the identical diff.
    # B's review sees A's diff: the exact misattribution this sub-iterate
    # fixes.
    diff_reviewed_as_b = old_unscoped_diff()
    assert diff_reviewed_as_b == diff_reviewed_as_a
    assert "unit A's own change" in diff_reviewed_as_b  # WRONG: this is B's review

    # R3 doubt-round, low: the old command above cannot fail on ANY codebase
    # (it never touches the new code at all), so it proves nothing about the
    # fix. Show the contrast directly: on this SAME shared worktree, `pin()`
    # for a second unit whose row claims a DIFFERENT branch than what's
    # actually checked out (still "iterate/unit-a-shared" from above)
    # refuses outright, exactly where the old command above silently
    # returned unit A's diff for unit B's "turn."
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [
        {"id": "B-shared", "branch": "iterate/unit-b-shared", "attempt": 0},
    ])
    with pytest.raises(ReviewAttributionError, match="refusing to pin the wrong branch"):
        pin(state_path, "B-shared", project_root=str(work), campaign_worktree=str(work),
            loop_id="r3-test")


def test_fallback_to_shared_campaign_worktree_when_row_has_no_worktree_field(git_origin_repo):
    """Every row, pre-R5a — the row carries no `worktree` field at all."""
    work, _ = git_origin_repo
    head = _commit_file(work, "c.txt", "shared worktree change\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "C", "branch": "main", "attempt": 0}])

    result = pin(state_path, "C", project_root=str(work), campaign_worktree=str(work),
                 loop_id="r3-test")
    assert result["reviewed_head"] == head
    assert result["worktree"] == str(work)


def test_resolve_unit_identity_defaults_attempt_id_when_absent():
    state = {"units": [{"id": "D", "branch": "main", "attempt": 3}]}
    identity = resolve_unit_identity(state, "D", campaign_worktree="/fallback")
    assert identity["attempt_id"] == "a3"


def test_pin_writes_legacy_reviewed_head_file_alongside_the_new_pin_file(git_origin_repo):
    work, _ = git_origin_repo
    head = _commit_file(work, "d.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "E", "branch": "main", "attempt": 0}])

    result = pin(state_path, "E", project_root=str(work), campaign_worktree=str(work),
                 loop_id="r3-test")

    legacy = work / ".shipwright" / "runs" / "r3-test" / "E" / "reviewed_head"
    assert legacy.read_text(encoding="utf-8").strip() == head == result["reviewed_head"]

    pin_file = work / ".shipwright" / "runs" / "r3-test" / "E" / "a0" / "review_pin.json"
    assert json.loads(pin_file.read_text(encoding="utf-8"))["reviewed_head"] == head


def test_pin_refuses_when_the_recorded_branch_is_not_the_one_checked_out(git_origin_repo):
    work, _ = git_origin_repo
    subprocess.run(["git", "-C", str(work), "checkout", "-b", "other"],
                    check=True, capture_output=True)
    state_path = work / ".shipwright" / "loop_state.json"
    # Row claims `main`, but `other` is actually checked out at this worktree.
    _write_loop_state(state_path, [{"id": "F", "branch": "main", "attempt": 0}])

    with pytest.raises(ReviewAttributionError, match="refusing to pin the wrong branch"):
        pin(state_path, "F", project_root=str(work), campaign_worktree=str(work),
            loop_id="r3-test")


def test_verify_against_reviewed_head_passes_on_an_untouched_branch(git_origin_repo):
    work, _ = git_origin_repo
    _commit_file(work, "e.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "G", "branch": "main", "attempt": 0}])
    pin(state_path, "G", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    result = verify(state_path, "G", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="reviewed_head")
    assert result["ok"] is True


def test_verify_against_reviewed_head_detects_a_commit_added_after_pinning(git_origin_repo):
    work, _ = git_origin_repo
    _commit_file(work, "f.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "H", "branch": "main", "attempt": 0}])
    pin(state_path, "H", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    _commit_file(work, "g.txt", "unexpected extra commit\n")

    result = verify(state_path, "H", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="reviewed_head")
    assert result["ok"] is False


def test_verify_against_reviewed_head_detects_a_rebase(git_origin_repo):
    """A rebase (here simulated with `commit --amend`) changes the branch's
    tip SHA while the tree content stays superficially similar — the guard
    must key on the SHA, not the content."""
    work, _ = git_origin_repo
    head1 = _commit_file(work, "h.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "I", "branch": "main", "attempt": 0}])
    pin(state_path, "I", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    subprocess.run(["git", "-C", str(work), "commit", "--amend", "-m", "rebased onto x"],
                    check=True, capture_output=True)
    amended_head = _git(work, "rev-parse", "HEAD")
    assert amended_head != head1

    result = verify(state_path, "I", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="reviewed_head")
    assert result["ok"] is False


def test_review_skipped_pin_sets_shipped_head_equal_to_reviewed_head(git_origin_repo):
    work, _ = git_origin_repo
    head = _commit_file(work, "i.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "J", "branch": "main", "attempt": 0}])

    result = pin(state_path, "J", project_root=str(work), campaign_worktree=str(work),
                 loop_id="r3-test", review_skipped=True)
    assert result["shipped_head"] == head == result["reviewed_head"]


def test_verify_against_shipped_head_passes_when_review_skipped_and_nothing_moved(git_origin_repo):
    work, _ = git_origin_repo
    _commit_file(work, "j.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "K", "branch": "main", "attempt": 0}])
    pin(state_path, "K", project_root=str(work), campaign_worktree=str(work),
        loop_id="r3-test", review_skipped=True)

    result = verify(state_path, "K", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="shipped_head")
    assert result["ok"] is True


def test_verify_against_shipped_head_passes_after_exactly_one_review_record_commit(git_origin_repo):
    work, _ = git_origin_repo
    _commit_file(work, "k.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "L", "branch": "main", "attempt": 0}])
    pin(state_path, "L", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    # The review-record commit 3f-bis adds on top (reviews.json), then ships it.
    shipped = _commit_file(work, "reviews.json", "{}\n")
    ship(state_path, "L", project_root=str(work), campaign_worktree=str(work),
         loop_id="r3-test", shipped_head=shipped)

    result = verify(state_path, "L", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="shipped_head")
    assert result["ok"] is True


def test_verify_against_shipped_head_fails_with_more_than_one_extra_commit(git_origin_repo):
    work, _ = git_origin_repo
    _commit_file(work, "l.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "M", "branch": "main", "attempt": 0}])
    pin(state_path, "M", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    shipped = _commit_file(work, "reviews.json", "{}\n")
    ship(state_path, "M", project_root=str(work), campaign_worktree=str(work),
         loop_id="r3-test", shipped_head=shipped)
    _commit_file(work, "extra.txt", "unexpected second commit\n")

    result = verify(state_path, "M", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="shipped_head")
    assert result["ok"] is False


def test_ship_refuses_to_record_a_sha_that_is_not_the_branchs_current_tip(git_origin_repo):
    work, _ = git_origin_repo
    _commit_file(work, "m.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "P", "branch": "main", "attempt": 0}])
    pin(state_path, "P", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    with pytest.raises(ReviewAttributionError, match="not branch .* current local tip"):
        ship(state_path, "P", project_root=str(work), campaign_worktree=str(work),
             loop_id="r3-test", shipped_head="0" * 40)


def test_ship_refuses_to_silently_overwrite_a_different_prior_shipped_head(git_origin_repo):
    work, _ = git_origin_repo
    _commit_file(work, "n.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "Q", "branch": "main", "attempt": 0}])
    pin(state_path, "Q", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    first_shipped = _commit_file(work, "reviews.json", "{}\n")
    ship(state_path, "Q", project_root=str(work), campaign_worktree=str(work),
         loop_id="r3-test", shipped_head=first_shipped)

    second_shipped = _commit_file(work, "extra.txt", "amended-in retry\n")
    with pytest.raises(ReviewAttributionError, match="already has shipped_head"):
        ship(state_path, "Q", project_root=str(work), campaign_worktree=str(work),
             loop_id="r3-test", shipped_head=second_shipped)


def test_ship_refuses_a_shipped_head_that_is_not_exactly_one_commit_ahead_of_reviewed_head(git_origin_repo):
    """Code-review round 3, high: ship() used to check only that shipped_head
    was the branch tip, never that it was the record commit — the ONE
    reviewed commit ahead of reviewed_head. Since today's 3f-bis/3g call
    ship(), never verify(), an unchecked ship() was the sole thing standing
    between an unreviewed EXTRA commit (landed between pin and the record
    commit) and a merge. Concretely: pin, then an unreviewed fix commit, then
    the record commit — the record commit's parent is the fix, not
    reviewed_head, so ship() must refuse it."""
    work, _ = git_origin_repo
    _commit_file(work, "r1.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "X", "branch": "main", "attempt": 0}])
    pin(state_path, "X", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    _commit_file(work, "unreviewed-fix.txt", "an unreviewed commit landed between pin and record\n")
    record_commit = _commit_file(work, "reviews.json", "{}\n")

    with pytest.raises(ReviewAttributionError, match="exactly one commit"):
        ship(state_path, "X", project_root=str(work), campaign_worktree=str(work),
             loop_id="r3-test", shipped_head=record_commit)


def test_ship_refuses_a_merge_commit_even_when_its_first_parent_is_reviewed_head(git_origin_repo):
    """R3 doubt-round, round 2, medium: a bare `rev-parse {sha}^` resolves
    only the FIRST parent and never errors on a merge commit, so it could not
    tell a genuine single-commit record from a merge whose first parent
    happened to be `reviewed_head`. Build exactly that shape — a side branch
    with an unreviewed commit, merged into the reviewed branch with
    `--no-ff` so the merge's first parent IS reviewed_head — and assert
    `ship()` still refuses it (via `_single_parent` returning `None` for a
    two-parent commit, not the old parent-of-first-parent check)."""
    work, _ = git_origin_repo
    _commit_file(work, "m1.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "M", "branch": "main", "attempt": 0}])
    pin(state_path, "M", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")
    reviewed_head = _git(work, "rev-parse", "HEAD")

    subprocess.run(["git", "-C", str(work), "checkout", "-b", "side"],
                    check=True, capture_output=True)
    _commit_file(work, "unreviewed-side.txt", "an unreviewed commit on a side branch\n")
    subprocess.run(["git", "-C", str(work), "checkout", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(work), "merge", "--no-ff", "side", "-m", "merge unreviewed side branch"],
        check=True, capture_output=True,
    )
    merge_commit = _git(work, "rev-parse", "HEAD")
    parents = _git(work, "rev-list", "--parents", "-n", "1", merge_commit).split()
    assert parents[1] == reviewed_head, "the merge's first parent must be reviewed_head for this to test the gap"
    assert len(parents) == 3, "the merge must have exactly two parents"

    with pytest.raises(ReviewAttributionError, match="exactly one commit"):
        ship(state_path, "M", project_root=str(work), campaign_worktree=str(work),
             loop_id="r3-test", shipped_head=merge_commit)


def test_verify_against_shipped_head_blocks_when_ship_was_never_called_even_with_a_valid_record_commit(git_origin_repo):
    """R3 doubt-round, high: a reviewed unit's `shipped_head` stays `None`
    until `ship()` records it. Before this fix, `verify` fell back to a
    content-blind "any commit whose parent is reviewed_head" check here and
    ALLOWed — silently weaker than `--match-head-commit`, which this pin is
    meant to replace."""
    work, _ = git_origin_repo
    _commit_file(work, "o.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "R", "branch": "main", "attempt": 0}])
    pin(state_path, "R", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    _commit_file(work, "reviews.json", "{}\n")  # the record commit lands, but ship() is never called

    result = verify(state_path, "R", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="shipped_head")
    assert result["ok"] is False
    assert "shipped_head was never recorded" in result["detail"]


def test_verify_against_shipped_head_blocks_a_force_push_amend_of_the_record_commit(git_origin_repo):
    """A force-push/amend of the review-record commit changes the tip SHA
    while its parent stays `reviewed_head` — content-blind logic would still
    ALLOW; pinning the exact shipped SHA must not."""
    work, _ = git_origin_repo
    _commit_file(work, "p.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "S", "branch": "main", "attempt": 0}])
    pin(state_path, "S", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    shipped = _commit_file(work, "reviews.json", "{}\n")
    ship(state_path, "S", project_root=str(work), campaign_worktree=str(work),
         loop_id="r3-test", shipped_head=shipped)

    subprocess.run(["git", "-C", str(work), "commit", "--amend", "-m", "amended record commit"],
                    check=True, capture_output=True)
    amended = _git(work, "rev-parse", "HEAD")
    assert amended != shipped

    result = verify(state_path, "S", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="shipped_head")
    assert result["ok"] is False
    assert "does not match pinned shipped_head" in result["detail"]


def test_pin_verify_and_ship_all_refuse_a_loop_id_that_disagrees_with_the_state_files_own(git_origin_repo):
    """Code-review round 3, low: the original test named `pin` and `verify`
    but only exercised `pin` — `_check_loop_id` is shared by all three entry
    points, so this covers `verify` and `ship` explicitly too."""
    work, _ = git_origin_repo
    _commit_file(work, "q.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"loop_id": "the-real-loop", "units": [{"id": "T", "branch": "main", "attempt": 0}]}),
        encoding="utf-8")

    with pytest.raises(ReviewAttributionError, match="does not match loop_state.json"):
        pin(state_path, "T", project_root=str(work), campaign_worktree=str(work),
            loop_id="a-different-loop")
    with pytest.raises(ReviewAttributionError, match="does not match loop_state.json"):
        verify(state_path, "T", project_root=str(work), campaign_worktree=str(work),
               loop_id="a-different-loop", against="reviewed_head")
    with pytest.raises(ReviewAttributionError, match="does not match loop_state.json"):
        ship(state_path, "T", project_root=str(work), campaign_worktree=str(work),
             loop_id="a-different-loop", shipped_head="a" * 40)


def test_verify_raises_when_no_pin_exists_for_the_unit(git_origin_repo):
    work, _ = git_origin_repo
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "N", "branch": "main", "attempt": 0}])

    with pytest.raises(ReviewAttributionError, match="no pin file"):
        verify(state_path, "N", project_root=str(work), campaign_worktree=str(work),
               loop_id="r3-test", against="reviewed_head")


def test_pin_raises_for_an_unknown_unit_id(git_origin_repo):
    work, _ = git_origin_repo
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "O", "branch": "main", "attempt": 0}])

    with pytest.raises(ReviewAttributionError, match="not found"):
        pin(state_path, "does-not-exist", project_root=str(work), campaign_worktree=str(work),
            loop_id="r3-test")
