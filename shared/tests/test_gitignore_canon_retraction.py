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


def test_read_superseded_rules_includes_decision_drops_retraction() -> None:
    assert _STALE_DECISION_DROPS_RULE in read_superseded_rules(TEMPLATE)
    # It must NOT also be canonical — narrowed, not merely duplicated.
    assert _STALE_DECISION_DROPS_RULE not in read_canonical_rules(TEMPLATE)


def _gitignore_with_stale_blanket_rule() -> str:
    """A managed block as an already-adopted project (pre-2026-08-08) would
    still carry it: every current canonical rule EXCEPT the two narrow
    decision-drops ones, PLUS the old blanket rule they replaced."""
    canonical = read_canonical_rules(TEMPLATE)
    narrow = {
        "/.shipwright/agent_docs/decision-drops/INDEX.md",
        "/.shipwright/agent_docs/decision-drops/*.tmp",
    }
    stale_lines = [r for r in canonical if r not in narrow] + [_STALE_DECISION_DROPS_RULE]
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


def test_merge_does_not_retract_a_rule_outside_the_managed_block(tmp_path: Path) -> None:
    """A hand-written rule outside the managed block that happens to match a
    superseded literal is a user's own line, not something gitignore_canon
    added — must be left alone even though it's byte-identical."""
    gi = tmp_path / ".gitignore"
    gi.write_text(
        f"# my own rule, not managed\n{_STALE_DECISION_DROPS_RULE}\n", encoding="utf-8"
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
