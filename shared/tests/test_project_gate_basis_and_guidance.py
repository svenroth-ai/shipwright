"""Tests for the FR-01.02 basis/criteria/starting-guidance gates in
``shared/scripts/tools/verifiers/_project_gate_wiring.py``.

Split out of ``test_verifiers_project.py`` (shared bloat gate, 300-line
limit; req3-06-enforcement-mono sub-iterate e2) — this file covers
``check_basis_forbids_assumed``, ``check_criteria_free_of_implementation_detail``
and ``check_starting_guidance_present``. ``check_no_empty_split`` and
``_is_safe_split_name`` live in ``test_project_gate_no_empty_split.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.verifiers._project_gate_wiring import (  # noqa: E402
    check_basis_forbids_assumed,
    check_criteria_free_of_implementation_detail,
    check_starting_guidance_present,
)

from _project_check_fixtures import _write_splits_config  # noqa: E402


def test_check_basis_forbids_assumed_skips_when_no_spec_yet(tmp_path):
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is True
    assert r.is_skipped


def test_check_basis_forbids_assumed_fails_on_a_bare_assumed_cell_with_no_criteria(tmp_path):
    """Revised post-merge (Stage-1 spec-review REJECT, PR #729): a bare
    ``assumed`` cell is only a hit when the row carries NO acceptance
    criterion at all — ``assumed`` with nothing to settle it is exactly
    the silent-assuming the docs ban, per ``fr-authoring.md`` §4a."""
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | assumed |\n",
        encoding="utf-8",
    )
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is False
    assert "FR-01.01" in r.detail


def test_check_basis_forbids_assumed_passes_on_a_bare_assumed_cell_paired_with_a_criterion(tmp_path):
    """Revised post-merge (Stage-1 spec-review REJECT, PR #729): the
    original round shipped an outright ban on Basis='assumed', stricter
    than FR-01.02 #4's own recorded ceiling and contradicting
    ``fr-authoring.md``/``requirement-elicitation.md``/``spec-generation.md``,
    all of which keep greenfield ``assumed`` legal when paired with a
    named settlement. A recorded acceptance criterion on the row is the
    mechanical form obligation the docs actually state — this gate
    cannot and does not judge whether the criterion truly names a
    settlement (no deterministic 'aboutness' oracle exists), only that
    one is present."""
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | assumed |\n\n"
        "### FR-01.01\n"
        "- (E) Given the PO confirms the export scope, when the spec is "
        "revised, then this row's Basis is updated to interview.\n",
        encoding="utf-8",
    )
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is True


def test_check_basis_forbids_assumed_fails_loud_on_a_declared_but_missing_spec(tmp_path):
    """External code review (round 2, low): only ``no_empty_split`` had a
    missing/unreadable-spec wiring test; the other two gates sharing
    ``_read_spec_texts`` need the same proof they don't silently pass."""
    _write_splits_config(tmp_path, ["01-a"])
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is False
    assert "unreadable/missing" in r.detail
    assert "01-a" in r.detail


def test_check_basis_forbids_assumed_fires_on_extension_scope_too(tmp_path):
    """Required Tier-3 PR review (PR #729): round 5 skipped this WHOLE gate
    for extension scope, reasoning both #4 and #15 were greenfield-only —
    but the merged function no longer enforces #4's original ban (reverted
    for being stricter than the ledger's ceiling), only #15's un-scoped
    form obligation. An extension ``/shipwright-project`` run still runs an
    interview (a PO is present), so #15 is reachable there too, unlike
    ``/shipwright-adopt`` — a bare ``assumed`` row with no criterion must
    still fail, not be silently skipped."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({
            "scope": "extension",
            "splits": [{"name": "01-a", "status": "not_started"}],
        }),
        encoding="utf-8",
    )
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | assumed |\n",
        encoding="utf-8",
    )
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is False
    assert "FR-01.01" in r.detail


def test_check_basis_forbids_assumed_fails_loud_on_non_object_config(tmp_path):
    """External code review (round 5, medium, openai): syntactically valid
    but non-object JSON (a bare list) must not crash ``.get('scope')``."""
    (tmp_path / "shipwright_project_config.json").write_text("[]", encoding="utf-8")
    r = check_basis_forbids_assumed(tmp_path)  # must not raise
    assert r.ok is False
    assert "not a JSON object" in r.detail


def test_check_basis_forbids_assumed_catches_a_qualified_assumed_cell(tmp_path):
    """External code review (round 3, low, GLM): ``fr_basis.classify``
    returns ``kind='malformed'`` (not ``known``/``assumed``) for
    ``assumed: <reason>`` — a naive known/assumed check misses it, which
    is exactly the qualifier-smuggling loophole the "no exceptions"
    wording on #4/#15 exists to close."""
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | "
        "assumed: nobody could answer |\n",
        encoding="utf-8",
    )
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is False
    assert "FR-01.01" in r.detail


def test_check_basis_forbids_assumed_fails_on_a_qualified_cell_even_with_a_criterion(tmp_path):
    """Revised post-merge (Stage-1 spec-review REJECT, PR #729): the
    bare-``assumed``-with-a-criterion carve-out does NOT extend to a
    qualified cell — ``fr-authoring.md`` §4a is explicit that the Basis
    cell takes one bare vocabulary value; a settlement belongs in an
    acceptance criterion, never smuggled into the Basis cell itself, so
    a qualified cell stays banned regardless of what criteria the row
    also carries."""
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | "
        "assumed: nobody could answer |\n\n"
        "### FR-01.01\n"
        "- (E) Given the PO confirms the export scope, when the spec is "
        "revised, then this row's Basis is updated to interview.\n",
        encoding="utf-8",
    )
    r = check_basis_forbids_assumed(tmp_path)
    assert r.ok is False
    assert "FR-01.01" in r.detail


