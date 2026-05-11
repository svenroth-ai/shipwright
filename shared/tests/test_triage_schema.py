"""JSONL schema-validation tests for the triage inbox.

AC-8: required fields, enum values, camelCase keys on the wire format.
Tests verify that produced JSONL conforms to the documented schema and
that the in-memory dict returned by `read_all_items` matches the wire
format.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import (  # noqa: E402
    KINDS,
    SCHEMA_VERSION,
    SEVERITIES,
    STATUSES,
    TRIAGE_FILE,
    append_triage_item,
    read_all_items,
)


REQUIRED_APPEND_KEYS = {
    "event",
    "id",
    "ts",
    "originalTs",
    "source",
    "severity",
    "kind",
    "title",
    "detail",
    "status",
    "suggestedPriority",
    "suggestedDomain",
}

OPTIONAL_APPEND_KEYS = {"evidencePath", "runId", "commit"}

REQUIRED_STATUS_KEYS = {"event", "id", "ts", "newStatus", "by"}
OPTIONAL_STATUS_KEYS = {"reason", "promotedTaskId"}


ID_PATTERN = re.compile(r"^trg-[0-9a-f]{8}$")
ISO_Z_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Bare project root with no .shipwright dir — exercises bootstrap."""
    return tmp_path


def _read_raw_lines(project_root: Path) -> list[dict]:
    path = project_root / ".shipwright" / TRIAGE_FILE
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- header / file bootstrap ---------------------------------------------

def test_first_append_bootstraps_file_with_header(project: Path) -> None:
    """HIGH-3: append auto-creates triage.jsonl with header on missing file."""
    item_id = append_triage_item(
        project,
        source="phaseQuality",
        severity="high",
        kind="bug",
        title="t",
        detail="d",
    )

    lines = _read_raw_lines(project)
    assert len(lines) == 2  # header + append event
    header, append_event = lines

    assert header == {
        "v": SCHEMA_VERSION,
        "schema": "triage",
        "created": header["created"],  # presence-only; format checked below
    }
    assert ISO_Z_PATTERN.match(header["created"])

    assert append_event["event"] == "append"
    assert append_event["id"] == item_id


def test_camelcase_wire_format(project: Path) -> None:
    """The on-disk JSONL keys are camelCase (matches webui ExternalTask)."""
    append_triage_item(
        project,
        source="compliance",
        severity="medium",
        kind="compliance",
        title="t",
        detail="d",
        evidence_path="path/to/evidence.txt",
        run_id="iterate-foo",
        commit="abc123",
    )

    [_header, evt] = _read_raw_lines(project)

    # snake_case must NOT appear in wire format
    snake_keys = {k for k in evt if "_" in k}
    assert snake_keys == set(), f"unexpected snake_case keys: {snake_keys}"

    # Required camelCase keys present
    assert "evidencePath" in evt
    assert "runId" in evt
    assert "suggestedPriority" in evt
    assert "suggestedDomain" in evt


def test_id_format(project: Path) -> None:
    item_id = append_triage_item(
        project,
        source="phaseQuality",
        severity="high",
        kind="bug",
        title="t",
        detail="d",
    )
    assert ID_PATTERN.match(item_id), f"id {item_id!r} doesn't match trg-<8hex>"


def test_ts_format_iso8601_with_z(project: Path) -> None:
    append_triage_item(
        project,
        source="phaseQuality",
        severity="high",
        kind="bug",
        title="t",
        detail="d",
    )
    [_header, evt] = _read_raw_lines(project)
    assert ISO_Z_PATTERN.match(evt["ts"]), f"ts={evt['ts']!r} not ISO-8601 with Z"
    assert ISO_Z_PATTERN.match(evt["originalTs"])


# --- required keys on append event ---------------------------------------

def test_append_event_has_required_keys(project: Path) -> None:
    append_triage_item(
        project,
        source="phaseQuality",
        severity="high",
        kind="bug",
        title="t",
        detail="d",
    )
    [_, evt] = _read_raw_lines(project)
    missing = REQUIRED_APPEND_KEYS - set(evt)
    assert not missing, f"missing required append keys: {missing}"
    extra = set(evt) - REQUIRED_APPEND_KEYS - OPTIONAL_APPEND_KEYS
    assert not extra, f"unexpected append keys: {extra}"


# --- enum validation -----------------------------------------------------

@pytest.mark.parametrize("severity", list(SEVERITIES))
def test_all_severities_accepted(project: Path, severity: str) -> None:
    append_triage_item(
        project,
        source="phaseQuality",
        severity=severity,
        kind="bug",
        title="t",
        detail="d",
    )


def test_invalid_severity_rejected(project: Path) -> None:
    with pytest.raises(ValueError, match="severity"):
        append_triage_item(
            project,
            source="phaseQuality",
            severity="catastrophic",
            kind="bug",
            title="t",
            detail="d",
        )


@pytest.mark.parametrize("kind", list(KINDS))
def test_all_kinds_accepted(project: Path, kind: str) -> None:
    append_triage_item(
        project,
        source="phaseQuality",
        severity="medium",
        kind=kind,
        title="t",
        detail="d",
    )


def test_invalid_kind_rejected(project: Path) -> None:
    with pytest.raises(ValueError, match="kind"):
        append_triage_item(
            project,
            source="phaseQuality",
            severity="medium",
            kind="not-a-real-kind",
            title="t",
            detail="d",
        )


@pytest.mark.parametrize("status", list(STATUSES))
def test_all_statuses_accepted_by_mark_status(project: Path, status: str) -> None:
    from triage import mark_status

    item_id = append_triage_item(
        project,
        source="phaseQuality",
        severity="medium",
        kind="bug",
        title="t",
        detail="d",
    )
    if status == "triage":
        # Initial status — already there; calling mark_status to triage is a
        # no-op event we don't forbid (idempotency).
        mark_status(project, item_id, new_status=status, by="test")
    else:
        mark_status(project, item_id, new_status=status, by="test")
    resolved = {item["id"]: item for item in read_all_items(project)}
    assert resolved[item_id]["status"] == status


def test_invalid_status_rejected_by_mark_status(project: Path) -> None:
    from triage import mark_status

    item_id = append_triage_item(
        project,
        source="phaseQuality",
        severity="medium",
        kind="bug",
        title="t",
        detail="d",
    )
    with pytest.raises(ValueError, match="status"):
        mark_status(project, item_id, new_status="closed", by="test")
