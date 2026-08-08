"""JSONL schema-validation for the `amend` branch (AC6).

Split into its own file rather than added to `test_triage_schema.py`, which
is bloat-baselined at its exact current size with zero headroom.
iterate-2026-08-08-triage-amend-event.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import amend_triage_item, append_triage_item, TRIAGE_FILE  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "shared" / "schemas" / "triage_item.schema.json"


@pytest.fixture(scope="module")
def triage_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(event: dict, schema: dict) -> list[str]:
    import jsonschema

    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return [e.message for e in validator.iter_errors(event)]


def _last_line(project: Path) -> dict:
    lines = (project / ".shipwright" / TRIAGE_FILE).read_text(encoding="utf-8").splitlines()
    return json.loads(lines[-1])


def test_amend_event_matches_schema(tmp_path: Path, triage_schema: dict) -> None:
    item_id = append_triage_item(
        tmp_path, source="manual", severity="low", kind="bug", title="t", detail="d",
    )
    amend_triage_item(tmp_path, item_id, by="sven", title="new", severity="high")
    errors = _validate(_last_line(tmp_path), triage_schema)
    assert not errors, f"amend event failed schema: {errors}"


def test_single_field_amend_matches_schema(tmp_path: Path, triage_schema: dict) -> None:
    item_id = append_triage_item(
        tmp_path, source="manual", severity="low", kind="bug", title="t", detail="d",
    )
    amend_triage_item(tmp_path, item_id, by="sven", detail="only detail changed")
    errors = _validate(_last_line(tmp_path), triage_schema)
    assert not errors, f"amend event failed schema: {errors}"


def test_contentless_amend_fails_schema(triage_schema: dict) -> None:
    """The writer already refuses this (`ValueError`) — the schema's `anyOf`
    is the wire-level half of the same rule, exercised directly here since a
    contentless event can never reach disk through the writer."""
    event = {"event": "amend", "id": "trg-00000000", "ts": "2026-08-08T00:00:00Z", "by": "cli"}
    errors = _validate(event, triage_schema)
    assert errors, "a contentless amend must fail the anyOf constraint"


def test_amend_with_unknown_key_fails_schema(triage_schema: dict) -> None:
    event = {
        "event": "amend", "id": "trg-00000000", "ts": "2026-08-08T00:00:00Z",
        "by": "cli", "title": "x", "source": "manual",
    }
    errors = _validate(event, triage_schema)
    assert errors, "additionalProperties:false must reject a non-amendable key"


def test_amend_with_bad_severity_fails_schema(triage_schema: dict) -> None:
    event = {
        "event": "amend", "id": "trg-00000000", "ts": "2026-08-08T00:00:00Z",
        "by": "cli", "severity": "urgent",
    }
    errors = _validate(event, triage_schema)
    assert errors


def test_amend_with_whitespace_only_title_fails_schema(triage_schema: dict) -> None:
    """Stage-2 code review finding 6: `minLength: 1` alone accepts a
    whitespace-only title, which the Python reader then rejects WHOLE — the
    `pattern: \\S` addition closes that gap at the wire-contract level, for
    any writer (not only this iterate's Python one)."""
    event = {
        "event": "amend", "id": "trg-00000000", "ts": "2026-08-08T00:00:00Z",
        "by": "cli", "title": "   ",
    }
    errors = _validate(event, triage_schema)
    assert errors, "a whitespace-only amend title must fail the pattern constraint"


def test_append_with_whitespace_only_title_fails_schema(triage_schema: dict) -> None:
    """Same `pattern: \\S` tightening applied to the append branch's `title`
    for consistency (Stage-2 code review finding 6) — homed here rather than
    `test_triage_schema.py`, which is bloat-baselined with zero headroom."""
    event = {
        "event": "append", "id": "trg-00000000", "ts": "2026-08-08T00:00:00Z",
        "originalTs": "2026-08-08T00:00:00Z", "source": "manual",
        "severity": "low", "kind": "bug", "title": "   ", "detail": "d",
        "status": "triage", "suggestedPriority": "P3", "suggestedDomain": "engineering",
    }
    errors = _validate(event, triage_schema)
    assert errors, "a whitespace-only append title must fail the pattern constraint"
