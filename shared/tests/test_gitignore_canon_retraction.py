"""Tests for the gitignore-canon SUPERSEDED (retraction) mechanism.

Sibling of ``test_gitignore_canon_merge.py`` (split out to stay under the
300-line guideline), covering the gap doubt-reviewer's HIGH #1 found in
iterate-2026-08-08-track-decision-drops: ``gitignore_canon.py``'s merge was
add-only, so an already-adopted project still carrying the OLD blanket
``/.shipwright/agent_docs/decision-drops/`` ignore would never self-heal —
the directory stays ignored forever, F6's `git add` on it silently no-ops,
and `git worktree remove` destroys every future iterate's ADR drop. The
SUPERSEDED block (a second marker-delimited section in the template) closes
that: a rule listed there is actively stripped from a target's managed
block, in the same pass that adds its canonical replacement(s).
"""

from __future__ import annotations

from pathlib import Path

# conftest.py adds shared/scripts to sys.path; lib is a package under it.
from lib.gitignore_canon import (
    BEGIN_MARKER,
    END_MARKER,
    merge_canonical_block,
    plan_merge,
    read_canonical_rules,
    read_superseded_rules,
)

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "shipwright-gitignore.template"
)

_STALE_DECISION_DROPS_RULE = "/.shipwright/agent_docs/decision-drops/"
_NARROW_DECISION_DROPS_REPLACEMENTS = {
    "/.shipwright/agent_docs/decision-drops/INDEX.md",
    "/.shipwright/agent_docs/decision-drops/*.tmp",
}


def test_read_superseded_rules_includes_decision_drops_retraction() -> None:
    assert _STALE_DECISION_DROPS_RULE in read_superseded_rules(TEMPLATE)
    # It must NOT also be canonical — narrowed, not merely duplicated.
    assert _STALE_DECISION_DROPS_RULE not in read_canonical_rules(TEMPLATE)


def test_superseded_entries_stay_shipwright_namespaced() -> None:
    """opus-plan-reviewer, 2026-08-16: position + exact-text-match is a safe
    retraction-ownership proxy only because every SUPERSEDED entry is a
    curated ``/.shipwright/``-namespaced literal a project would not
    plausibly author independently — documented as a standing constraint in
    the template's SUPERSEDED header, but a doc comment alone doesn't stop a
    future edit from adding a generic-looking entry that silently inherits
    the same broad-strip reach. Enforce it mechanically instead."""
    for rule in read_superseded_rules(TEMPLATE):
        assert rule.startswith("/.shipwright/"), (
            f"superseded entry {rule!r} is not /.shipwright/-namespaced — "
            "the retraction's position+exact-match ownership assumption "
            "only holds for entries this specific; see the template's own "
            "SUPERSEDED header for why"
        )


def _gitignore_with_stale_blanket_rule() -> str:
    """A managed block as an already-adopted project (pre-2026-08-08) would
    still carry it: every current canonical rule EXCEPT the two narrow
    decision-drops ones, PLUS the old blanket rule they replaced."""
    canonical = read_canonical_rules(TEMPLATE)
    stale_lines = [
        r for r in canonical if r not in _NARROW_DECISION_DROPS_REPLACEMENTS
    ] + [_STALE_DECISION_DROPS_RULE]
    return "\n".join([BEGIN_MARKER, *stale_lines, END_MARKER]) + "\n"


