"""Unit tests for shared/scripts/lib/adr_headers.py.

Moved verbatim out of test_drift_parsers.py in campaign S2 alongside the
ADR-header cluster itself, so the tests keep living next to the code they
cover. No assertion changed -- only the import path.
"""

from __future__ import annotations

from lib.adr_headers import (
    ADRHeader,
    extract_adr_id_number,
    find_duplicate_adr_ids,
    find_gaps_in_adr_ids,
    parse_adr_headers,
)


def test_parse_adr_headers_handles_compact_format():
    md = (
        "# Decision Log\n\n"
        "### ADR-001: First decision\n"
        "- **Status:** accepted\n\n"
        "### ADR-002: Second decision\n"
        "- **Status:** superseded\n"
        "- **Supersedes:** ADR-001\n"
    )
    headers = parse_adr_headers(md)
    assert len(headers) == 2
    assert headers[0].id == "ADR-001"
    assert headers[0].status == "accepted"
    assert headers[1].supersedes == ("ADR-001",)


def test_parse_adr_headers_handles_old_format():
    md = "## ADR-042 | 2026-04-13 | foo | Commit abcd1234\n### Status: accepted\n"
    headers = parse_adr_headers(md)
    assert len(headers) == 1
    assert headers[0].id == "ADR-042"


def test_extract_adr_id_number_parses_and_rejects():
    assert extract_adr_id_number("ADR-027") == 27
    assert extract_adr_id_number("ADR-") is None
    assert extract_adr_id_number("not an id") is None


def test_find_duplicate_adr_ids_detects_repeats():
    headers = [
        ADRHeader("ADR-001", "a", 1),
        ADRHeader("ADR-002", "b", 2),
        ADRHeader("ADR-001", "a-dup", 3),
    ]
    assert find_duplicate_adr_ids(headers) == ["ADR-001"]


def test_find_gaps_in_adr_ids_detects_missing():
    headers = [
        ADRHeader("ADR-023", "a", 1),
        ADRHeader("ADR-025", "b", 2),
        ADRHeader("ADR-027", "c", 3),
    ]
    assert find_gaps_in_adr_ids(headers) == [24, 26]


def test_find_gaps_in_adr_ids_no_gaps():
    headers = [ADRHeader("ADR-001", "a", 1), ADRHeader("ADR-002", "b", 2)]
    assert find_gaps_in_adr_ids(headers) == []
