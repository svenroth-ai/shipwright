"""Tests for shared/scripts/lib/review_findings.py — normalizing what each
reviewer emits into one finding shape.

Covers the four adapters (AC1), both observed external-prose layouts and the
no-fabrication rule (AC5), empty native payloads (AC11), and Markdown-wrapped
JSON hand-over (AC1, external plan review G1/O1).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_findings import (  # noqa: E402
    PARSE_STRUCTURED,
    PARSE_UNSTRUCTURED,
    ReviewFindingsError,
    extract_json_payload,
    from_code_reviewer,
    from_doubt_reviewer,
    from_external_prose,
    from_self_review,
)


# --- code-reviewer (AC1, AC11) ----------------------------------------------


def test_from_code_reviewer_maps_its_native_shape():
    findings = from_code_reviewer({
        "section": "auth",
        "review": [{
            "severity": "high",
            "category": "correctness",
            "file": "src/auth/login.ts",
            "line": 42,
            "finding": "Token expiry not checked before use",
            "suggestion": "Add isTokenExpired() check",
        }],
    })
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"
    assert findings[0]["category"] == "correctness"
    assert findings[0]["file"] == "src/auth/login.ts"
    assert findings[0]["line"] == 42
    assert findings[0]["finding"].startswith("Token expiry")
    assert findings[0]["source"] == "code-reviewer"


def test_from_code_reviewer_accepts_a_clean_review():
    assert from_code_reviewer({"section": "auth", "review": []}) == []


def test_from_code_reviewer_tolerates_missing_optional_fields():
    findings = from_code_reviewer({"review": [{"finding": "something is off"}]})
    assert findings[0]["severity"] is None
    assert findings[0]["file"] is None
    assert findings[0]["line"] is None
    assert findings[0]["suggestion"] is None


def test_from_code_reviewer_refuses_an_item_with_no_finding_text():
    """Originally this asserted the item was silently DROPPED. The Stage-3 doubt
    pass showed that made a malformed payload indistinguishable from an honest
    clean review, so the contract changed: refuse it. See
    test_element_level_loss_is_refused_not_recorded_as_clean."""
    with pytest.raises(ReviewFindingsError):
        from_code_reviewer({"review": [{"severity": "high"}]})


def test_from_code_reviewer_rejects_a_non_object_payload():
    with pytest.raises(ReviewFindingsError):
        from_code_reviewer([1, 2, 3])


# --- doubt-reviewer (AC1, AC11) ---------------------------------------------


def test_from_doubt_reviewer_maps_lens_and_disproof():
    findings = from_doubt_reviewer({
        "stage": "doubt",
        "doubts": [{
            "severity": "high",
            "lens": "reversibility",
            "claim_under_doubt": "the migration is safe to ship",
            "disproof_attempt": "0003_drop_legacy.sql drops a column with no down.sql",
            "file": "supabase/migrations/0003_drop_legacy.sql",
            "what_would_resolve_it": "add down.sql recreating the column",
        }],
    })
    assert len(findings) == 1
    assert findings[0]["category"] == "reversibility"
    assert "the migration is safe to ship" in findings[0]["finding"]
    assert "no down.sql" in findings[0]["finding"]
    assert findings[0]["suggestion"] == "add down.sql recreating the column"
    assert findings[0]["source"] == "doubt-reviewer"


def test_from_doubt_reviewer_accepts_an_honest_empty_pass():
    assert from_doubt_reviewer({"stage": "doubt", "doubts": []}) == []


# --- self-review (AC1, AC11) ------------------------------------------------


def test_from_self_review_records_only_the_failures():
    findings = from_self_review({"items": [
        {"name": "Spec Compliance", "verdict": "pass", "note": "all ACs covered"},
        {"name": "Error Handling", "verdict": "fail", "note": "no guard on the read path"},
        {"name": "Affected Boundaries", "verdict": "n/a", "note": "none touched"},
    ]})
    assert len(findings) == 1
    assert findings[0]["category"] == "Error Handling"
    assert findings[0]["finding"] == "no guard on the read path"
    assert findings[0]["source"] == "self-review"


def test_from_self_review_leaves_severity_null_rather_than_inventing_one():
    """The checklist reports pass/fail, not severity. Manufacturing one would
    fabricate review data — the exact failure this artifact exists to prevent."""
    findings = from_self_review({"items": [
        {"name": "Test Quality", "verdict": "fail", "note": "no error-path test"},
    ]})
    assert findings[0]["severity"] is None


def test_from_self_review_accepts_an_all_passing_checklist():
    assert from_self_review({"items": [
        {"name": "Spec Compliance", "verdict": "pass", "note": "ok"},
    ]}) == []


def test_from_self_review_falls_back_to_the_item_name_when_the_note_is_empty():
    findings = from_self_review({"items": [{"name": "Security Basics", "verdict": "fail"}]})
    assert len(findings) == 1
    assert "Security Basics" in findings[0]["finding"]


# --- external prose (AC5) ---------------------------------------------------

PROSE_DASH = """\
- Category: bug
- Severity: high
- File: shared/scripts/triage.py:325
- Finding: append_triage_item_idempotent() checks for duplicates before taking the lock.
- Suggestion: Move the dedup scan and the append into one critical section.

