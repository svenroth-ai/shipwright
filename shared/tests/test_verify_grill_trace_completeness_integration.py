"""End-to-end ``run_all_checks`` coverage for
shared/scripts/tools/verify_grill_trace_completeness.py, plus the required
acceptance criterion — the honesty guard: a well-formed but low-quality
trace passes, because the gate checks completeness, never prose quality.
Split out of test_verify_grill_trace_completeness.py at the 300-LOC
guideline; the per-check unit tests live there.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.grill_trace_format import parse_trace
from tools.verify_grill_trace_completeness import (
    check_blank_dimension,
    check_greenfield_assumed,
    check_outcome_fit_criterion,
    check_undefined_term,
    run_all_checks,
)


def _payload(**overrides) -> dict:
    payload = {
        "requirement_key": "user-login",
        "requirement_text": "The system SHALL authenticate users via email/password.",
        "surface": "project",
        "evidence": ["turn 3: user described login as required"],
        "dimensions": {
            "outcome": "answered",
            "purpose": "answered",
            "boundaries": "answered",
            "failure": "answered",
            "glossary": "n/a:no new term introduced",
            "rationale": "n/a:not hard to reverse",
            "out_of_scope": "answered",
        },
        "fit_criterion": "a valid email/password pair returns a session token",
        "glossary_delta": [],
        "confirmed_by": "user confirmed in turn 5",
        "terms_used": [],
    }
    payload.update(overrides)
    return payload


def _write_trace(planning_dir: Path, payload: dict) -> Path:
    directory = planning_dir / "grill-traces"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{payload['requirement_key']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# End-to-end: run_all_checks against a real planning tree
# ---------------------------------------------------------------------------

def test_run_all_checks_all_green_for_a_well_formed_trace(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload())
    glossary = tmp_path / "glossary.md"
    glossary.write_text("", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir, glossary_path=glossary)

    assert all(r.ok is not False for r in results)


def test_run_all_checks_reports_the_one_failure_when_a_trace_has_a_blank_dimension(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    payload = _payload()
    del payload["dimensions"]["glossary"]
    _write_trace(planning_dir, payload)
    glossary = tmp_path / "glossary.md"
    glossary.write_text("", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir, glossary_path=glossary)

    failures = [r for r in results if r.ok is False]
    assert len(failures) == 1
    assert "blank_dimension" in failures[0].name


def test_run_all_checks_flags_coverage_gap_when_transcript_exists_with_no_traces(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    planning_dir.mkdir(parents=True)
    (planning_dir / "shipwright_project_interview.md").write_text("x", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir)

    by_name = {r.name: r for r in results}
    assert by_name["grill_trace_coverage"].ok is False
    # No spec.md anywhere yet — the FR-join check has nothing to check against.
    assert by_name["fr_trace_coverage"].is_skipped


def test_run_all_checks_flags_fr_without_a_matching_trace_even_when_others_exist(tmp_path):
    """The gap external plan review found: a PARTIALLY recorded interview
    (some requirements traced, one not) passes the plain grill_trace_coverage
    guard but must not pass the FR-join check."""
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload(requirement_key="user-login"))
    spec = planning_dir / "01-auth" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "## 2. Functional Requirements\n\n"
        "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | Auth | User login | Must | ... | interview | unit |\n"
        "| FR-01.02 | Auth | Password reset | Must | ... | interview | unit |\n",
        encoding="utf-8",
    )
    glossary = tmp_path / "glossary.md"
    glossary.write_text("", encoding="utf-8")

    results = run_all_checks(tmp_path, planning_dir=planning_dir, glossary_path=glossary)

    by_name = {r.name: r for r in results}
    assert by_name["grill_trace_coverage"].ok is True  # at least one trace exists
    assert by_name["fr_trace_coverage"].ok is False
    assert "FR-01.02" in by_name["fr_trace_coverage"].detail


# ---------------------------------------------------------------------------
# Honesty guard — required acceptance criterion: completeness only, never
# prose quality. Two separate traces (external plan review, P4.2 — the
# combined single-test version conflated "passes despite low quality" with
# "still catches a real gap", which read as internally unclear):
# ---------------------------------------------------------------------------

def test_low_quality_but_structurally_complete_trace_passes_every_check():
    """One-word evidence/confirmation, a terse assumption reason, a
    one-letter fit criterion — the gate must not judge any of that. Only
    structural shape is checked, per shared/grill-trace-format.md §3. Every
    dimension here is properly shaped (answered/assumed/n-a with a non-blank
    reason), so every check passes."""
    payload = _payload(
        evidence=["x"],
        confirmed_by="ok",
        fit_criterion="y",
        terms_used=[],
    )
    payload["dimensions"]["rationale"] = "assumed:idk"
    payload["dimensions"]["out_of_scope"] = "n/a:n"
    trace = parse_trace(payload)

    assert check_blank_dimension(trace).ok is True
    assert check_outcome_fit_criterion(trace).ok is True
    assert check_undefined_term(trace, known_terms=set()).ok is True


def test_low_quality_trace_still_catches_a_real_completeness_gap():
    """The mirror of the test above: the SAME low-quality prose style
    (terse, one-word) does not mask a genuine STOP condition. `assumed:idk`
    on the project surface is a real declined-to-ask, not a prose-quality
    defect — proving the gate discriminates on structure, not eloquence."""
    payload = _payload(evidence=["x"], confirmed_by="ok")
    payload["dimensions"]["rationale"] = "assumed:idk"
    trace = parse_trace(payload)

    assert check_greenfield_assumed(trace).ok is False
