"""Tests for shared/scripts/tools/grill_trace_format.py — the grill-trace
schema validation and the read API used by both the producer
(write_grill_trace.py) and the completeness gate
(verify_grill_trace_completeness.py). Schema: shared/grill-trace-format.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.grill_trace_format import (
    DIMENSIONS,
    GrillTraceError,
    parse_trace,
    read_trace_dir,
    trace_path,
)


def _valid_payload(**overrides) -> dict:
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


def test_parse_trace_accepts_a_well_formed_record():
    trace = parse_trace(_valid_payload())
    assert trace.requirement_key == "user-login"
    assert set(trace.dimensions) == set(DIMENSIONS)
    assert trace.fit_criterion == "a valid email/password pair returns a session token"


@pytest.mark.parametrize("key", [
    "requirement_key", "requirement_text", "surface", "confirmed_by",
])
def test_parse_trace_rejects_blank_required_string_fields(key):
    with pytest.raises(GrillTraceError):
        parse_trace(_valid_payload(**{key: "   "}))


def test_parse_trace_rejects_missing_evidence():
    with pytest.raises(GrillTraceError):
        parse_trace(_valid_payload(evidence=[]))


def test_parse_trace_rejects_unknown_dimension_key():
    payload = _valid_payload()
    payload["dimensions"]["extra_dimension"] = "answered"
    with pytest.raises(GrillTraceError):
        parse_trace(payload)


def test_parse_trace_rejects_blank_dimension_value():
    payload = _valid_payload()
    payload["dimensions"]["outcome"] = "   "
    with pytest.raises(GrillTraceError):
        parse_trace(payload)


def test_parse_trace_rejects_surface_outside_closed_vocabulary():
    with pytest.raises(GrillTraceError):
        parse_trace(_valid_payload(surface="onboarding"))


def test_parse_trace_allows_empty_terms_used_and_glossary_delta():
    trace = parse_trace(_valid_payload(terms_used=[], glossary_delta=[]))
    assert trace.terms_used == ()
    assert trace.glossary_delta == ()


def test_parse_trace_accepts_glossary_delta_entries():
    payload = _valid_payload(glossary_delta=[{"term": "Order", "recorded_in": "CONTEXT.md"}])
    trace = parse_trace(payload)
    assert trace.glossary_delta == ({"term": "Order", "recorded_in": "CONTEXT.md"},)


def test_parse_trace_rejects_malformed_glossary_delta_entry():
    payload = _valid_payload(glossary_delta=[{"term": "Order"}])
    with pytest.raises(GrillTraceError):
        parse_trace(payload)


def test_parse_trace_allows_null_fit_criterion_when_outcome_not_answered():
    payload = _valid_payload(fit_criterion=None)
    payload["dimensions"]["outcome"] = "n/a:not applicable to this requirement"
    trace = parse_trace(payload)
    assert trace.fit_criterion is None


def test_read_trace_dir_returns_empty_list_when_directory_missing(tmp_path):
    assert read_trace_dir(tmp_path / ".shipwright" / "planning") == []


def test_read_trace_dir_reads_every_json_file(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    directory = planning_dir / "grill-traces"
    directory.mkdir(parents=True)
    (directory / "a.json").write_text(json.dumps(_valid_payload(requirement_key="a")))
    (directory / "b.json").write_text(
        json.dumps(_valid_payload(requirement_key="b")), encoding="utf-8",
    )

    traces = read_trace_dir(planning_dir)

    assert {t.requirement_key for t in traces} == {"a", "b"}
    assert all(isinstance(t.source_path, Path) for t in traces)


def test_read_trace_dir_raises_on_a_malformed_file(tmp_path):
    """A broken trace must surface, never be silently skipped — it would
    otherwise look identical to 'elicitation never ran'."""
    planning_dir = tmp_path / ".shipwright" / "planning"
    directory = planning_dir / "grill-traces"
    directory.mkdir(parents=True)
    (directory / "bad.json").write_text(json.dumps({"requirement_key": "bad"}))

    with pytest.raises(GrillTraceError):
        read_trace_dir(planning_dir)


def test_trace_path_is_keyed_by_requirement_key(tmp_path):
    path = trace_path(tmp_path, "user-login")
    assert path == tmp_path / "grill-traces" / "user-login.json"
