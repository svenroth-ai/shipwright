"""`check_fr_hygiene_on_touched_rows` — DELTA-scoping regressions
(iterate-2026-09-06-fr-hygiene-touched-rows).

Split out of `test_check_fr_hygiene.py` (which crossed the 300-line
guideline): this file is specifically the "judge the delta, not the whole
row" theme — the fix for a run inheriting a legacy violation on a CELL or
CRITERION it never touched, plus the two edge cases an internal/external
review round found in that fix (a reinstated FR whose base criteria were
wrongly treated as empty, and an already-merged commit reporting a false
"clean"). Shares helpers/fixtures with the sibling module rather than
duplicating them.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_check_fr_hygiene import (  # noqa: E402
    _HEADER,
    _RUN,
    _clean_spec,
    _commit_on_worktree,
    _seed_main,
)
from test_integrate_main import _git, _write  # noqa: E402
from tools.verifiers import fr_hygiene as fh  # noqa: E402


def test_ignores_a_legacy_dirty_name_when_only_description_is_edited(git_origin_repo, make_worktree):
    """Judge the DELTA, not the row: a legacy-dirty Name that this run did not
    touch must not ride along on an edit to the Description cell alone."""
    work, _o = git_origin_repo
    dirty_name_row = (
        "| FR-01.02 | Core | Build copy-command (POST) | Must | "
        "Users can reset their password. | interview | unit |\n"
    )
    _seed_main(work, _clean_spec(extra_row=dirty_name_row))
    wt = make_worktree(work, "frh-namedelta")
    edited = _clean_spec(extra_row=dirty_name_row).replace(
        "Users can reset their password.", "Users can reset their password by email.",
    )
    commit = _commit_on_worktree(wt, edited, "clarify description only")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is True
    assert "FR-01.02" not in res.detail


def test_ignores_legacy_dirty_criteria_when_a_clean_criterion_is_folded_in(
    git_origin_repo, make_worktree,
):
    """Judge the DELTA, not the row: a fold that adds one clean criterion must
    not inherit a block from a DIFFERENT, pre-existing malformed criterion on
    the same row that this run never touched."""
    work, _o = git_origin_repo
    seeded = _clean_spec(
        extra_body="- Scaffold-creation half - verified (auth.ts, test_auth.py): "
                   "confirmed by running the existing suite.\n",
    )
    _seed_main(work, seeded)
    wt = make_worktree(work, "frh-folddelta")
    folded = seeded + (
        "- (E) Given a signed-in user, when they sign out, then their "
        "session ends.\n"
    )
    commit = _commit_on_worktree(wt, folded, "fold in one clean criterion")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is True


def test_reinstated_row_does_not_inherit_a_legacy_malformed_criterion(
    git_origin_repo, make_worktree,
):
    """`base_row is None` does NOT mean "no criteria at base" — an id restored
    from `## Removed Requirements` can have had its `### FR-xx.yy` criteria
    section present at base all along. Un-removing it, with the criteria text
    itself unchanged, must not inherit a block on that legacy content."""
    work, _o = git_origin_repo
    removed_at_base = (
        "## 2. Functional Requirements\n\n"
        + _HEADER
        + "| FR-01.01 | Core | Login | Must | Users can sign in. | interview | unit |\n\n"
        "### FR-01.01 — Login\n\n"
        "#### Acceptance Criteria\n"
        "- (E) Given a registered user, when they submit valid credentials, "
        "then they are signed in.\n\n"
        "## Removed Requirements\n\n"
        + _HEADER
        + "| FR-01.02 | Core | Two-factor login | Could | "
        "Users can add a second step to sign-in. | interview | unit |\n\n"
        "### FR-01.02 — Two-factor login\n\n"
        "- Scaffold-creation half - verified (auth.ts, test_auth.py): "
        "confirmed by running the existing suite.\n"
    )
    _seed_main(work, removed_at_base)
    wt = make_worktree(work, "frh-reinstate")
    reinstated = (
        "## 2. Functional Requirements\n\n"
        + _HEADER
        + "| FR-01.01 | Core | Login | Must | Users can sign in. | interview | unit |\n"
        "| FR-01.02 | Core | Two-factor login | Could | "
        "Users can add a second step to sign-in. | interview | unit |\n\n"
        "### FR-01.01 — Login\n\n"
        "#### Acceptance Criteria\n"
        "- (E) Given a registered user, when they submit valid credentials, "
        "then they are signed in.\n\n"
        "### FR-01.02 — Two-factor login\n\n"
        "- Scaffold-creation half - verified (auth.ts, test_auth.py): "
        "confirmed by running the existing suite.\n"
    )
    commit = _commit_on_worktree(wt, reinstated, "reinstate FR-01.02, criteria untouched")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is True


def test_reports_skip_when_commit_is_already_contained_in_the_trunk(
    git_origin_repo, make_worktree,
):
    """`_branch_base_commit` has no `mb != commit` guard: an already-merged
    commit resolves base_sha == commit, so base_text == head_text for every
    row. Reporting that as "clean" would claim rows were judged when none
    were — an honest skip is required instead."""
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-onmain")
    bad_row = (
        "| FR-01.02 | Core | Build copy-command (POST) | Must | "
        "Calls auth.ts login_handler() per ADR-042. | interview | unit |\n"
    )
    commit = _commit_on_worktree(wt, _clean_spec(extra_row=bad_row), "add bad FR row")
    _git(wt, "push", "origin", "HEAD:main")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is True
    assert "already contained in the trunk" in res.detail


def test_a_dirty_row_added_in_an_earlier_commit_is_still_caught_at_a_later_head(
    git_origin_repo, make_worktree,
):
    """The gate reads the merge-base RANGE, not just HEAD's own commit (doubt
    review, high): a dirty row can land two commits back on a branch, with an
    unrelated commit on top of it as HEAD. `_iterate_changed_paths`'s old
    silent single-commit fallback made this depend on which git call ran —
    this gate no longer calls it at all, so there is no fallback to fall
    into."""
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-earliercommit")
    bad_row = (
        "| FR-01.02 | Core | Build copy-command (POST) | Must | "
        "Calls auth.ts login_handler() per ADR-042. | interview | unit |\n"
    )
    _commit_on_worktree(wt, _clean_spec(extra_row=bad_row), "add bad FR row")
    _write(wt, "src/unrelated.py", "print('hi')\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "unrelated follow-up commit")
    head = _git(wt, "rev-parse", "HEAD").stdout.strip()
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, head)
    assert res.ok is False
    assert "FR-01.02" in res.detail


def test_a_non_canonical_id_this_run_added_is_still_flagged(
    git_origin_repo, make_worktree,
):
    """A row whose id fails the canonical `FR-XX.YY` shape never becomes a
    `FrTableRow` at all — invisible to `_row_map`, so `_touched_ids` and
    `_row_findings` never see it (doubt review, medium). A hand-typed
    `FR-1.02` for the canonical `FR-01.02` would otherwise let a dirty row
    slip past this gate purely by virtue of a typo the shared reader itself
    already declines to parse."""
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-nonid")
    bad_row = (
        "| FR-1.02 | Core | Build copy-command (POST) | Must | "
        "Calls auth.ts login_handler() per ADR-042. | interview | unit |\n"
    )
    commit = _commit_on_worktree(
        wt, _clean_spec(extra_row=bad_row), "add a non-canonical-id row",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "does not parse as a governed FR requirement" in res.detail
    assert "FR-1.02" in res.detail


def test_a_criterion_anchored_outside_the_recognised_ac_region_is_still_touched(
    git_origin_repo, make_worktree,
):
    """`_touched_ids` must use the SAME scope `_row_findings` uses
    (`fr_criteria.criteria_for`, whole-document) for deciding "did this row's
    criteria change" — `_layer_coverage_ac.criteria_digests` restricts to a
    recognised `## Acceptance Criteria` region when that region's anchor
    ID-SET matches the whole document's, which does not guarantee every
    BLOCK for a shared id is inside it (doubt review, medium). Here FR-01.01
    is anchored twice at HEAD: once inside the recognised region (unchanged)
    and once by a stray bold anchor just before it (new, and not a real
    criterion) — both resolve to the SAME id, so the region-restricted
    digest's id-set still matches the whole document's and the guard never
    fires, yet the stray block sits outside the region it returns."""
    work, _o = git_origin_repo
    header = ("## 2. Functional Requirements\n\n" + _HEADER +
              "| FR-01.01 | Core | Login | Must | Users can sign in. | "
              "interview | unit |\n\n")
    ac_section = (
        "## Acceptance Criteria\n\n"
        "### FR-01.01 — Login\n\n"
        "- (E) Given a registered user, when they submit valid credentials, "
        "then they are signed in.\n"
    )
    _seed_main(work, header + ac_section)
    wt = make_worktree(work, "frh-strayanchor")
    stray = (
        "**FR-01.01**\n"
        "- Scaffold-creation half - verified (auth.ts, test_auth.py): "
        "confirmed by running the existing suite.\n\n"
    )
    commit = _commit_on_worktree(
        wt, header + stray + ac_section, "add a stray anchor block",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "FR-01.01" in res.detail
    assert "Given" in res.detail
