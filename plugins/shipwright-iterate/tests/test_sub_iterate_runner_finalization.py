"""Drift-protection for the sub-iterate-runner FINALIZATION contract.

Companion to ``test_sub_iterate_runner_contract.py`` (which is grandfathered at
its bloat baseline). Split out (iterate-2026-07-20-runner-finalization-integrity)
so the finalization additions do not ratchet the sibling file.

Covers:
- the runner routes F3 through ``write_decision_drop.py`` (NOT
  ``write_decision_log.py``) and carries F5c (``append_iterate_entry.py``) as a
  mandatory step — the two gaps that silently lost the ADR + iterate-entry in
  campaign 2026-07-18-mission-artifacts;
- the result-JSON schema admits the optional ``finalization`` record so a runner
  emitting it validates under ``additionalProperties: false``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUNNER_DOC = PLUGIN_ROOT / "agents" / "sub-iterate-runner.md"
SCHEMA_FILE = PLUGIN_ROOT / "agents" / "sub_iterate_runner_contract.schema.json"


def _load_runner_text() -> str:
    return RUNNER_DOC.read_text(encoding="utf-8")


def _load_schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))


def _success_props() -> dict:
    return _load_schema()["$defs"]["success"]["properties"]


@pytest.mark.covers("FR-01.11")
def test_runner_doc_documents_f3_drop_and_f5c():
    """The finalization contract must route F3 through the decision-DROP writer
    (NOT write_decision_log.py) and carry F5c as a mandatory step."""
    text = _load_runner_text()
    assert "write_decision_drop.py" in text, "F3 must use write_decision_drop.py"
    assert "append_iterate_entry.py" in text, "F5c (append_iterate_entry.py) must be documented"
    assert "check_iterate_no_direct_decision_log" in text, (
        "the contract must name the F11 gate that forbids a direct decision_log.md write"
    )
    assert "F5c" in text, "F5c must be an explicit finalization step"


@pytest.mark.covers("FR-01.11")
def test_schema_has_finalization_property():
    """The success schema declares a `finalization` property so a runner that
    emits the F3/F5c/self-verify record validates (schema is
    additionalProperties: false)."""
    props = _success_props()
    assert "finalization" in props, (
        "success schema must declare a 'finalization' property so the runner's "
        "F3/F5c/self-verify record is not rejected by additionalProperties:false"
    )
    sub = props["finalization"].get("properties", {})
    for key in ("f3_decision_drop", "f5c_iterate_entry", "verifier"):
        assert key in sub, f"finalization schema must declare sub-property '{key}'"


@pytest.mark.covers("FR-01.11")
def test_schema_finalization_field_is_optional():
    """Backwards-compat: historical result.json files carry no `finalization`."""
    schema = _load_schema()
    required = schema["$defs"]["success"]["required"]
    assert "finalization" not in required, (
        "finalization must be optional to keep historical result.json files valid"
    )


@pytest.mark.covers("FR-01.11")
def test_schema_validates_result_with_finalization_field():
    """Positive probe: a result JSON carrying the finalization block validates."""
    schema = _load_schema()
    sample = {
        "sub_iterate_id": "X",
        "status": "complete",
        "commit": "abcdef0",
        "branch": "iterate/x",
        "tests_passed": 3,
        "tests_total": 3,
        "complexity": "small",
        "finalization": {
            "f3_decision_drop": "written",
            "f5c_iterate_entry": "written",
            "verifier": {"status": "green", "exit_code": 0},
        },
    }
    try:
        import jsonschema  # type: ignore
    except ImportError:
        assert "finalization" in _success_props()
        return
    jsonschema.validate(sample, schema)