def test_check_criteria_free_of_implementation_detail_fails_on_a_symbol(tmp_path):
    _write_splits_config(tmp_path, ["01-a"])
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "| ID | Name | Priority | Description | Basis |\n|---|---|---|---|---|\n"
        "| FR-01.01 | widget export | Must | export widgets | interview |\n\n"
        "### FR-01.01\n"
        "- (E) Given write_export_batch runs, when it completes, then a "
        "receipt is written.\n",
        encoding="utf-8",
    )
    r = check_criteria_free_of_implementation_detail(tmp_path)
    assert r.ok is False
    assert "FR-01.01" in r.detail


def test_check_criteria_free_of_implementation_detail_skips_when_no_spec_yet(tmp_path):
    """Stage-2 code review (round 3, PR #729, low): the docstring on
    ``test_check_basis_forbids_assumed_fails_loud_on_a_declared_but_missing_spec``
    claimed the OTHER two gates sharing ``_read_spec_texts`` needed the same
    proof they don't silently pass — only ``basis_forbids_assumed`` actually
    got it. This closes the gap for ``criteria_free_of_implementation_detail``."""
    r = check_criteria_free_of_implementation_detail(tmp_path)
    assert r.ok is True
    assert r.is_skipped


def test_check_criteria_free_of_implementation_detail_fails_loud_on_a_declared_but_missing_spec(tmp_path):
    """Stage-2 code review (round 3, PR #729, low): companion to the above —
    a declared split whose spec.md was never written must fail loud, not
    read as "no criteria to check" (vacuous pass)."""
    _write_splits_config(tmp_path, ["01-a"])
    r = check_criteria_free_of_implementation_detail(tmp_path)
    assert r.ok is False
    assert "unreadable/missing" in r.detail
    assert "01-a" in r.detail


def test_check_starting_guidance_present_skips_extension_scope(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"scope": "extension"}), encoding="utf-8",
    )
    r = check_starting_guidance_present(tmp_path)
    assert r.ok is True
    assert r.is_skipped


def test_check_starting_guidance_present_fails_on_missing_files_full_app(tmp_path):
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8",
    )
    r = check_starting_guidance_present(tmp_path)
    assert r.ok is False
    assert "missing" in r.detail


def test_check_starting_guidance_present_fails_loud_on_non_object_config(tmp_path):
    """External code review (round 5, medium, openai): ``null`` is valid
    JSON but has no ``.get`` — must not crash."""
    (tmp_path / "shipwright_project_config.json").write_text("null", encoding="utf-8")
    r = check_starting_guidance_present(tmp_path)  # must not raise
    assert r.ok is False
    assert "not a JSON object" in r.detail


def test_check_starting_guidance_present_fails_loud_on_malformed_config(tmp_path):
    """External code review (round 4, low, GLM): a corrupt project config
    used to fall through to scope=None, which then silently ENFORCED the
    full-application guidance check instead of reporting the config as
    unverifiable — the one gate in this module that broke the
    fail-loud-on-unparseable-manifest pattern the other three follow."""
    (tmp_path / "shipwright_project_config.json").write_text(
        "{not valid json", encoding="utf-8",
    )
    r = check_starting_guidance_present(tmp_path)
    assert r.ok is False
    assert "could not be parsed" in r.detail
