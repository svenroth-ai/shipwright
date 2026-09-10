"""Tests for shared/scripts/tools/verify_grill_trace_completeness.py — the
per-check unit coverage for all four closed-vocabulary STOP conditions from
the design plus the ``grill_trace_coverage`` guard. End-to-end
``run_all_checks`` coverage and the honesty-guard acceptance criterion live
in ``test_verify_grill_trace_completeness_integration.py`` (split at the
300-LOC guideline).
"""

from __future__ import annotations

from tools.grill_trace_format import parse_trace
from tools.verify_grill_trace_completeness import (
    check_blank_dimension,
    check_grill_trace_coverage,
    check_greenfield_assumed,
    check_outcome_fit_criterion,
    check_undefined_term,
    collect_known_terms,
    parse_glossary_terms,
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

def test_blank_dimension_passes_when_all_seven_are_answered_or_assumed_or_na():
    trace = parse_trace(_payload())
    assert check_blank_dimension(trace).ok is True


def test_blank_dimension_fails_on_a_missing_key():
    payload = _payload()
    del payload["dimensions"]["rationale"]
    trace = parse_trace(payload)
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

def test_greenfield_assumed_fails_on_any_assumed_in_project_surface():
    payload = _payload()
    payload["dimensions"]["rationale"] = "assumed:nobody has decided yet, ask PO"
    trace = parse_trace(payload)
    result = check_greenfield_assumed(trace)
    assert result.ok is False
    assert "rationale" in result.detail


def test_greenfield_assumed_permits_n_a_in_project_surface():
    trace = parse_trace(_payload())  # rationale is n/a, not assumed
    assert check_greenfield_assumed(trace).ok is True


def test_greenfield_assumed_rule_does_not_apply_outside_project_surface():
    payload = _payload(surface="adopt")
    payload["dimensions"]["rationale"] = "assumed:code predates every current maintainer"
    trace = parse_trace(payload)
    result = check_greenfield_assumed(trace)
    assert result.is_skipped


# ---------------------------------------------------------------------------
# STOP 3 — undefined term
# ---------------------------------------------------------------------------

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


def test_collect_known_terms_reads_glossary_bullets_and_context_language(tmp_path):
    glossary = tmp_path / "glossary.md"
    glossary.write_text(
        "# Glossary\n\n## Core mechanics\n\n"
        "- **Allowlist** — the bloat baseline file.\n"
        "- **Ratchet** — measured LOC exceeds the frozen value.\n",
        encoding="utf-8",
    )
    context = tmp_path / "CONTEXT.md"
    context.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme sells widgets.\n\n"
        "## Language\n\n**Order** — a confirmed purchase.\n",
        encoding="utf-8",
    )

    terms = collect_known_terms(glossary, context)

    assert terms == {"Allowlist", "Ratchet", "Order"}


def test_parse_glossary_terms_ignores_a_missing_file(tmp_path):
    assert parse_glossary_terms(tmp_path / "does-not-exist.md") == set()


def test_parse_glossary_terms_dedupes_a_repeated_mid_sentence_bold_phrase(tmp_path):
    """A bold phrase referenced again mid-sentence elsewhere in the glossary's
    own prose (not a new bullet entry) must not produce a second, distinct
    term — the set naturally dedupes, and no false term is introduced."""
    content = (
        "## Section\n\n"
        "- **Real Term** — a bullet-anchored entry, referencing "
        "a **Real Term** again mid-line.\n"
    )
    path = tmp_path / "glossary.md"
    path.write_text(content, encoding="utf-8")

    assert parse_glossary_terms(path) == {"Real Term"}


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