- Category: spec
- Severity: medium
- File: shared/scripts/hooks/audit.py:226
- Finding: The producer emits every non-tier-2 FAIL into triage.
- Suggestion: Filter to the allowed codes before appending.
"""

PROSE_BOLD = """\
### Findings

- **Category:** Approach / Dependency
- **Severity:** High
- **Finding:** There is a data pipeline gap between the agents and the CLI tool.
- **Suggestion:** Make the parser extract JSON blocks from Markdown directly.

- **Category:** Risk
- **Severity:** Medium
- **Finding:** The hard gate will fail in-flight runs.
- **Suggestion:** Add a one-command escape hatch.
"""

PROSE_NUMBERED_COMBINED = """\
1. **Category: approach - Severity: high**
   **Finding:** The plan assumes a native JSON payload is always available.
   **Suggestion:** Identify the concrete call site for each pass.

2. **Category: risk - Severity: medium**
   **Finding:** Two separately persisted files are not transactional.
   **Suggestion:** Define a deterministic write order.
"""


@pytest.mark.parametrize("prose", [PROSE_DASH, PROSE_BOLD, PROSE_NUMBERED_COMBINED])
def test_external_prose_splits_into_one_finding_per_item(prose):
    findings, parse_status = from_external_prose(prose)
    assert parse_status == PARSE_STRUCTURED
    assert len(findings) == 2
    assert all(f["finding"].strip() for f in findings)
    assert all(f["source"] == "external-review" for f in findings)


def test_external_prose_extracts_severity_in_any_casing():
    findings, _ = from_external_prose(PROSE_BOLD)
    assert [f["severity"] for f in findings] == ["high", "medium"]


def test_external_prose_extracts_severity_from_a_combined_header():
    findings, _ = from_external_prose(PROSE_NUMBERED_COMBINED)
    assert [f["severity"] for f in findings] == ["high", "medium"]
    assert findings[0]["category"] == "approach"


def test_external_prose_splits_file_and_line():
    findings, _ = from_external_prose(PROSE_DASH)
    assert findings[0]["file"] == "shared/scripts/triage.py"
    assert findings[0]["line"] == 325


def test_a_clean_external_review_yields_zero_findings_not_one_fabricated_one():
    """A reviewer that found nothing must never be rendered as having found
    something. This was a real defect in the original plan (external review O4)."""
    findings, parse_status = from_external_prose(
        "I reviewed the diff against the spec and found no defects. Ship as is."
    )
    assert findings == []
    assert parse_status == PARSE_UNSTRUCTURED


def test_unparseable_prose_is_flagged_rather_than_silently_called_clean():
    findings, parse_status = from_external_prose("::: garbled ::: 12345 :::")
    assert findings == []
    assert parse_status == PARSE_UNSTRUCTURED


def test_empty_prose_is_unstructured_not_a_crash():
    findings, parse_status = from_external_prose("")
    assert findings == []
    assert parse_status == PARSE_UNSTRUCTURED


def test_external_prose_severity_is_null_when_absent():
    findings, parse_status = from_external_prose(
        "- Category: bug\n- Finding: the retry budget is off by one\n"
    )
    assert parse_status == PARSE_STRUCTURED
    assert findings[0]["severity"] is None


# --- regressions from the code-review round ---------------------------------

PROSE_NO_CATEGORY = """\
- **Finding:** The lock is released before the companion write.
- **Suggestion:** Hold one lock across both artifacts.

- **Finding:** A clean review is rendered as one fabricated item.
- **Suggestion:** Return an empty list with an unstructured marker.
"""

PROSE_WITH_TRAILING_PROSE = """\
- Category: bug
- Severity: high
- Finding: the retry budget is off by one
- Suggestion: start the counter at zero

