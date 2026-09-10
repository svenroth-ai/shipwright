"""P3.6 THE KEYSTONE GATE — the never-silent guards (``_keystone_ac_digest``).

Covers AC-K9 (a)(b)(c) (never silent) and the cross-spec-path collision guards,
from ``.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md``. Split
out of ``test_keystone_ac_digest.py`` (Stage-2 code review, low — that module
crossed the 300-line guideline) as its own thematic unit: every test here
exists because a specific silent-failure mode was found and closed.

**Real git throughout.** Same rationale as its sibling: mocking the reader
would test the mock, not the one failure direction the design forbids.

Its siblings: AC-K1/K2/K3 and the minted change classes are in
``test_keystone_ac_digest.py``; AC-K9(d)'s reader-divergence guard and AC-K15's
drift pin are in ``test_keystone_readers.py``; AC-K13/K14 and the exit codes
are in ``test_check_keystone_ac_gate.py``; AC-K9(e)'s base-manifest three-way
read and AC-K11's base resolution are in ``test_keystone_gate_infra.py``; the
pure evaluator is in ``shared/tests/test_keystone_core*.py``.
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


def test_no_spec_path_in_either_manifest_warns_rather_than_reading_as_clean(repo):
    """Stage-2 code review, medium. Neither manifest naming a `spec_path` makes
    the whole loop below a no-op, so a trivially-empty change set would
    otherwise be silent about WHY -- indistinguishable from "nothing changed"
    when the real story is "there was nothing to compare". A freshly
    regenerated head manifest naming zero spec paths is itself a wiring signal,
    not evidence of a clean PR."""
    head = _git("rev-parse", "HEAD", cwd=repo)
    empty = {"requirements": {"ns::FR-01.01": {"id": "FR-01.01", "status": "active"}}}
    cs = kd.ac_change_set(repo, head, head, empty, empty)
    assert cs.is_empty
    assert any("spec_path" in w for w in cs.warnings)


def test_no_spec_path_read_suppresses_the_new_fr_arm_even_with_a_nonempty_base(repo):
    """Stage-2 code review, medium. The prior test passes the SAME manifest as
    head and base, which never exercises arm 2's risky combination: a base
    manifest that DOES carry an active requirement, alongside a head-only
    active FR, with NEITHER manifest naming a spec_path. Without the
    ``spec_text_was_read`` suppression, `base_fr_digests` and `head_minted`
    are empty because no spec text was ever scanned -- not because the base
    genuinely has no criteria -- so the head-only FR would read as
    `new_frs_without_criteria` (a HARD block) from a document nobody read."""
    head = _git("rev-parse", "HEAD", cwd=repo)
    base_manifest = {"requirements": {"ns::FR-01.01": {"id": "FR-01.01", "status": "active"}}}
    head_manifest = {"requirements": {
        "ns::FR-01.01": {"id": "FR-01.01", "status": "active"},
        "ns::FR-02.01": {"id": "FR-02.01", "status": "active"},  # new at head, no spec_path
    }}
    cs = kd.ac_change_set(repo, head, head, head_manifest, base_manifest)
    assert cs.is_empty
    assert cs.new_frs_without_criteria == []


def test_a_named_spec_path_absent_from_git_at_both_commits_also_suppresses_arm_2(repo):
    """Stage-2 code review, low; found round 6. ``spec_text_was_read`` asks
    whether text was actually READ, not merely whether a path was NAMED -- a
    ``spec_path`` present in both manifests but absent from git at BOTH
    commits (a stale or mistyped path, so `spec_text_at` returns `""` for
    each side, same as the no-path-named case) must suppress arm 2 exactly
    like the test above, not fall through to a false HARD block asserted
    from a document that was never actually read. Unlike the test above, this
    branch does NOT hit the top-of-function `not spec_paths` warning (a path
    WAS named), so it needs -- and, since Stage-1 round 18 (hard), now has --
    its OWN warning: silently suppressing here would repeat the exact defect
    this suppression exists to prevent, one layer removed."""
    head = _git("rev-parse", "HEAD", cwd=repo)
    stale_path = "Spec/design/does-not-exist.md"
    base_manifest = {"requirements": {
        "ns::FR-01.01": {"id": "FR-01.01", "status": "active", "spec_path": stale_path},
    }}
    head_manifest = {"requirements": {
        "ns::FR-01.01": {"id": "FR-01.01", "status": "active", "spec_path": stale_path},
        "ns::FR-02.01": {"id": "FR-02.01", "status": "active", "spec_path": stale_path},
    }}
    cs = kd.ac_change_set(repo, head, head, head_manifest, base_manifest)
    assert cs.is_empty
    assert cs.new_frs_without_criteria == []
    assert any("none resolved to any content" in w for w in cs.warnings)


def test_one_stale_path_among_several_warns_even_though_a_sibling_was_read(repo):
    """Code robustness follow-up (P4.4 triage card). ``spec_text_was_read`` is
    computed ONCE across ALL named spec paths, so with multiple spec paths where
    one resolves to no content at either commit and another has real content,
    the aggregate flag stays True -- correctly, per design, so arm 2's
    suppression does NOT apply to a head-only FR anchored to the good path (it
    is judged against text that WAS read). But the stale path itself used to get
    NO warning at all, because the aggregate-empty branch above is keyed on
    ``not spec_text_was_read`` and never fires once a sibling path succeeds --
    the exact silence the module docstring calls the one failure worse than
    over-firing, one layer deeper than the all-paths-stale case already
    covered above."""
    good_path = "docs/spec.md"  # already committed by `make_repo`
    stale_path = "Spec/design/does-not-exist.md"
    head = _git("rev-parse", "HEAD", cwd=repo)
    base_manifest = {"requirements": {
        "ns::FR-01.01": {"id": "FR-01.01", "status": "active", "spec_path": good_path},
    }}
    head_manifest = {"requirements": {
        "ns::FR-01.01": {"id": "FR-01.01", "status": "active", "spec_path": good_path},
        "ns::FR-03.01": {"id": "FR-03.01", "status": "active", "spec_path": stale_path},
    }}
    cs = kd.ac_change_set(repo, head, head, head_manifest, base_manifest)
    # The suppression stays keyed on the aggregate flag (unchanged by design):
    # FR-03.01 is a new active FR at head with no minted criteria anywhere, and
    # `spec_text_was_read` is True because `good_path` was read -- so it DOES
    # fire, exactly as the aggregate design intends.
    assert cs.new_frs_without_criteria == ["FR-03.01"]
    assert any(
        stale_path in w and good_path not in w and "even though another" in w
        for w in cs.warnings
    ), cs.warnings


# --------------------------------------------------------------------------
# Cross-spec-path collision (Stage-3 doubt review, medium)
# --------------------------------------------------------------------------

def test_two_spec_files_minting_the_same_ac_id_at_head_raises_read_error(repo):
    """Stage-3 doubt review, medium. ``dict.update`` across the ``_spec_paths`` loop is
    last-write-wins: a SECOND spec file added in this same PR that re-anchors
    an ALREADY-EDITED ``(fr_id, ac_id)`` with its OLD text used to silently
    overwrite the genuine edit's digest, reverting ``head_minted`` back to
    ``base_minted`` and erasing ``changed`` for a criterion this PR did
    change. That is exactly the "no ACs changed" silence the module's own
    docstring names as the one failure worse than over-firing. Written to
    fail against that phrasing: a second head-minted claim on the same id
    must raise, never silently win or lose."""
    base = _git("rev-parse", "HEAD", cwd=repo)
    _commit_spec(repo, BASE_SPEC.replace(
        "The widget must fizz.", "The widget must fizz TWICE."))
    second = "docs/second-spec.md"
    (repo / second).write_text(BASE_SPEC, encoding="utf-8")  # OLD AC01 text, same id
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "add a second spec re-anchoring FR-01.01/AC01", cwd=repo)
    head = _git("rev-parse", "HEAD", cwd=repo)
    head_manifest = _manifest()
    head_manifest["requirements"]["ns::FR-01.01-dup"] = {
        "id": "FR-01.01", "status": "active", "spec_path": second,
    }
    with pytest.raises(kd.ReadError, match=r"FR-01\.01/AC01 is minted in both"):
        kd.ac_change_set(repo, base, head, head_manifest, _manifest())


def test_two_spec_files_heading_anchoring_the_same_fr_with_no_ac_markers_raises(repo):
    """Stage-2 code review, medium. The AC-id collision guard above only fires
    when both spec files MINT an ``[ACnn]``-marked criterion for the shared id;
    an unminted FR-heading block (no ``[ACnn]`` markers at all) never touches
    ``h_minted``, so this pins the SIBLING guard on ``head_fr_digest_from`` --
    previously untested -- which must independently catch two spec files
    heading-anchoring the same FR id at head."""
    base = _git("rev-parse", "HEAD", cwd=repo)
    second = "docs/second-spec.md"
    (repo / second).write_text(
        "### FR-01.01: Widgets\n\nSome unmarked prose describing the widget.\n",
        encoding="utf-8",
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "add a second spec re-anchoring the FR-01.01 heading", cwd=repo)
    head = _git("rev-parse", "HEAD", cwd=repo)
    head_manifest = _manifest()
    head_manifest["requirements"]["ns::FR-01.01-dup"] = {
        "id": "FR-01.01", "status": "active", "spec_path": second,
    }
    with pytest.raises(kd.ReadError, match=r"FR-01\.01 is heading-anchored in both"):
        kd.ac_change_set(repo, base, head, head_manifest, _manifest())
