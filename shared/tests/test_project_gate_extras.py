"""Tests for ``shared/scripts/tools/verifiers/_project_gate_extras.py`` — the
two pure /shipwright-project Step-8 gates closing FR-01.02 #4/#15 and #11
(req3-06-enforcement-mono, sub-iterate e2-checks-project-elicitation).

#5 (``criteria_free_of_implementation_detail``) and #10 (``no_empty_split``)
moved to ``test_project_gate_extras_rollout.py`` on 2026-09-12
(`trg-9583d3a8`), the moment their own module split out of this one to carry
rollout-transition grace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.verifiers import _project_gate_extras as ext

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPLIT_HEURISTICS = (
    _REPO_ROOT / "plugins" / "shipwright-project" / "skills" / "project"
    / "references" / "split-heuristics.md"
)


@pytest.mark.covers("FR-01.02/AC13")
def test_split_heuristics_still_demands_cohesive_purpose():
    """FR-01.02 #10b (req3-06-enforcement-mono, sub-iterate e2, round 3
    follow-up): ``no_empty_split`` only enforces the zero-row floor — a
    MULTI-row split's actual topical coherence ("is this genuinely one
    cohesive part?") is reading comprehension with no deterministic
    oracle, per the campaign's own abort condition. Pin that
    ``split-heuristics.md`` still demands it in prose, mirroring #8b/#3b's
    drift-test pattern for the same class of honest downgrade."""
    body = _SPLIT_HEURISTICS.read_text(encoding="utf-8")
    assert "Cohesive purpose" in body

# --------------------------------------------------------------------------- #
# basis_forbids_assumed — #4 + #15
# --------------------------------------------------------------------------- #

_HEADER = "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"


def _row(fr_id: str, basis: str, *, name: str = "widget export", desc: str = "export widgets") -> str:
    return f"| {fr_id} | {name} | Must | {desc} | {basis} |\n"


def test_basis_forbids_assumed_passes_when_no_row_reads_assumed():
    text = _HEADER + _row("FR-01.01", "interview") + _row("FR-01.02", "code")
    result = ext.basis_forbids_assumed({"spec.md": text})
    assert result.ok is True


@pytest.mark.covers("FR-01.02/AC06")
def test_basis_forbids_assumed_fails_on_a_bare_assumed_cell():
    text = _HEADER + _row("FR-01.01", "assumed")
    result = ext.basis_forbids_assumed({"01-x/spec.md": text})
    assert result.ok is False
    assert "FR-01.01" in result.detail
    assert "01-x/spec.md" in result.detail


@pytest.mark.covers("FR-01.02/AC06")
def test_basis_forbids_assumed_passes_on_a_bare_assumed_cell_with_a_criterion():
    """Revised post-merge (Stage-1 spec-review REJECT, PR #729): a bare
    ``assumed`` cell paired with a recorded acceptance criterion is legal
    per ``fr-authoring.md`` §4a — the original round's outright ban was
    stricter than FR-01.02 #4's own decided ceiling."""
    text = (
        _HEADER + _row("FR-01.01", "assumed") + "\n### FR-01.01\n"
        "- (E) Given the PO confirms scope, when the spec is revised, "
        "then this row's Basis is updated to interview.\n"
    )
    result = ext.basis_forbids_assumed({"spec.md": text})
    assert result.ok is True


def test_basis_forbids_assumed_ignores_a_positional_basis_column():
    """Only a NAMED Basis column is scored — mirrors ``fr_basis``'s own
    contract that a legacy/unnamed cell never claimed to be a basis."""
    text = (
        "| ID | Name | Priority | Description |\n|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets |\n"
    )
    result = ext.basis_forbids_assumed({"spec.md": text})
    assert result.ok is True


def test_basis_forbids_assumed_catches_a_qualified_assumed_cell():
    """Round 3 (external code review, low, GLM): ``assumed: <reason>``
    classifies as ``fr_basis`` kind ``malformed``, not ``known``/``assumed``
    — a naive equality check misses it."""
    text = _HEADER + _row("FR-01.01", "assumed: nobody could answer")
    result = ext.basis_forbids_assumed({"spec.md": text})
    assert result.ok is False
    assert "FR-01.01" in result.detail


def test_basis_forbids_assumed_ignores_an_unrelated_malformed_cell():
    """Stage-2 code review (round 3, PR #729, low): a glued out-of-vocabulary
    typo with no word boundary after "assumed" (``fr_basis`` classifies it
    under its OTHER ``malformed`` branch, "not in the vocabulary") must not
    be mislabeled "settlement smuggled into the Basis cell" by a raw
    ``.startswith("assumed")`` on the value — this gate polices the
    assumed/settlement rule, not general vocabulary validity, which is a
    different check's job."""
    text = _HEADER + _row("FR-01.01", "assumedallowed")
    result = ext.basis_forbids_assumed({"spec.md": text})
    assert result.ok is True


def test_basis_forbids_assumed_across_multiple_specs_names_every_hit():
    text_a = _HEADER + _row("FR-01.01", "assumed")
    text_b = _HEADER + _row("FR-02.01", "assumed")
    result = ext.basis_forbids_assumed({"a/spec.md": text_a, "b/spec.md": text_b})
    assert result.ok is False
    assert "FR-01.01" in result.detail
    assert "FR-02.01" in result.detail


# --------------------------------------------------------------------------- #
# starting_guidance_present — #11
# --------------------------------------------------------------------------- #


def _write_guidance(root, *, empty_one: bool = False) -> None:
    root.joinpath("CLAUDE.md").write_text("# Project guidance\n", encoding="utf-8")
    agent_docs = root / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True)
    (agent_docs / "architecture.md").write_text("" if empty_one else "# Architecture\n", encoding="utf-8")
    (agent_docs / "decision_log.md").write_text("# Decision log\n", encoding="utf-8")
    (agent_docs / "conventions.md").write_text("# Conventions\n", encoding="utf-8")


@pytest.mark.covers("FR-01.02/AC14")
def test_starting_guidance_present_passes_when_all_four_are_non_empty(tmp_path):
    _write_guidance(tmp_path)
    result = ext.starting_guidance_present(tmp_path)
    assert result.ok is True


@pytest.mark.covers("FR-01.02/AC14")
def test_starting_guidance_present_fails_when_a_file_is_missing(tmp_path):
    _write_guidance(tmp_path)
    (tmp_path / "CLAUDE.md").unlink()
    result = ext.starting_guidance_present(tmp_path)
    assert result.ok is False
    assert "missing" in result.detail
    assert "CLAUDE.md" in result.detail


def test_starting_guidance_present_fails_when_a_file_is_empty(tmp_path):
    _write_guidance(tmp_path, empty_one=True)
    result = ext.starting_guidance_present(tmp_path)
    assert result.ok is False
    assert "empty" in result.detail
    assert "architecture.md" in result.detail
