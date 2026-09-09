"""P3.6 THE KEYSTONE GATE — per-AC change detection (``_keystone_ac_digest``).

Covers AC-K1 (docs-only / prose-outside-a-criterion), AC-K2 (the naming arm),
AC-K3 (reorder + reflow are not changes) and AC-K9 (a)(b)(c) (never silent), from
``.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md``.

**Real git throughout.** This module is the gate's only git-facing half, and a
wrong invocation here fails in the one direction the design forbids: silently,
as "no ACs changed". Mocking the reader would test the mock.

Its siblings: AC-K9(d)'s reader-divergence guard and AC-K15's drift pin are in
``test_keystone_readers.py``; AC-K9(e)'s base-manifest three-way read, the exit
codes and AC-K11/K13/K14 are in ``test_check_keystone_ac_gate.py``; the pure
evaluator is in ``shared/tests/test_keystone_core*.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from verifiers import _keystone_ac_digest as kd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import BASE_SPEC  # noqa: E402
from _keystone_repo import commit_spec as _commit_spec  # noqa: E402
from _keystone_repo import git as _git  # noqa: E402
from _keystone_repo import make_repo  # noqa: E402
from _keystone_repo import manifest as _manifest  # noqa: E402


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def _change_set(repo: Path, head_sha: str, base_sha: str = "HEAD~1"):
    resolved_base = _git("rev-parse", base_sha, cwd=repo)
    return kd.ac_change_set(repo, resolved_base, head_sha, _manifest(), _manifest())


# --------------------------------------------------------------------------
# AC-K1 / AC-K3 — what is NOT a change
# --------------------------------------------------------------------------

def test_a_commit_touching_no_criterion_yields_an_empty_change_set(repo):
    """AC-K1 — the docs-only pass falls out with zero machinery."""
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "docs", cwd=repo)
    assert _change_set(repo, _git("rev-parse", "HEAD", cwd=repo)).is_empty


def test_editing_spec_prose_outside_every_criterion_is_not_a_change(repo):
    """AC-K1's second half: even a spec.md edit passes when it lands on prose."""
    head = _commit_spec(repo, BASE_SPEC.replace(
        "Some prose that is not a criterion at all.",
        "Some COMPLETELY REWRITTEN prose that is still not a criterion.",
    ))
    assert _change_set(repo, head).is_empty


def test_reordering_two_criteria_within_one_fr_is_not_a_change(repo):
    """AC-K3 — the ``[ACnn]`` marker travels with the line, so identity survives
    a move. Today's FR-POOLED digest fires on any reordering; this is one of the
    two properties per-AC digests buy for free."""
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC01] The widget must fizz.\n- [AC02] The widget must buzz.",
        "- [AC02] The widget must buzz.\n- [AC01] The widget must fizz.",
    ))
    assert _change_set(repo, head).is_empty


def test_rewrapping_a_criterions_continuation_lines_is_not_a_change(repo):
    """AC-K3's second half — ``block_criteria`` joins continuations and
    normalises whitespace BEFORE the digest is taken."""
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC01] The widget must fizz.",
        "- [AC01] The widget\n  must\n  fizz.",
    ))
    assert _change_set(repo, head).is_empty


# --------------------------------------------------------------------------
# The minted change classes
# --------------------------------------------------------------------------

def test_editing_a_minted_criterion_lands_in_changed(repo):
    head = _commit_spec(repo, BASE_SPEC.replace(
        "The widget must fizz.", "The widget must fizz TWICE."))
    cs = _change_set(repo, head)
    assert cs.changed == {("FR-01.01", "AC01")}
    assert cs.added == set() and cs.removed == set()


def test_a_new_minted_criterion_lands_in_added_never_in_changed(repo):
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC03] The gadget must whirr.",
        "- [AC03] The gadget must whirr.\n- [AC04] The gadget must click.",
    ))
    cs = _change_set(repo, head)
    assert cs.added == {("FR-01.02", "AC04")}
    assert cs.changed == set()


def test_a_deleted_minted_criterion_lands_in_removed(repo):
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC02] The widget must buzz.\n", ""))
    assert _change_set(repo, head).removed == {("FR-01.01", "AC02")}


def test_moving_a_criterion_between_frs_is_a_remove_plus_an_add(repo):
    """Ids are never reused, so an id cannot appear under two FRs — the move
    reads as a deletion and an addition, which is the honest description."""
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC02] The widget must buzz.\n", "",
    ).replace(
        "- [AC03] The gadget must whirr.",
        "- [AC03] The gadget must whirr.\n- [AC04] The widget must buzz.",
    ))
    cs = _change_set(repo, head)
    assert cs.removed == {("FR-01.01", "AC02")}
    assert cs.added == {("FR-01.02", "AC04")}


# --------------------------------------------------------------------------
# AC-K2 — the naming arm (unminted criteria)
# --------------------------------------------------------------------------

