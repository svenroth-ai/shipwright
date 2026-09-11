"""`check_fr_hygiene_on_touched_rows` — Stage-3 doubt-review regressions,
round 2 (iterate-2026-09-06-fr-hygiene-touched-rows).

Split into its own file from the start (rather than growing
`test_check_fr_hygiene_delta_scope.py` past the 300-line guideline again):
a second, fresh-context doubt-review pass — run after the first round's five
fixes already landed — found four more genuine gaps: a row moved between two
`spec.md` files was re-judged in full instead of on the delta, a criterion
folded in under a mistyped (non-canonical) anchor id was silently invisible
to every FR-catalogue check, a duplicate id at HEAD let a dict-based lookup
silently shadow a dirty new row behind an untouched clean one, and
`_new_reject_findings`'s set-based comparison lost multiplicity. Shares
helpers/fixtures with the sibling modules rather than duplicating them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_check_fr_hygiene import (  # noqa: E402
    _HEADER,
    _RUN,
    _SPEC,
    _clean_spec,
    _commit_on_worktree,
    _seed_main,
)
from test_integrate_main import _git, _write  # noqa: E402
from tools.verifiers import fr_hygiene as fh  # noqa: E402

_SPEC_B = ".shipwright/planning/02-other/spec.md"


def test_a_row_moved_between_spec_files_is_not_reflagged_when_unchanged(
    git_origin_repo, make_worktree,
):
    """Row identity is the FR id ACROSS every touched spec path, not scoped to
    one file's own history (doubt review, high): `fr-authoring.md` §4's own
    prescribed remedy for "filed in the wrong split" is moving a row to a
    different `spec.md`. A dirty legacy row this run does nothing but
    relocate must not be judged in full purely because its destination path
    has no base-side history of it — `global_base_rows` in `fr_hygiene.py`
    must find its true prior content at the OLD path instead."""
    work, _o = git_origin_repo
    dirty_row = (
        "| FR-01.02 | Core | Build copy-command (POST) | Must | "
        "Calls auth.ts login_handler() per ADR-042. | interview | unit |\n"
    )
    _seed_main(work, _clean_spec(extra_row=dirty_row))
    wt = make_worktree(work, "frh-move-unchanged")
    _write(wt, _SPEC, _clean_spec())  # path A: row removed
    _write(
        wt, _SPEC_B,
        "## 2. Functional Requirements\n\n" + _HEADER + dirty_row,
    )  # path B: row relocated, byte-identical
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "move FR-01.02 to a different split")
    commit = _git(wt, "rev-parse", "HEAD").stdout.strip()
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is True
    assert "FR-01.02" not in res.detail


def test_a_row_moved_between_spec_files_is_flagged_for_a_violation_added_during_the_move(
    git_origin_repo, make_worktree,
):
    """The move itself must not exempt a violation this run introduces WHILE
    relocating the row — only a byte-identical move is exempt; the fallback
    used to establish "unchanged" must still let a genuine edit through."""
    work, _o = git_origin_repo
    clean_row = (
        "| FR-01.02 | Core | Password reset | Should | "
        "Users who forget their password can reset it by email. | interview | unit |\n"
    )
    _seed_main(work, _clean_spec(extra_row=clean_row))
    wt = make_worktree(work, "frh-move-dirtied")
    _write(wt, _SPEC, _clean_spec())
    dirtied_row = (
        "| FR-01.02 | Core | Password reset | Should | "
        "Calls auth.ts resetPassword() per ADR-042. | interview | unit |\n"
    )
    _write(
        wt, _SPEC_B,
        "## 2. Functional Requirements\n\n" + _HEADER + dirtied_row,
    )
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "move FR-01.02 and smuggle detail in during the move")
    commit = _git(wt, "rev-parse", "HEAD").stdout.strip()
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "FR-01.02" in res.detail


def test_orphan_criterion_anchor_with_non_canonical_id_is_flagged(
    git_origin_repo, make_worktree,
):
    """A criterion anchored under a heading id that is not canonical
    `FR-XX.YY` shape (e.g. a missing zero-pad) never joins its intended row's
    pool on either side of the id comparison — invisible to every
    FR-catalogue check unless this gate itself surfaces the mismatch (doubt
    review, medium)."""
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-orphananchor")
    mistyped = _clean_spec() + (
        "\n### FR-1.02 — Password reset\n\n"
        "- Scaffold-creation half - verified (auth.ts, test_auth.py): "
        "confirmed by running the existing suite.\n"
    )
    commit = _commit_on_worktree(wt, mistyped, "fold a criterion under a mistyped anchor id")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "FR-1.02" in res.detail
    assert "non-canonical id" in res.detail


@pytest.mark.covers("FR-01.11/AC06")
def test_a_new_duplicate_id_at_head_is_flagged(git_origin_repo, make_worktree):
    """AC06 (negative space): a retired/guessed number is never reused —
    enforced here by catching a NEW duplicate FR id at HEAD, since a duplicate
    is exactly what a bad guess or a reused retired number produces. An id
    with more than one active row at HEAD is an ambiguous identity a
    dict-based lookup elsewhere would silently resolve to whichever occurs
    LAST — a dirty new row added ABOVE an existing clean legacy row sharing
    its id would otherwise be shadowed and never judged at all (doubt
    review, high)."""
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-dupid")
    dirty_first = (
        "| FR-01.01 | Core | Build copy-command (POST) | Must | "
        "Calls auth.ts login_handler() per ADR-042. | interview | unit |\n"
    )
    duplicated = (
        "## 2. Functional Requirements\n\n"
        + _HEADER
        + dirty_first
        + "| FR-01.01 | Core | Login | Must | Users can sign in. | interview | unit |\n"
        "\n### FR-01.01 — Login\n\n"
        "#### Acceptance Criteria\n"
        "- (E) Given a registered user, when they submit valid credentials, "
        "then they are signed in.\n"
    )
    commit = _commit_on_worktree(
        wt, duplicated, "duplicate FR-01.01 with a dirty row above it",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "duplicate id" in res.detail


def test_a_new_duplicate_id_split_across_two_touched_files_is_flagged(
    git_origin_repo, make_worktree,
):
    """FR ids are catalog-wide, not scoped to one file (Tier-3 PR review, PR
    #679): a NEW duplicate with exactly ONE occurrence in each of two touched
    spec files was invisible to a per-file duplicate count — neither file
    alone contains more than one occurrence of the id. Both files must be
    touched by this same commit for the pooled comparison to see them
    together; ``_SPEC`` picks up an unrelated clean row so it appears in the
    diff alongside the newly added ``_SPEC_B``."""
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-dupid-crossfile")
    unrelated_clean_row = (
        "| FR-01.02 | Core | Password reset | Should | "
        "Users who forget their password can reset it by email. | interview | unit |\n"
    )
    _write(wt, _SPEC, _clean_spec(extra_row=unrelated_clean_row))
    _write(
        wt, _SPEC_B,
        "## 2. Functional Requirements\n\n"
        + _HEADER
        + "| FR-01.01 | Other | Sign in | Must | Users can sign in. | interview | unit |\n",
    )
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "introduce FR-01.01 again in a second split")
    commit = _git(wt, "rev-parse", "HEAD").stdout.strip()
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "duplicate id" in res.detail
    assert "FR-01.01" in res.detail


def test_editing_one_occurrence_of_a_pre_existing_duplicate_id_is_flagged(
    git_origin_repo, make_worktree,
):
    """`_row_map` keeps whichever duplicate occurrence is LAST in document
    order, so editing the OTHER (non-surviving) occurrence's content is
    invisible to `_touched_ids` — the surviving occurrence never changed
    (Tier-3 PR review, PR #679, first finding). A duplicate id already
    present at base is normally out of this gate's "touched only" scope, but
    an edit to what one of its occurrences SAYS must still surface — the old
    "new duplicate ids only" comparison excluded it because the id was
    already duplicated at base, count unchanged."""
    work, _o = git_origin_repo
    base_content = (
        "## 2. Functional Requirements\n\n"
        + _HEADER
        + "| FR-01.01 | Core | Login | Must | Users can sign in. | interview | unit |\n"
        "| FR-01.01 | Core | Login (dup) | Must | Users can sign in via SSO. | interview | unit |\n"
        "\n### FR-01.01 — Login\n\n"
        "#### Acceptance Criteria\n"
        "- (E) Given a registered user, when they submit valid credentials, "
        "then they are signed in.\n"
    )
    _seed_main(work, base_content)
    wt = make_worktree(work, "frh-dupid-edit-nonsurviving")
    edited_content = (
        "## 2. Functional Requirements\n\n"
        + _HEADER
        + "| FR-01.01 | Core | Login | Must | "
        "Calls auth.ts login_handler() per ADR-042. | interview | unit |\n"
        "| FR-01.01 | Core | Login (dup) | Must | Users can sign in via SSO. | interview | unit |\n"
        "\n### FR-01.01 — Login\n\n"
        "#### Acceptance Criteria\n"
        "- (E) Given a registered user, when they submit valid credentials, "
        "then they are signed in.\n"
    )
    commit = _commit_on_worktree(
        wt, edited_content, "edit the non-surviving occurrence of a pre-existing duplicate",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "duplicate id" in res.detail
    assert "FR-01.01" in res.detail


def test_editing_an_already_rejected_rows_content_is_flagged(
    git_origin_repo, make_worktree,
):
    """`_new_reject_findings` used to key solely on `(id, reason)` — editing
    an already-rejected row's CONTENT while its id and rejection reason stay
    the same matched an existing base key and was silently absorbed as
    "already there" (Tier-3 PR review, PR #679, second finding). The
    rejected row never produces an `FrTableRow`, so nothing else in this gate
    ever judges the changed content either — the `raw` fingerprint must catch
    it."""
    legacy_bad_id_row = (
        "| FR-1.02 | Core | Password reset | Must | "
        "Users who forget their password can reset it by email. | interview | unit |\n"
    )
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec(extra_row=legacy_bad_id_row))
    wt = make_worktree(work, "frh-reject-content-edit")
    edited_bad_id_row = (
        "| FR-1.02 | Core | Password reset | Must | "
        "Calls auth.ts resetPassword() per ADR-042. | interview | unit |\n"
    )
    commit = _commit_on_worktree(
        wt, _clean_spec(extra_row=edited_bad_id_row),
        "edit the content of an already-rejected malformed-id row",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "does not parse as a governed FR requirement" in res.detail


def test_a_second_row_with_the_same_malformed_id_and_reason_is_flagged(
    git_origin_repo, make_worktree,
):
    """`_new_reject_findings` compares by MULTIPLICITY, not set membership: a
    legacy reject sharing the same (id, reason) pair as a NEW row this run
    adds must not mask the new one (doubt review, low)."""
    work, _o = git_origin_repo
    legacy_bad_id_row = (
        "| FR-1.02 | Core | Build copy-command (POST) | Must | "
        "Calls auth.ts login_handler() per ADR-042. | interview | unit |\n"
    )
    _seed_main(work, _clean_spec(extra_row=legacy_bad_id_row))
    wt = make_worktree(work, "frh-dupreject")
    second_bad_id_row = (
        "| FR-1.02 | Core | Another feature (PATCH) | Must | "
        "Calls src/thing.ts run() per ADR-043. | interview | unit |\n"
    )
    commit = _commit_on_worktree(
        wt, _clean_spec(extra_row=legacy_bad_id_row + second_bad_id_row),
        "add a second row with the same malformed id",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "does not parse as a governed FR requirement" in res.detail