### Overall Assessment
This is a pragmatic approach and is ready to implement once the above is fixed.
"""


def test_a_category_less_layout_still_splits_into_findings():
    """Blocks used to open only on a Category key, so a payload without one lost
    every finding while still reporting a structured parse."""
    findings, parse_status = from_external_prose(PROSE_NO_CATEGORY)
    assert parse_status == PARSE_STRUCTURED
    assert len(findings) == 2
    assert "lock is released" in findings[0]["finding"]
    assert "fabricated" in findings[1]["finding"]


def test_trailing_prose_is_not_glued_onto_the_last_finding():
    """The last value used to run to end-of-text, absorbing the reviewer's
    closing summary into the final suggestion."""
    findings, _ = from_external_prose(PROSE_WITH_TRAILING_PROSE)
    assert len(findings) == 1
    assert "Overall Assessment" not in (findings[0]["suggestion"] or "")
    assert "ready to implement" not in (findings[0]["suggestion"] or "")
    assert findings[0]["suggestion"] == "start the counter at zero"


@pytest.mark.parametrize("value,expected", [
    ("high", "high"),
    ("High", "high"),
    ("**Medium**", "medium"),
    ("medium - would be high if the lock were shared", "medium"),
    ("not high", None),
    ("critical", None),
    ("", None),
])
def test_severity_is_read_from_the_leading_token_not_scanned_for(value, expected):
    """A substring scan turned 'not high' into 'high'. Overstating a severity
    the reviewer never gave is fabrication."""
    findings, _ = from_external_prose(
        f"- Category: bug\n- Severity: {value}\n- Finding: something is wrong\n"
    )
    assert findings[0]["severity"] == expected


@pytest.mark.parametrize("payload,key", [
    ({}, "review"),
    ({"section": "x"}, "review"),
    ({"stage": "doubt"}, "doubts"),
    ({"items": None}, "items"),
])
def test_a_missing_result_array_is_malformed_not_a_clean_review(payload, key):
    """`{}` used to read as 'zero findings' and could close a review row as
    clean on the strength of a truncated reply. Only an explicit [] is clean."""
    adapter = {"review": from_code_reviewer, "doubts": from_doubt_reviewer,
               "items": from_self_review}[key]
    with pytest.raises(ReviewFindingsError):
        adapter(payload)


def test_an_oversized_native_payload_is_rejected_not_truncated():
    """Silently keeping the first 200 would record a partial review as complete."""
    payload = {"review": [{"finding": f"defect {i}"} for i in range(201)]}
    with pytest.raises(ReviewFindingsError):
        from_code_reviewer(payload)


def test_a_long_finding_is_marked_when_shortened():
    findings = from_code_reviewer({"review": [{"finding": "y" * 5000}]})
    assert findings[0]["finding"].endswith("[…truncated]")
    assert len(findings[0]["finding"]) == 4000


# --- regressions from the Stage-3 doubt pass --------------------------------

#: The exact rendering gemini produced in this change's own code review. The
#: reviewer prompt mandates the `File:line` label, so this is the format the
#: system asks for — not an exotic input.
PROSE_FILE_LINE_LABEL = """\
**Category:** Spec Compliance / Bug
**Severity:** High
**File:line:** `shared/scripts/tools/record_review_pass.py:157`
**Finding:** The marker write happens after the file lock is released.
**Suggestion:** Move the lock acquisition out to the CLI level.
"""


def test_the_mandated_file_line_label_yields_a_usable_path():
    """`**File:line:**` used to match at `File:`, leaving the value as
    "line: `path:157`" — the number was peeled off correctly and the path was
    stored as "line: `path`". Observed verbatim in this run's first artifact."""
    findings, parse_status = from_external_prose(PROSE_FILE_LINE_LABEL)
    assert parse_status == PARSE_STRUCTURED
    assert findings[0]["file"] == "shared/scripts/tools/record_review_pass.py"
    assert findings[0]["line"] == 157
    assert findings[0]["severity"] == "high"


@pytest.mark.parametrize("payload,adapter_key", [
    ({"review": [{"severity": "high", "issue": "token never expires"}]}, "review"),
    ({"review": [{"finding": "real"}, {"severity": "low", "note": "x"}]}, "review"),
    ({"doubts": [{"severity": "high", "lens": "reversibility"}]}, "doubts"),
    ({"items": [{"name": "Test Quality", "verdict": "fail"}, {"verdict": "fail"}]}, "items"),
])
def test_element_level_loss_is_refused_not_recorded_as_clean(payload, adapter_key):
    """A field-name slip (`issue` where the contract says `finding`) used to
    record as 'ran, found nothing' — byte-identical to an honest clean review,
    and the likeliest malformation when the producer is an LLM."""
    adapter = {"review": from_code_reviewer, "doubts": from_doubt_reviewer,
               "items": from_self_review}[adapter_key]
    with pytest.raises(ReviewFindingsError):
        adapter(payload)


def test_a_well_formed_payload_still_passes_the_element_loss_guard():
    assert len(from_code_reviewer({"review": [
        {"finding": "one"}, {"finding": "two"},
    ]})) == 2
    assert from_self_review({"items": [
        {"name": "Spec Compliance", "verdict": "pass"},
        {"name": "Test Quality", "verdict": "n/a"},
    ]}) == []


# --- Markdown-wrapped JSON hand-over (AC1) ----------------------------------


def test_extract_json_payload_reads_a_fenced_block_from_markdown():
    payload = extract_json_payload(
        'Here is my review.\n\n```json\n{"review": [{"finding": "x"}]}\n```\n\nDone.'
    )
    assert payload == {"review": [{"finding": "x"}]}


def test_extract_json_payload_reads_a_bare_json_document():
    assert extract_json_payload('{"review": []}') == {"review": []}


def test_extract_json_payload_reads_an_unlabelled_fence():
    assert extract_json_payload('```\n{"doubts": []}\n```') == {"doubts": []}


def test_extract_json_payload_prefers_the_labelled_fence_over_stray_braces():
    payload = extract_json_payload(
        'Consider {not json} first.\n```json\n{"review": []}\n```'
    )
    assert payload == {"review": []}


def test_extract_json_payload_raises_when_there_is_no_json():
    with pytest.raises(ReviewFindingsError):
        extract_json_payload("no payload here at all")
