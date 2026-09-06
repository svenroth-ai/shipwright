"""`check_fr_hygiene_on_touched_rows` — Tier-3 PR-review regressions, round 3/4
(iterate-2026-09-06-fr-hygiene-touched-rows).

Split into its own file (rather than growing `test_check_fr_hygiene_doubt3.py`
past the 300-line guideline again): two more genuine gaps the automated
Tier-3 reviewer (`openai/gpt-5.6-luna`, PR #679) found after round 2 landed —
duplicate-id detection only pooled TOUCHED spec files, so a new row colliding
with an id in an untouched catalogue file slipped through; and the rejected-
row content fingerprint keyed on the reader's own display `raw` field, which
is truncated to 200 characters, so an edit landing entirely past that
boundary kept the same key as before. Shares helpers/fixtures with the
sibling modules rather than duplicating them.
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
from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools.verifiers import fr_hygiene as fh  # noqa: E402

_SPEC_B = ".shipwright/planning/02-other/spec.md"


def test_a_new_anchor_with_a_canonical_prefix_but_extra_suffix_is_flagged(
    git_origin_repo, make_worktree,
):
    """`CANONICAL_FR_RE.fullmatch`, not `.match` (Tier-3 PR review round 5, PR
    #679): a new criterion anchored under an id carrying a canonical PREFIX
    but extra trailing characters (`FR-01.02.03`) must still be reported as
    non-canonical — it is exactly the shape a prefix-only check would let
    through. (`CANONICAL_FR_RE`'s own `$` anchor already rejects this under
    `.match` too — empirically confirmed before this test was written — but
    `fullmatch` removes the ambiguity and this test pins the behavior either
    way.)"""
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-orphananchor-prefix-suffix")
    mistyped = _clean_spec() + (
        "\n### FR-01.02.03 — Password reset\n\n"
        "- Scaffold-creation half - verified (auth.ts, test_auth.py): "
        "confirmed by running the existing suite.\n"
    )
    commit = _commit_on_worktree(
        wt, mistyped, "fold a criterion under a canonical-prefixed anchor id",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "FR-01.02.03" in res.detail
    assert "non-canonical id" in res.detail


def test_a_new_duplicate_id_against_an_untouched_catalog_file_is_flagged(
    git_origin_repo, make_worktree,
):
    """FR ids are catalog-wide identity (Tier-3 PR review round 3, PR #679):
    the OTHER occurrence of a duplicate can live in a `spec.md` this run's
    diff never touches at all. Pooling only TOUCHED paths (the round-2 fix)
    never even read that untouched file's content, so a new row reusing an
    id already used elsewhere in the untouched catalogue slipped through —
    only one occurrence (the new one) was ever counted."""
    work, _o = git_origin_repo
    base_a = (
        "## 2. Functional Requirements\n\n"
        + _HEADER
        + "| FR-01.02 | Core | Password reset | Should | "
        "Users who forget their password can reset it by email. | interview | unit |\n"
    )
    base_b = (
        "## 2. Functional Requirements\n\n"
        + _HEADER
        + "| FR-01.01 | Core | Login | Must | Users can sign in. | interview | unit |\n"
        "\n### FR-01.01 — Login\n\n"
        "#### Acceptance Criteria\n"
        "- (E) Given a registered user, when they submit valid credentials, "
        "then they are signed in.\n"
    )
    _set_repo_identity(work)
    _write(work, _SPEC, base_a)
    _write(work, _SPEC_B, base_b)
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed a two-file FR catalogue")
    _git(work, "push", "origin", "main")
    wt = make_worktree(work, "frh-dupid-untouched-catalog")
    head_a = base_a + (
        "| FR-01.01 | Core | Login (again) | Must | "
        "Users can sign in too. | interview | unit |\n"
    )
    commit = _commit_on_worktree(
        wt, head_a, "add a new row reusing an id from an untouched catalogue file",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "duplicate id" in res.detail
    assert "FR-01.01" in res.detail


def test_an_existing_non_canonical_anchors_edited_criterion_is_flagged(
    git_origin_repo, make_worktree,
):
    """An anchor id that was ALREADY non-canonical at base is not exempt from
    reporting just because this run did not invent the malformed id (Tier-3
    PR review round 6, PR #679): the round-2/round-5 version excluded any
    ``fr_id`` present in ``base_ids`` outright, so editing or supplementing
    the criterion text under an existing ``FR-1.02``-shaped anchor was
    silently invisible — same blast radius as a brand-new malformed anchor,
    since neither ever joins a canonical table row's pool."""
    work, _o = git_origin_repo
    base_extra = (
        "\n### FR-1.02 — Password reset\n\n"
        "#### Acceptance Criteria\n"
        "- (E) Given a user with a forgotten password, when they request a "
        "reset, then they receive an email.\n"
    )
    _seed_main(work, _clean_spec(extra_body=base_extra))
    wt = make_worktree(work, "frh-existing-nonrecanonical-anchor-edited")
    head_extra = (
        "\n### FR-1.02 — Password reset\n\n"
        "#### Acceptance Criteria\n"
        "- (E) Given a user with a forgotten password, when they request a "
        "reset, then they receive an email within five minutes.\n"
    )
    commit = _commit_on_worktree(
        wt, _clean_spec(extra_body=head_extra),
        "edit the criterion text under an already-existing non-canonical anchor",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "FR-1.02" in res.detail
    assert "non-canonical id" in res.detail


def test_editing_an_already_rejected_row_past_the_raw_truncation_boundary_is_flagged(
    git_origin_repo, make_worktree,
):
    """The reader's own ``raw`` field is truncated to 200 characters for
    display — keying the reject comparison on it alone (round-2 fix) let an
    edit landing entirely AFTER character 200 keep an identical
    ``(id, reason, raw[:200])`` triple as before and stay silently absorbed
    as unchanged (Tier-3 PR review round 3, PR #679). ``raw_digest`` (a
    sha256 of the FULL cell content) is required to catch it — this pins
    the exact truncation-boundary case, not just "any content edit"."""
    common = "X" * 159  # + the 41-char cell prefix below = exactly 200 chars
    legacy_row = (
        "| FR-1.02 | Core | Password reset | Must | "
        + common + "-legacy-tail | interview | unit |\n"
    )
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec(extra_row=legacy_row))
    wt = make_worktree(work, "frh-reject-truncation-boundary")
    edited_row = (
        "| FR-1.02 | Core | Password reset | Must | "
        + common + "-EDITED-tail-past-200-chars | interview | unit |\n"
    )
    commit = _commit_on_worktree(
        wt, _clean_spec(extra_row=edited_row),
        "edit an already-rejected row's content beyond the 200-char raw truncation",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "does not parse as a governed FR requirement" in res.detail
