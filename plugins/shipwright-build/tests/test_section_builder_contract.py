"""Contract tests for section-builder subagent result format.

Validates the JSON schema against the documented output format in
agents/section-builder.md and verifies that example payloads conform.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
SCHEMA_PATH = AGENTS_DIR / "section_builder_contract.schema.json"
AGENT_MD_PATH = AGENTS_DIR / "section-builder.md"


@pytest.fixture
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def agent_md():
    return AGENT_MD_PATH.read_text(encoding="utf-8")


def _extract_json_blocks(md_text: str) -> list[dict]:
    """Extract all ```json blocks from markdown."""
    pattern = r"```json\s*\n(.*?)\n```"
    blocks = re.findall(pattern, md_text, re.DOTALL)
    results = []
    for block in blocks:
        cleaned = re.sub(r"//.*$", "", block, flags=re.MULTILINE)
        try:
            results.append(json.loads(cleaned))
        except json.JSONDecodeError:
            pass
    return results


def _validate(instance: dict, schema: dict) -> list[str]:
    """Validate instance against schema, return list of errors."""
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
        return [e.message for e in validator.iter_errors(instance)]
    except ImportError:
        return _validate_manual(instance, schema)


def _validate_manual(instance: dict, schema: dict) -> list[str]:
    """Manual validation without jsonschema package."""
    errors = []

    if "oneOf" in schema:
        defs = schema.get("$defs", {})
        matched = False
        for ref_obj in schema["oneOf"]:
            ref = ref_obj["$ref"].split("/")[-1]
            sub_schema = defs[ref]
            sub_errors = _validate_manual(instance, sub_schema)
            if not sub_errors:
                matched = True
                break
        if not matched:
            errors.append("Does not match any oneOf variant")
        return errors

    if "required" in schema:
        for field in schema["required"]:
            if field not in instance:
                errors.append(f"Missing required field: {field}")

    if "properties" in schema:
        for key, prop_schema in schema["properties"].items():
            if key not in instance:
                continue
            val = instance[key]
            if "const" in prop_schema and val != prop_schema["const"]:
                errors.append(f"{key}: expected const {prop_schema['const']!r}, got {val!r}")
            if "type" in prop_schema:
                expected = prop_schema["type"]
                if isinstance(expected, list):
                    type_ok = any(_check_type(val, t) for t in expected)
                else:
                    type_ok = _check_type(val, expected)
                if not type_ok:
                    errors.append(f"{key}: wrong type, expected {expected}, got {type(val).__name__}")
            if "minimum" in prop_schema and isinstance(val, (int, float)):
                if val < prop_schema["minimum"]:
                    errors.append(f"{key}: value {val} < minimum {prop_schema['minimum']}")

    if schema.get("additionalProperties") is False and "properties" in schema:
        extra = set(instance.keys()) - set(schema["properties"].keys())
        if extra:
            errors.append(f"Unexpected properties: {extra}")

    return errors


def _check_type(val, expected_type: str) -> bool:
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    expected = type_map.get(expected_type)
    if expected is None:
        return True
    if expected_type == "integer" and isinstance(val, bool):
        return False
    return isinstance(val, expected)


class TestSchemaExists:
    def test_schema_file_exists(self):
        assert SCHEMA_PATH.exists(), f"Schema not found at {SCHEMA_PATH}"

    def test_schema_is_valid_json(self, schema):
        assert "$schema" in schema
        assert "oneOf" in schema

    def test_agent_md_exists(self):
        assert AGENT_MD_PATH.exists()


class TestSchemaMatchesAgent:
    """Verify schema fields match what section-builder.md documents."""

    def test_success_required_fields(self, schema):
        success = schema["$defs"]["success"]
        required = set(success["required"])
        expected = {"section", "status", "commit", "branch", "tests_passed", "tests_total"}
        assert required == expected

    def test_failure_required_fields(self, schema):
        failure = schema["$defs"]["failure"]
        required = set(failure["required"])
        expected = {"section", "status", "error"}
        assert required == expected

    def test_success_has_all_documented_fields(self, schema, agent_md):
        success_props = set(schema["$defs"]["success"]["properties"].keys())
        documented_fields = {
            "section", "status", "commit", "branch",
            "tests_passed", "tests_total",
            "review_findings", "design_fidelity",
            "design_groups", "design_screens_checked", "decisions",
        }
        for field in documented_fields:
            assert field in success_props, f"Documented field {field!r} missing from schema"

    def test_failure_has_all_documented_fields(self, schema):
        failure_props = set(schema["$defs"]["failure"]["properties"].keys())
        documented_fields = {"section", "status", "error", "partial_commit",
                             "tests_passed", "tests_total", "debug_log"}
        for field in documented_fields:
            assert field in failure_props, f"Documented field {field!r} missing from schema"


class TestSuccessPayloads:
    """Verify valid success payloads pass schema validation."""

    def test_minimal_success(self, schema):
        payload = {
            "section": "01-auth",
            "status": "complete",
            "commit": "abc123def456",
            "branch": "build/myapp-20260411",
            "tests_passed": 12,
            "tests_total": 12,
        }
        errors = _validate(payload, schema)
        assert not errors, f"Validation errors: {errors}"

    def test_full_success(self, schema):
        payload = {
            "section": "01-auth",
            "status": "complete",
            "commit": "abc123def4567890abc123def4567890abc12345",
            "branch": "build/myapp-20260411-120000",
            "tests_passed": 15,
            "tests_total": 15,
            "integration_passed": 5,
            "integration_total": 5,
            "pgtap_passed": 3,
            "pgtap_total": 3,
            "review_findings": [
                {"finding": "Missing null check in handler", "status": "fixed"},
                {"finding": "Consider index on user_id", "status": "deferred"},
            ],
            "design_fidelity": "full",
            "design_groups": [
                {"group": "Layout structure", "status": "fixed",
                 "screens": ["01-login.html"], "attempts": 1},
            ],
            "design_screens_checked": ["01-login.html", "02-register.html"],
            "decisions": [
                {"title": "Use JWT for auth", "rationale": "Stateless, scalable"},
            ],
            "manual_steps_pending": False,
        }
        errors = _validate(payload, schema)
        assert not errors, f"Validation errors: {errors}"


class TestFailurePayloads:
    def test_minimal_failure(self, schema):
        payload = {
            "section": "01-auth",
            "status": "failed",
            "error": "Migration apply failed",
        }
        errors = _validate(payload, schema)
        assert not errors, f"Validation errors: {errors}"

    def test_full_failure(self, schema):
        payload = {
            "section": "01-auth",
            "status": "failed",
            "error": "Tests failing after 3 retries",
            "partial_commit": "abc1234",
            "tests_passed": 5,
            "tests_total": 12,
            "debug_log": [
                {"attempt": 1, "root_cause": "Missing env var", "result": "fail"},
                {"attempt": 2, "root_cause": "Wrong import path", "result": "fail"},
                {"attempt": 3, "root_cause": "Schema mismatch", "result": "fail"},
            ],
        }
        errors = _validate(payload, schema)
        assert not errors, f"Validation errors: {errors}"


class TestInvalidPayloads:
    def test_missing_section(self, schema):
        payload = {
            "status": "complete",
            "commit": "abc123",
            "branch": "build/x",
            "tests_passed": 1,
            "tests_total": 1,
        }
        errors = _validate(payload, schema)
        assert errors

    def test_wrong_status_value(self, schema):
        payload = {
            "section": "01-auth",
            "status": "partial",
            "commit": "abc123",
            "branch": "build/x",
            "tests_passed": 1,
            "tests_total": 1,
        }
        errors = _validate(payload, schema)
        assert errors

    def test_tests_passed_negative(self, schema):
        payload = {
            "section": "01-auth",
            "status": "complete",
            "commit": "abc123",
            "branch": "build/x",
            "tests_passed": -1,
            "tests_total": 1,
        }
        errors = _validate(payload, schema)
        assert errors


class TestAgentMdJsonExamples:
    """Extract JSON examples from section-builder.md and validate them."""

    def test_documented_examples_are_valid(self, schema, agent_md):
        blocks = _extract_json_blocks(agent_md)
        result_blocks = [b for b in blocks if "section" in b and "status" in b]
        assert len(result_blocks) >= 2, (
            f"Expected at least 2 result JSON examples in agent md, found {len(result_blocks)}"
        )
        for i, block in enumerate(result_blocks):
            errors = _validate(block, schema)
            assert not errors, (
                f"JSON example {i + 1} in section-builder.md fails validation: {errors}"
            )
