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


def test_a_new_duplicate_id_at_head_is_flagged(git_origin_repo, make_worktree):
    """An id with more than one active row at HEAD is an ambiguous identity a
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
