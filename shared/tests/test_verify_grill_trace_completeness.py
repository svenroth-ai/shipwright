"""Tests for shared/scripts/tools/verify_grill_trace_completeness.py — the
per-check unit coverage for all four closed-vocabulary STOP conditions from
the design plus the ``grill_trace_coverage`` guard. End-to-end
``run_all_checks`` coverage and the honesty-guard acceptance criterion live
in ``test_verify_grill_trace_completeness_integration.py`` (split at the
300-LOC guideline).
"""

from __future__ import annotations

import pytest

from tools.grill_trace_format import GrillTrace, parse_trace
from tools.verify_grill_trace_completeness import (
    check_blank_dimension,
    check_glossary_delta_declared,
    check_grill_trace_coverage,
    check_greenfield_assumed,
    check_outcome_fit_criterion,
    check_undefined_term,
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


# ---------------------------------------------------------------------------
# STOP 1 — blank dimension
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.16/AC01")
def test_blank_dimension_passes_when_all_seven_are_answered_or_assumed_or_na():
    trace = parse_trace(_payload())
    assert check_blank_dimension(trace).ok is True


@pytest.mark.covers("FR-01.16/AC01", "FR-01.02/AC07")
def test_blank_dimension_fails_on_a_missing_key():
    """A missing dimensions key is now rejected earlier, at parse_trace() /
    write time (grill_trace_format._validate_dimensions — external code
    review, P4.2) — this test constructs the GrillTrace dataclass directly,
    bypassing that write-time validation, to prove check_blank_dimension()
    still independently catches a missing key on a record that somehow
    reached it anyway (e.g. a legacy file written before that guard existed)."""
    payload = _payload()
    dimensions = dict(payload["dimensions"])
    del dimensions["rationale"]
    trace = GrillTrace(
        requirement_key=payload["requirement_key"],
        requirement_text=payload["requirement_text"],
        surface=payload["surface"],
        evidence=tuple(payload["evidence"]),
        dimensions=dimensions,
        fit_criterion=payload["fit_criterion"],
        glossary_delta=tuple(payload["glossary_delta"]),
        confirmed_by=payload["confirmed_by"],
        terms_used=tuple(payload["terms_used"]),
    )
    result = check_blank_dimension(trace)
    assert result.ok is False
    assert "rationale" in result.detail


def test_blank_dimension_fails_on_a_value_outside_the_closed_vocabulary():
    payload = _payload()
    payload["dimensions"]["boundaries"] = "maybe"
    trace = parse_trace(payload)
    result = check_blank_dimension(trace)
    assert result.ok is False
    assert "boundaries" in result.detail


def test_blank_dimension_fails_when_assumed_reason_is_blank():
    payload = _payload()
    payload["dimensions"]["rationale"] = "assumed:   "
    trace = parse_trace(payload)
    assert check_blank_dimension(trace).ok is False


# ---------------------------------------------------------------------------
# STOP 2 — greenfield 'assumed'
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.16/AC07")
def test_greenfield_assumed_fails_on_any_assumed_in_project_surface():
    payload = _payload()
    payload["dimensions"]["rationale"] = "assumed:nobody has decided yet, ask PO"
    trace = parse_trace(payload)
    result = check_greenfield_assumed(trace)
    assert result.ok is False
    assert "rationale" in result.detail


@pytest.mark.covers("FR-01.16/AC07")
def test_greenfield_assumed_permits_n_a_in_project_surface():
    trace = parse_trace(_payload())  # rationale is n/a, not assumed
    assert check_greenfield_assumed(trace).ok is True


def test_greenfield_assumed_fails_a_non_project_surface_trace_as_a_data_integrity_error():
    """Changed from a skip to a FAIL (external code review, P4.2 finding
    OpenAI-C): this gate is wired only into /shipwright-project's Step 8,
    so a trace claiming surface != "project" under a project's planning
    tree is a data-integrity fault, never a legitimate exemption from the
    no-'assumed' rule — trusting the payload-declared field to skip the
    rule was exactly the bypass the finding identified."""
    payload = _payload(surface="adopt")
    payload["dimensions"]["rationale"] = "assumed:code predates every current maintainer"
    trace = parse_trace(payload)
    result = check_greenfield_assumed(trace)
    assert result.ok is False
    assert "adopt" in result.detail


# ---------------------------------------------------------------------------
# STOP 3 — undefined term
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.02/AC10")
def test_undefined_term_fails_when_a_declared_term_is_in_neither_source():
    trace = parse_trace(_payload(terms_used=["Widget"]))
    result = check_undefined_term(trace, known_terms=set())
    assert result.ok is False
    assert "Widget" in result.detail


def test_undefined_term_passes_when_every_declared_term_is_known():
    trace = parse_trace(_payload(terms_used=["Order"]))
    result = check_undefined_term(trace, known_terms={"Order"})
    assert result.ok is True


def test_undefined_term_matching_is_exact_case_no_folding():
    """Same contract as context_md_format.read_terms(): 'order' != 'Order'."""
    trace = parse_trace(_payload(terms_used=["order"]))
    result = check_undefined_term(trace, known_terms={"Order"})
    assert result.ok is False


# collect_known_terms / parse_glossary_terms now live in grill_trace_glossary.py
# (external code review split, P4.2) — their tests moved to
# shared/tests/test_grill_trace_glossary.py.


# ---------------------------------------------------------------------------
# STOP 4 — outcome without a fit criterion
# ---------------------------------------------------------------------------

def test_outcome_fit_criterion_fails_when_outcome_answered_with_no_fit_criterion():
    trace = parse_trace(_payload(fit_criterion=None))
    result = check_outcome_fit_criterion(trace)
    assert result.ok is False


def test_outcome_fit_criterion_passes_when_outcome_answered_with_a_fit_criterion():
    trace = parse_trace(_payload())
    assert check_outcome_fit_criterion(trace).ok is True


def test_outcome_fit_criterion_rule_does_not_apply_when_outcome_not_answered():
    payload = _payload(fit_criterion=None)
    payload["dimensions"]["outcome"] = "n/a:not applicable to this requirement"
    trace = parse_trace(payload)
    assert check_outcome_fit_criterion(trace).ok is True


# ---------------------------------------------------------------------------
# Coverage guard (not one of the four, own name)
# ---------------------------------------------------------------------------

def test_coverage_skips_when_no_interview_transcript_yet(tmp_path):
    result = check_grill_trace_coverage(tmp_path, traces=[])
    assert result.is_skipped


def test_coverage_fails_when_transcript_exists_but_no_traces_were_written(tmp_path):
    (tmp_path / "shipwright_project_interview.md").write_text("transcript", encoding="utf-8")
    result = check_grill_trace_coverage(tmp_path, traces=[])
    assert result.ok is False


def test_coverage_passes_when_at_least_one_trace_exists(tmp_path):
    trace = parse_trace(_payload())
    result = check_grill_trace_coverage(tmp_path, traces=[trace])
    assert result.ok is True


# ---------------------------------------------------------------------------
# glossary_delta_declared (not one of the four, own name)
# ---------------------------------------------------------------------------

def test_glossary_delta_declared_passes_when_every_delta_term_is_in_terms_used():
    trace = parse_trace(_payload(
        terms_used=["Order"],
        glossary_delta=[{"term": "Order", "recorded_in": "CONTEXT.md"}],
    ))
    assert check_glossary_delta_declared(trace).ok is True


@pytest.mark.covers("FR-01.02/AC10")
def test_glossary_delta_declared_fails_when_a_delta_term_is_missing_from_terms_used():
    trace = parse_trace(_payload(
        terms_used=[],
        glossary_delta=[{"term": "Order", "recorded_in": "CONTEXT.md"}],
    ))
    result = check_glossary_delta_declared(trace)
    assert result.ok is False
    assert "Order" in result.detail


