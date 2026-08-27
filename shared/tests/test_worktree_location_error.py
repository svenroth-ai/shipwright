"""Unit tests for lib.worktree_location.worktree_location_error.

Split out of test_worktree_isolation_lib.py (which was already at the 300-line
guideline) — a location-only guard, distinct from the fuller F0/F11 leak-guard
(detect_leak): no snapshot, no run_id, never diffs the main tree. Used by the
campaign spawn guard (check_worktree_location.py) and by sub-iterate-runner's
own Step 1.0, to stop a runner subagent from mutating branches in the main
repository checkout — the exact failure two production campaigns hit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.worktree_location import worktree_location_error


def _add_worktree(work: Path, slug: str) -> Path:
    wt = work / ".worktrees" / slug
    subprocess.run(
        [
            "git", "-C", str(work), "worktree", "add", str(wt),
            "-b", f"iterate/{slug}", "main",
        ],
        capture_output=True, text=True, check=True,
    )
    return wt


def test_worktree_location_error_empty_for_isolated_worktree(git_origin_repo):
    work, _ = git_origin_repo
    wt = _add_worktree(work, "probe")
    assert worktree_location_error(wt) == ""


def test_worktree_location_error_flags_main_repo(git_origin_repo):
    """The exact incident this guard exists for: a runner handed the main
    repo checkout instead of the campaign worktree."""
    work, _ = git_origin_repo
    error = worktree_location_error(work)
    assert error != ""
    assert ".worktrees/" in error


def test_worktree_location_error_never_diffs_the_main_tree(git_origin_repo):
    """Unlike check_iterate_isolation's leak-guard, this check has no snapshot
    and no run_id — a main-tree write (e.g. campaign step 3h's status.json)
    must never affect the verdict for an already-isolated worktree."""
    work, _ = git_origin_repo
    wt = _add_worktree(work, "probe")
    (work / "status.json").write_text("{}", encoding="utf-8")  # main-tree write
    assert worktree_location_error(wt) == ""


def test_worktree_location_error_blocks_a_stray_non_git_directory(tmp_path):
    """The GitError branch — a stray directory that is not a Git repo at all —
    must return a blocking string, not raise (external review,
    iterate-2026-08-26-campaign-worktree-guard; the CLI-level equivalent
    (test_check_worktree_location.py) runs via subprocess and is invisible to
    in-process coverage)."""
    stray = tmp_path / "not-a-repo"
    stray.mkdir()
    error = worktree_location_error(stray)
    assert error != ""
    assert "cannot resolve git context" in error


def test_worktree_location_error_flags_a_linked_worktree_outside_worktrees_dir(
    git_origin_repo,
):
    """A genuine linked worktree still fails if it lives OUTSIDE
    <main_root>/.worktrees/ — is_worktree() alone is not sufficient; the
    is_under_worktrees() location check is what this guard is actually for
    (external review, iterate-2026-08-26-campaign-worktree-guard)."""
    work, _ = git_origin_repo
    outside_wt = work.parent / "external-wt"
    subprocess.run(
        [
            "git", "-C", str(work), "worktree", "add", str(outside_wt),
            "-b", "iterate/outside", "main",
        ],
        capture_output=True, text=True, check=True,
    )
    error = worktree_location_error(outside_wt)
    assert error != ""
    assert ".worktrees/" in error


# --- expected_campaign_slug (identity, not just location) -------------------
#
# Checked against the worktree DIRECTORY's basename, not the checked-out
# branch — a branch-prefix check was tried first and rejected (external
# review): it cannot distinguish two campaigns whose slugs are themselves a
# hyphenated extension of one another (req3 vs req3-04) from a slug plus a
# sub-iterate suffix, since both share the same '-'-separated shape. The
# directory basename never gains a sub-iterate suffix, so it is exact.


def _add_campaign_worktree(work: Path, dirname: str, branch: str | None = None) -> Path:
    wt = work / ".worktrees" / dirname
    subprocess.run(
        ["git", "-C", str(work), "worktree", "add", str(wt),
         "-b", branch or f"iterate/{dirname}", "main"],
        capture_output=True, text=True, check=True,
    )
    return wt


def test_expected_slug_passes_when_the_directory_name_matches(git_origin_repo):
    work, _ = git_origin_repo
    wt = _add_campaign_worktree(work, "campaign-req3-04")
    assert worktree_location_error(wt, expected_campaign_slug="req3-04") == ""


def test_expected_slug_is_unaffected_by_which_branch_is_checked_out(git_origin_repo):
    """The directory name is fixed at creation and never changes; the branch
    checked out inside it DOES change once Step 1 of sub-iterate-runner.md
    branches off it — the identity check must not care which branch that is."""
    work, _ = git_origin_repo
    wt = _add_campaign_worktree(work, "campaign-req3-04",
                                 branch="iterate/campaign-req3-04-r0-spec-reader")
    assert worktree_location_error(wt, expected_campaign_slug="req3-04") == ""


def test_expected_slug_rejects_a_different_valid_campaign_worktree(git_origin_repo):
    """The exact gap this fix closes: project_root IS an isolated worktree
    under .worktrees/ (location check passes) but belongs to a DIFFERENT
    campaign — a stale prior campaign, or a sibling one."""
    work, _ = git_origin_repo
    wt = _add_campaign_worktree(work, "campaign-other")
    error = worktree_location_error(wt, expected_campaign_slug="req3-04")
    assert error != ""
    assert "req3-04" in error


def test_expected_slug_rejects_an_adjacent_hyphenated_slug(git_origin_repo):
    """The case a branch-prefix check could not close: a DIFFERENT campaign
    whose slug is this one's slug plus a hyphenated suffix (req3-04 vs req3)
    is a different worktree directory, so it is correctly rejected."""
    work, _ = git_origin_repo
    wt = _add_campaign_worktree(work, "campaign-req3-04")
    error = worktree_location_error(wt, expected_campaign_slug="req3")
    assert error != ""


def test_expected_slug_none_keeps_prior_behavior(git_origin_repo):
    """Omitting expected_campaign_slug is unaffected by this fix — every
    pre-existing call site (and test) keeps working unchanged."""
    work, _ = git_origin_repo
    wt = _add_campaign_worktree(work, "campaign-anything")
    assert worktree_location_error(wt) == ""


def test_expected_slug_rejects_a_nested_directory_sharing_the_right_basename(
    git_origin_repo,
):
    """A basename-only compare would let <main>/.worktrees/other/campaign-foo
    pass for slug "foo" (is_under_worktrees allows any depth under
    .worktrees/) — the full resolved-path compare (doubt-reviewer,
    iterate-2026-08-26-campaign-worktree-guard-followups) closes it."""
    work, _ = git_origin_repo
    wt = work / ".worktrees" / "other" / "campaign-foo"
    subprocess.run(
        ["git", "-C", str(work), "worktree", "add", str(wt),
         "-b", "iterate/nested", "main"],
        capture_output=True, text=True, check=True,
    )
    error = worktree_location_error(wt, expected_campaign_slug="foo")
    assert error != ""
