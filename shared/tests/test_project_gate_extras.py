"""Tests for ``shared/scripts/tools/verifiers/_project_gate_extras.py`` — the
four pure /shipwright-project Step-8 gates closing FR-01.02 #4/#15, #5, #10
and #11 (req3-06-enforcement-mono, sub-iterate e2-checks-project-elicitation).
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
# criteria_free_of_implementation_detail — #5
# --------------------------------------------------------------------------- #


@pytest.mark.covers("FR-01.02/AC08")
def test_criteria_free_of_implementation_detail_passes_on_clean_criteria():
    text = (
        _HEADER + _row("FR-01.01", "interview") + "\n"
        "### FR-01.01\n"
        "- (E) Given a signed-in customer, when they request an export, "
        "then a file download begins within five seconds.\n"
    )
    result = ext.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is True


def test_criteria_free_of_implementation_detail_fails_on_a_file_path():
    text = (
        _HEADER + _row("FR-01.01", "interview") + "\n"
        "### FR-01.01\n"
        "- (E) Given the handler in export_service.py, when it runs, "
        "then a file is written.\n"
    )
    result = ext.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is False
    assert "FR-01.01" in result.detail
    assert "file-path" in result.detail


def test_criteria_free_of_implementation_detail_fails_on_an_adr_reference():
    text = (
        _HEADER + _row("FR-01.01", "interview") + "\n"
        "### FR-01.01\n"
        "- (E) Given ADR-042 was accepted, when export runs, then it uses "
        "the chosen queue.\n"
    )
    result = ext.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is False
    assert "adr-number" in result.detail


@pytest.mark.covers("FR-01.02/AC08")
def test_criteria_free_of_implementation_detail_fails_on_a_code_symbol():
    text = (
        _HEADER + _row("FR-01.01", "interview") + "\n"
        "### FR-01.01\n"
        "- (E) Given export_widget_batch runs, when it completes, then a "
        "receipt is written.\n"
    )
    result = ext.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is False
    assert "code-symbol" in result.detail


def test_criteria_free_of_implementation_detail_passes_when_no_criteria_anchored():
    """A row with no ``### FR-xx.yy`` criteria block at all yields no
    criteria to score — this check is not I6 (does an FR have criteria)."""
    text = _HEADER + _row("FR-01.01", "interview")
    result = ext.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is True


def test_criteria_free_of_implementation_detail_reads_the_real_bold_anchor_shape():
    """Round-trip probe (ADR-024): ``spec-generation.md``'s ACTUAL template
    anchors criteria with ``**FR-XX.YY: Name**`` + ``- [ ]`` checkboxes, not
    the ``### FR-xx.yy`` + ``- (E)`` shape every other fixture in this file
    uses — both are supported by ``fr_criteria``'s own regexes, but only this
    test pins the format the real producer emits, with a real ``Area`` column
    too."""
    text = (
        "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | Auth | Password reset | Must | Let a user reset a "
        "forgotten password. | interview | unit |\n\n"
        "### Acceptance Criteria\n\n"
        "**FR-01.01: Password reset**\n"
        "- [ ] Given a user requests a reset, when they submit a valid "
        "email, then a reset link is sent.\n"
        "- [ ] Given the handler in reset_service.py runs, when it "
        "completes, then a token record is written.\n"
    )
    result = ext.criteria_free_of_implementation_detail({"spec.md": text})
    assert result.ok is False
    assert "FR-01.01" in result.detail
    assert "file-path" in result.detail


# --------------------------------------------------------------------------- #
# no_empty_split — #10
# --------------------------------------------------------------------------- #


@pytest.mark.covers("FR-01.02/AC13")
def test_no_empty_split_passes_when_every_spec_has_a_row():
    texts = {
        "01-a/spec.md": _HEADER + _row("FR-01.01", "interview"),
        "02-b/spec.md": _HEADER + _row("FR-02.01", "code"),
    }
    result = ext.no_empty_split(texts)
    assert result.ok is True


@pytest.mark.covers("FR-01.02/AC13")
def test_no_empty_split_fails_when_one_split_has_no_active_fr_row():
    texts = {
        "01-a/spec.md": _HEADER + _row("FR-01.01", "interview"),
        "02-b/spec.md": "# spec\n\nNothing here yet.\n",
    }
    result = ext.no_empty_split(texts)
    assert result.ok is False
    assert "02-b/spec.md" in result.detail
    assert "01-a/spec.md" not in result.detail


def test_no_empty_split_treats_a_removed_only_row_as_empty():
    text = (
        "## Removed Requirements\n\n" + _HEADER + _row("FR-01.01", "interview")
    )
    result = ext.no_empty_split({"01-a/spec.md": text})
    assert result.ok is False


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