def test_merge_retracts_superseded_rule_and_adds_replacement(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text(_gitignore_with_stale_blanket_rule(), encoding="utf-8")
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    text = gi.read_text(encoding="utf-8")

    assert result["retracted"] == [_STALE_DECISION_DROPS_RULE]
    assert _STALE_DECISION_DROPS_RULE not in text.splitlines()
    assert "/.shipwright/agent_docs/decision-drops/INDEX.md" in result["added"]
    assert "/.shipwright/agent_docs/decision-drops/*.tmp" in result["added"]
    for rule in read_canonical_rules(TEMPLATE):
        assert rule in text.splitlines()


def test_merge_retraction_is_idempotent(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text(_gitignore_with_stale_blanket_rule(), encoding="utf-8")
    merge_canonical_block(tmp_path, template_path=TEMPLATE)
    before = gi.read_text(encoding="utf-8")
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    after = gi.read_text(encoding="utf-8")
    assert result["action"] == "unchanged"
    assert result["retracted"] == []
    assert before == after


def test_merge_retracts_a_superseded_rule_before_the_managed_block(tmp_path: Path) -> None:
    """Field data (shipwright-webui, verified 2026-08-15) disproves the old
    assumption that a superseded rule outside the managed block must be a
    user's own hand-written line: webui's ``/.shipwright/agent_docs/
    decision-drops/`` blanket ignore was written by ``/shipwright-adopt``
    Step E on 2026-05-20, over two weeks before that project's managed
    BEGIN/END block was first scaffolded on 2026-06-07 — so the line sits
    outside the block not because a human wrote it, but because the marker
    convention did not exist yet on that project. A retraction scoped to
    "inside the block only" can never reach it, and the directory silently
    stays ignored forever (iterate-2026-08-08-track-decision-drops's own fix
    never actually landed on that live repo).

    The fixture carries a REAL, well-formed BEGIN/END block after the stale
    line (unlike the no-block-yet test below) — this is what drives
    ``_strip_superseded``'s ``len(begins) == 1 and len(ends) == 1`` branch
    and its ``i <= end_idx`` boundary, not the separate no-markers-at-all
    branch (code-reviewer, 2026-08-16: the prior markerless fixture here was
    a near-duplicate of the no-block-yet test and never exercised this
    branch at all)."""
    gi = tmp_path / ".gitignore"
    managed = [r for r in read_canonical_rules(TEMPLATE) if r not in _NARROW_DECISION_DROPS_REPLACEMENTS]
    gi.write_text(
        f"# scaffolded by /shipwright-adopt before markers existed\n"
        f"{_STALE_DECISION_DROPS_RULE}\n\n"
        + "\n".join([BEGIN_MARKER, *managed, END_MARKER])
        + "\n",
        encoding="utf-8",
    )
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    text = gi.read_text(encoding="utf-8")
    assert result["retracted"] == [_STALE_DECISION_DROPS_RULE]
    assert _STALE_DECISION_DROPS_RULE not in text.splitlines()
    assert "/.shipwright/agent_docs/decision-drops/INDEX.md" in result["added"]
    assert "/.shipwright/agent_docs/decision-drops/*.tmp" in result["added"]
    # doubt-reviewer, 2026-08-16: `added` is planner metadata, independent of
    # the write — confirm the replacements actually landed in the file too.
    for rule in read_canonical_rules(TEMPLATE):
        assert rule in text.splitlines()


def test_merge_preserves_a_superseded_match_authored_after_the_block(tmp_path: Path) -> None:
    """External review (2026-08-15, both providers, severity high): stripping
    a superseded literal ANYWHERE risks deleting a project's own deliberately
    later-added rule that happens to match one verbatim. Narrowed policy:
    only strip inside the block or ahead of it — never after, which is where
    a project's own later content lives and where nothing `gitignore_canon`
    itself ever writes."""
    gi = tmp_path / ".gitignore"
    gi.write_text(
        "\n".join([BEGIN_MARKER, *read_canonical_rules(TEMPLATE), END_MARKER])
        + f"\n\n# we deliberately still exclude this ourselves\n{_STALE_DECISION_DROPS_RULE}\n",
        encoding="utf-8",
    )
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    text = gi.read_text(encoding="utf-8")
    assert result["action"] == "unchanged"
    assert result["retracted"] == []
    assert _STALE_DECISION_DROPS_RULE in text.splitlines()


def test_merge_retracts_a_superseded_rule_with_no_managed_block_yet(tmp_path: Path) -> None:
    """A never-yet-scaffolded, pre-adopt-tooling project (no managed block at
    all) that happens to already carry a rule the template has since
    superseded: still stripped, and the fresh canonical block created in the
    same pass carries the replacements — there is no "after the block" to
    protect when there is no block."""
    gi = tmp_path / ".gitignore"
    gi.write_text(f"node_modules/\n{_STALE_DECISION_DROPS_RULE}\n", encoding="utf-8")
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    text = gi.read_text(encoding="utf-8")
    assert result["retracted"] == [_STALE_DECISION_DROPS_RULE]
    assert _STALE_DECISION_DROPS_RULE not in text.splitlines()
    assert "node_modules/" in text.splitlines()  # unrelated user content preserved
    for rule in read_canonical_rules(TEMPLATE):
        assert rule in text.splitlines()


def test_merge_falls_back_to_inside_only_scope_on_duplicate_markers(tmp_path: Path) -> None:
    """External review (2026-08-15, both providers, low severity): position-
    scoping the retraction means marker position now controls what gets
    deleted, so a malformed file (duplicate BEGIN markers here) must not
    silently widen the scope. Falls back to the pre-existing, conservative
    inside-the-first-block-only behavior rather than treating everything
    ahead of the first BEGIN as fair game."""
    gi = tmp_path / ".gitignore"
    gi.write_text(
        f"{_STALE_DECISION_DROPS_RULE}\n"
        f"{BEGIN_MARKER}\n{BEGIN_MARKER}\n{END_MARKER}\n",
        encoding="utf-8",
    )
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    text = gi.read_text(encoding="utf-8")
    assert result["retracted"] == []
    assert _STALE_DECISION_DROPS_RULE in text.splitlines()


def test_merge_preserves_a_match_inside_a_second_malformed_pair(tmp_path: Path) -> None:
    """External code review (2026-08-16, openai): the malformed-marker
    fallback must scope to ONLY the first complete BEGIN-to-following-END
    region — a stale rule sitting inside a SECOND complete pair
    (BEGIN/END/BEGIN/<rule>/END) is preserved exactly like content after a
    well-formed block, not re-scanned. Caught a real bug: the prior
    toggle-based fallback re-armed `inside` on every BEGIN it saw, so this
    second pair's content was still being retracted despite the spec's own
    claim that a malformed file never widens scope."""
    gi = tmp_path / ".gitignore"
    gi.write_text(
        f"{BEGIN_MARKER}\n{END_MARKER}\n"
        f"{BEGIN_MARKER}\n{_STALE_DECISION_DROPS_RULE}\n{END_MARKER}\n",
        encoding="utf-8",
    )
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    text = gi.read_text(encoding="utf-8")
    assert result["retracted"] == []
    assert _STALE_DECISION_DROPS_RULE in text.splitlines()


def test_plan_merge_returns_retracted_as_fourth_element() -> None:
    merged, changed, added, retracted = plan_merge(
        _gitignore_with_stale_blanket_rule(), template_path=TEMPLATE
    )
    assert changed is True
    assert retracted == [_STALE_DECISION_DROPS_RULE]
    assert _STALE_DECISION_DROPS_RULE not in merged.splitlines()
    assert added  # the two narrow replacements


def test_plan_merge_no_op_when_nothing_missing_or_superseded() -> None:
    canonical = read_canonical_rules(TEMPLATE)
    healthy = "\n".join([BEGIN_MARKER, *canonical, END_MARKER]) + "\n"
    merged, changed, added, retracted = plan_merge(healthy, template_path=TEMPLATE)
    assert changed is False
    assert added == []
    assert retracted == []
    assert merged == healthy