def test_deleting_a_markers_from_a_minted_criterion_fires_the_naming_arm(repo):
    """AC-K2(a) — the dodge: strip the ``[ACnn]`` and the framework can no longer
    name what changed. The criterion becomes unminted, its digest is absent from
    base's unminted set, so arm 1 fires."""
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC01] The widget must fizz.", "- The widget must fizz."))
    cs = _change_set(repo, head)
    assert [fr for fr, _ in cs.unminted_changed] == ["FR-01.01"]
    assert cs.removed == {("FR-01.01", "AC01")}


def test_adding_an_unminted_criterion_fires_the_naming_arm(repo):
    """AC-K2(b) — the sibling case. ``added`` is about MINTED ids only; an added
    and unminted criterion does block."""
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC03] The gadget must whirr.",
        "- [AC03] The gadget must whirr.\n- The gadget must also ping.",
    ))
    cs = _change_set(repo, head)
    assert cs.unminted_changed == [("FR-01.02", "The gadget must also ping.")]


def test_an_unminted_criterion_that_survives_byte_identical_does_not_fire(repo):
    """AC-K2(c) — pre-existing backlog is p3.7's, not p3.6's."""
    with_unminted = BASE_SPEC.replace(
        "- [AC03] The gadget must whirr.",
        "- [AC03] The gadget must whirr.\n- The gadget must also ping.",
    )
    _commit_spec(repo, with_unminted, "introduce the unminted criterion")
    head = _commit_spec(repo, with_unminted.replace(
        "The widget must buzz.", "The widget must buzz LOUDLY."))
    cs = _change_set(repo, head)
    assert cs.unminted_changed == []
    assert cs.changed == {("FR-01.01", "AC02")}


def test_an_unminted_criterion_moved_verbatim_between_frs_still_fires(repo):
    """The digest covers ``(fr_id, text)``, never bare text: a bare-text digest
    would cancel out on a verbatim move and the change would go undetected."""
    with_unminted = BASE_SPEC.replace(
        "- [AC02] The widget must buzz.",
        "- [AC02] The widget must buzz.\n- An unowned criterion.",
    )
    _commit_spec(repo, with_unminted, "introduce")
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC03] The gadget must whirr.",
        "- [AC03] The gadget must whirr.\n- An unowned criterion.",
    ))
    cs = _change_set(repo, head)
    assert cs.unminted_changed == [("FR-01.02", "An unowned criterion.")]


# --------------------------------------------------------------------------
# AC-K9 (a)(b)(c) — never silent
# --------------------------------------------------------------------------

def test_an_untrustworthy_marker_at_head_raises_read_error(repo):
    """AC-K9(a). Two criteria under one FR carrying the same number breaks
    "never reused", which is the whole basis of AC identity."""
    head = _commit_spec(repo, BASE_SPEC.replace(
        "- [AC02] The widget must buzz.", "- [AC01] The widget must buzz."))
    with pytest.raises(kd.ReadError):
        _change_set(repo, head)


def test_an_untrustworthy_marker_at_base_warns_and_treats_base_as_empty(repo):
    """AC-K9(b). Asymmetric on purpose: a base commit is already merged and
    cannot have been authored by this PR, so leniency there is not exploitable —
    and it lets a branch forked before the mint pass cleanly."""
    _commit_spec(repo, BASE_SPEC.replace(
        "- [AC02] The widget must buzz.", "- [AC01] The widget must buzz."),
        "a broken base")
    head = _commit_spec(repo, BASE_SPEC)
    cs = _change_set(repo, head)
    assert cs.warnings and "base commit" in cs.warnings[0]
    assert cs.added == {("FR-01.01", "AC01"), ("FR-01.01", "AC02"), ("FR-01.02", "AC03")}
    assert cs.changed == set()


def test_an_unreadable_side_raises_rather_than_reporting_no_change(repo):
    """AC-K9(c) — ``spec_text_at`` returning ``None`` is an infrastructure fault.
    Collapsing it into "" would make a broken repository look like a spec with no
    criteria, i.e. a false green exactly where the gate must fail closed."""
    head = _git("rev-parse", "HEAD", cwd=repo)
    with pytest.raises(kd.ReadError):
        kd.ac_change_set(repo, "0" * 40, head, _manifest(), _manifest())


def test_spec_paths_are_the_union_of_both_manifests(repo):
    """A spec file this PR REMOVES is only visible from the base side. Head-only
    scanning would hide its criteria — including from ``binding_removed``, the
    very subtractability ruling Q2 says must not be freely available."""
    other = "docs/other-spec.md"
    (repo / other).write_text(
        "### FR-02.01: Others\n\n- [AC01] The other must hum.\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "add second spec", cwd=repo)
    base = _git("rev-parse", "HEAD", cwd=repo)
    (repo / other).unlink()
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "remove second spec", cwd=repo)
    head = _git("rev-parse", "HEAD", cwd=repo)
    base_manifest = _manifest()
    base_manifest["requirements"]["ns::FR-02.01"] = {
        "id": "FR-02.01", "status": "active", "spec_path": other,
    }
    cs = kd.ac_change_set(repo, base, head, _manifest(), base_manifest)
    assert ("FR-02.01", "AC01") in cs.removed
