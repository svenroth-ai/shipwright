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

from triage import (  # noqa: E402
    DETAIL_MAX_LEN,
    amend_triage_item,
    append_triage_item,
    append_triage_item_idempotent,
    TRIAGE_FILE,
)

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


# iterate-2026-08-13-triage-detail-maxlength — `detail` maxLength (both
# branches share the DETAIL_MAX_LEN cap; homed here for the same
# zero-headroom reason as the two tests above).

def test_schema_detail_cap_matches_python_constant(triage_schema: dict) -> None:
    """Stage-2 code review finding 2: the cap is declared independently in
    the wire schema (both branches) and in `lib.triage_fields.DETAIL_MAX_LEN`
    — drift-guard so raising one without the other cannot go unnoticed."""
    append_cap = triage_schema["$defs"]["append"]["properties"]["detail"]["maxLength"]
    amend_cap = triage_schema["$defs"]["amend"]["properties"]["detail"]["maxLength"]
    assert append_cap == DETAIL_MAX_LEN
    assert amend_cap == DETAIL_MAX_LEN


def test_schema_rejects_oversized_append_detail(triage_schema: dict) -> None:
    event = {
        "event": "append", "id": "trg-00000000", "ts": "2026-08-08T00:00:00Z",
        "originalTs": "2026-08-08T00:00:00Z", "source": "manual",
        "severity": "low", "kind": "bug", "title": "t", "detail": "d" * (DETAIL_MAX_LEN + 1),
        "status": "triage", "suggestedPriority": "P3", "suggestedDomain": "engineering",
    }
    errors = _validate(event, triage_schema)
    assert errors, "an over-cap append detail must fail the maxLength constraint"


def test_schema_rejects_oversized_amend_detail(triage_schema: dict) -> None:
    event = {
        "event": "amend", "id": "trg-00000000", "ts": "2026-08-08T00:00:00Z",
        "by": "cli", "detail": "d" * (DETAIL_MAX_LEN + 1),
    }
    errors = _validate(event, triage_schema)
    assert errors, "an over-cap amend detail must fail the maxLength constraint"


def test_append_rejects_oversized_detail(tmp_path: Path) -> None:
    """A pathologically long finding from any producer must fail fast at
    append time, not silently write a record that later fails to promote
    (shipwright-webui's DESCRIPTION_MAX_LENGTH)."""
    with pytest.raises(ValueError, match=f"detail exceeds {DETAIL_MAX_LEN} characters"):
        append_triage_item(
            tmp_path, source="manual", severity="low", kind="bug",
            title="t", detail="d" * (DETAIL_MAX_LEN + 1),
        )


def test_append_rejects_non_string_detail(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="detail must be a string"):
        append_triage_item(
            tmp_path, source="manual", severity="low", kind="bug", title="t", detail=42,
        )


def test_append_accepts_detail_at_cap(tmp_path: Path, triage_schema: dict) -> None:
    append_triage_item(
        tmp_path, source="manual", severity="low", kind="bug",
        title="t", detail="d" * DETAIL_MAX_LEN,
    )
    errors = _validate(_last_line(tmp_path), triage_schema)
    assert not errors, f"a detail at exactly the cap must pass schema: {errors}"


def test_amend_rejects_oversized_detail(tmp_path: Path) -> None:
    """The amend path must enforce the same cap as append — otherwise a
    short-detail item can be pushed back over the cap post-promotion via a
    CLI correction, defeating the append-side guard entirely."""
    item_id = append_triage_item(
        tmp_path, source="manual", severity="low", kind="bug", title="t", detail="d",
    )
    with pytest.raises(ValueError, match=f"detail exceeds {DETAIL_MAX_LEN} characters"):
        amend_triage_item(tmp_path, item_id, by="cli", detail="d" * (DETAIL_MAX_LEN + 1))


def test_append_idempotent_rejects_oversized_detail(tmp_path: Path) -> None:
    """`append_triage_item_idempotent` builds its own wire event and must not
    bypass the cap `append_triage_item` enforces."""
    with pytest.raises(ValueError, match=f"detail exceeds {DETAIL_MAX_LEN} characters"):
        append_triage_item_idempotent(
            tmp_path, source="manual", severity="low", kind="bug",
            title="t", detail="d" * (DETAIL_MAX_LEN + 1), dedup_key="dk-1",
        )
