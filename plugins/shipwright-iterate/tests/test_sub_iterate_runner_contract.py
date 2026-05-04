"""Drift-protection test for the sub-iterate-runner contract (ADR-029).

Sub-Iterate F — Runner Contract Mandates Reviews (campaign
iterate-skill-hardening).

The sub-iterate-runner agent (`agents/sub-iterate-runner.md`) is the
contract that every campaign-spawned runner reads. Sub-Iterate F patched
that contract to mandate:

  - Step 3.5: External Plan Review (medium+ mandatory; Branch A/B/C
    mirror of `references/iteration-planning.md` flow)
  - Step 3.7: Code Review Cascade (medium+ OR risk flags OR diff > 100
    LOC; mirror of `references/iteration-reviews.md` Section "External
    Code-Review Cascade")
  - Result-JSON `reviews` field with `plan` / `code` / `external_code`
    sub-keys

This test parses the contract markdown and the JSON schema and asserts
those headings + cross-references + schema keys still exist. Pattern
mirrors `test_boundary_probes_doc.py` (Sub-Iterate A).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUNNER_DOC = PLUGIN_ROOT / "agents" / "sub-iterate-runner.md"
SCHEMA_FILE = PLUGIN_ROOT / "agents" / "sub_iterate_runner_contract.schema.json"
SKILL_DOC = PLUGIN_ROOT / "skills" / "iterate" / "SKILL.md"


def _load_runner_text() -> str:
    return RUNNER_DOC.read_text(encoding="utf-8")


def _load_schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Existence + sanity
# ---------------------------------------------------------------------------


def test_runner_doc_exists():
    assert RUNNER_DOC.exists(), f"sub-iterate-runner.md missing at {RUNNER_DOC}"


def test_schema_file_exists():
    assert SCHEMA_FILE.exists(), (
        f"sub_iterate_runner_contract.schema.json missing at {SCHEMA_FILE}"
    )


def test_runner_doc_not_empty():
    assert _load_runner_text().strip(), "sub-iterate-runner.md is empty"


# ---------------------------------------------------------------------------
# Step 3.5: External Plan Review
# ---------------------------------------------------------------------------


def test_step_3_5_heading_present():
    text = _load_runner_text()
    assert "Step 3.5" in text, (
        "Step 3.5 heading missing — the runner contract must document an "
        "External Plan Review gate per ADR-029."
    )


def test_step_3_5_external_plan_review_label():
    text = _load_runner_text().lower()
    assert "external plan review" in text, (
        "Step 3.5 must be labeled 'External Plan Review' to match "
        "references/iteration-planning.md."
    )


@pytest.mark.parametrize("branch_label", ["Branch A", "Branch B", "Branch C"])
def test_step_3_5_branches_referenced(branch_label):
    text = _load_runner_text()
    assert branch_label in text, (
        f"Step 3.5 must reference {branch_label} (mirrors the "
        "available / missing_keys / user_disabled flow in "
        "references/iteration-planning.md)."
    )


def test_step_3_5_complexity_gating_documented():
    text = _load_runner_text().lower()
    # The gate is medium+ mandatory; trivial/small skip.
    assert "medium" in text, "Step 3.5 must document medium+ gating"


# ---------------------------------------------------------------------------
# Step 3.7: Code Review Cascade
# ---------------------------------------------------------------------------


def test_step_3_7_heading_present():
    text = _load_runner_text()
    assert "Step 3.7" in text, (
        "Step 3.7 heading missing — the runner contract must document a "
        "Code Review Cascade per ADR-029."
    )


def test_step_3_7_code_review_cascade_label():
    text = _load_runner_text().lower()
    assert "code review cascade" in text, (
        "Step 3.7 must be labeled 'Code Review Cascade' to match "
        "references/iteration-reviews.md."
    )


def test_step_3_7_external_review_invocation_documented():
    text = _load_runner_text()
    # Cascade must mention the external_review.py --mode code path.
    assert "external_review.py" in text, (
        "Step 3.7 must reference external_review.py invocation"
    )
    assert "--mode code" in text, (
        "Step 3.7 must specify --mode code for the cascade"
    )


def test_step_3_7_diff_threshold_documented():
    text = _load_runner_text()
    # Trigger condition: diff > 100 lines. Allow either "100 lines" or
    # "100 LOC" phrasing.
    assert "100 lines" in text or "100 LOC" in text, (
        "Step 3.7 must document the >100-line cascade trigger"
    )


# ---------------------------------------------------------------------------
# Result-JSON reviews field
# ---------------------------------------------------------------------------


def test_result_json_documents_reviews_field():
    text = _load_runner_text()
    # The runner output schema in the markdown must mention the new field.
    assert '"reviews"' in text or "`reviews`" in text, (
        "Result-JSON contract must document the new `reviews` field"
    )


@pytest.mark.parametrize(
    "subkey", ["plan", "code", "external_code"]
)
def test_result_json_documents_reviews_subkeys(subkey):
    text = _load_runner_text()
    assert subkey in text, (
        f"Result-JSON `reviews` field must document sub-key '{subkey}'"
    )


# ---------------------------------------------------------------------------
# JSON schema: reviews definition + backwards compat
# ---------------------------------------------------------------------------


def _success_props() -> dict:
    schema = _load_schema()
    return schema["$defs"]["success"]["properties"]


def test_schema_has_reviews_property():
    props = _success_props()
    assert "reviews" in props, (
        "success schema must declare a 'reviews' property per ADR-029"
    )


@pytest.mark.parametrize("subkey", ["plan", "code", "external_code"])
def test_schema_reviews_has_subkey(subkey):
    props = _success_props()
    reviews = props["reviews"]
    sub_props = reviews.get("properties", {})
    assert subkey in sub_props, (
        f"reviews schema must declare sub-property '{subkey}'"
    )


def test_schema_reviews_field_is_optional():
    """Backwards-compat: A/B/C/D/E result.json files don't have `reviews`.

    The field must NOT be in `required` for the success branch.
    """
    schema = _load_schema()
    required = schema["$defs"]["success"]["required"]
    assert "reviews" not in required, (
        "reviews must be optional to keep historical result.json files valid"
    )


def test_schema_validates_result_with_reviews_field():
    """Positive probe: a result JSON with the new field validates.

    Uses jsonschema if available; falls back to structural assertions when
    jsonschema is not installed (drift-protection still meaningful).
    """
    schema = _load_schema()
    sample = {
        "sub_iterate_id": "F",
        "status": "complete",
        "commit": "abcdef0",
        "branch": "iterate/skill-hardening-F",
        "tests_passed": 1,
        "tests_total": 1,
        "complexity": "small",
        "reviews": {
            "plan": {"status": "skipped_complexity_below_threshold"},
            "code": {"status": "skipped_diff_below_threshold"},
            "external_code": {"status": "skipped_diff_below_threshold"},
        },
    }
    try:
        import jsonschema  # type: ignore
    except ImportError:
        # Fallback: schema declares reviews and the sample's reviews keys
        # match the schema's declared sub-properties.
        props = _success_props()
        assert "reviews" in props
        for sub in ("plan", "code", "external_code"):
            assert sub in props["reviews"]["properties"]
        return
    jsonschema.validate(sample, schema)


def test_schema_validates_result_without_reviews_field():
    """Negative-compat probe: legacy result JSON (no `reviews`) still valid."""
    schema = _load_schema()
    legacy_sample = {
        "sub_iterate_id": "A",
        "status": "complete",
        "commit": "ba98745",
        "branch": "iterate/skill-hardening-A",
        "tests_passed": 5,
        "tests_total": 5,
        "complexity": "small",
    }
    try:
        import jsonschema  # type: ignore
    except ImportError:
        # Fallback: confirm reviews is not required.
        required = schema["$defs"]["success"]["required"]
        assert "reviews" not in required
        return
    jsonschema.validate(legacy_sample, schema)


# ---------------------------------------------------------------------------
# SKILL.md Section 5b cross-reference
# ---------------------------------------------------------------------------


def test_skill_section_5b_references_review_steps():
    """The autonomous-loop briefing in Section 5b must mention the review steps.

    Loose match: any of the new step labels appearing in the section is
    enough. The section spans from "## 5b" to the next "## " heading.
    """
    text = SKILL_DOC.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    end = len(lines)
    for idx, line in enumerate(lines):
        if line.startswith("## 5b"):
            start = idx
            continue
        if start is not None and line.startswith("## ") and not line.startswith("## 5b"):
            end = idx
            break
    assert start is not None, "Section 5b not found in SKILL.md"
    section = "\n".join(lines[start:end]).lower()
    expected_phrases = [
        "step 3.5",
        "step 3.7",
        "external plan review",
        "code review cascade",
        "review steps",
    ]
    matches = [p for p in expected_phrases if p in section]
    assert matches, (
        "Section 5b must reference at least one review-step phrase from "
        f"{expected_phrases}; section text was:\n{section[:500]}"
    )
