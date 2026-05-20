"""launchPayload schema-extension tests (iterate-2026-05-20-triage-launch-surface).

Covers AC-2 (storage), AC-8 (idempotency), AC-9 (legacy producer null-safety) of
the iterate spec. Reverse-drift protection for the JSONL wire schema after the
`launch_payload` kwarg landed.

Layer 1 — schema round-trip via the storage API (both append paths × payload set/None).
Layer 2 — parametrized across all KNOWN_SOURCES so a future producer that omits
the field can never silently regress to a non-null default.
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
    KNOWN_SOURCES,
    TRIAGE_FILE,
    append_triage_item,
    append_triage_item_idempotent,
    read_all_items,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# AC-2 storage round-trip — append_triage_item
# ---------------------------------------------------------------------------

def test_append_persists_launch_payload(project: Path) -> None:
    payload = "/shipwright-security\n\nContext: code-scanning 3, dependabot 1"
    item_id = append_triage_item(
        project, source="github", severity="high", kind="bug",
        title="t", detail="d", launch_payload=payload,
    )
    [item] = read_all_items(project)
    assert item["id"] == item_id
    assert item["launchPayload"] == payload


def test_append_omitted_kwarg_persists_null(project: Path) -> None:
    item_id = append_triage_item(
        project, source="phaseQuality", severity="medium", kind="bug",
        title="t", detail="d",
    )
    [item] = read_all_items(project)
    assert item["id"] == item_id
    assert item["launchPayload"] is None


def test_append_explicit_none_persists_null(project: Path) -> None:
    append_triage_item(
        project, source="phaseQuality", severity="medium", kind="bug",
        title="t", detail="d", launch_payload=None,
    )
    [item] = read_all_items(project)
    assert item["launchPayload"] is None


# ---------------------------------------------------------------------------
# AC-2 storage round-trip — append_triage_item_idempotent
# ---------------------------------------------------------------------------

def test_idempotent_persists_launch_payload(project: Path) -> None:
    payload = "/shipwright-iterate --type bug\n\nWorkflow: ci.yml on main"
    new_id = append_triage_item_idempotent(
        project, source="github", severity="high", kind="bug",
        title="t", detail="d",
        dedup_key="gh-ci:ci.yml", launch_payload=payload,
    )
    assert new_id is not None
    [item] = read_all_items(project)
    assert item["launchPayload"] == payload


def test_idempotent_omitted_kwarg_persists_null(project: Path) -> None:
    append_triage_item_idempotent(
        project, source="drift", severity="medium", kind="improvement",
        title="t", detail="d", dedup_key="drift-foo",
    )
    [item] = read_all_items(project)
    assert item["launchPayload"] is None


# ---------------------------------------------------------------------------
# AC-8 idempotency — payload frozen at first append
# ---------------------------------------------------------------------------

def test_idempotent_second_call_does_not_overwrite_payload(project: Path) -> None:
    """Same dedup_key + open status → duplicate suppressed; first payload wins."""
    first = "/shipwright-security  (first run, 3 findings)"
    second = "/shipwright-security  (second run, 12 findings — would be stale)"

    new_id_a = append_triage_item_idempotent(
        project, source="github", severity="high", kind="bug",
        title="t", detail="d", dedup_key="gh-security:acme/foo",
        match_commit=False, window_seconds=None,
        launch_payload=first,
    )
    new_id_b = append_triage_item_idempotent(
        project, source="github", severity="high", kind="bug",
        title="t", detail="d", dedup_key="gh-security:acme/foo",
        match_commit=False, window_seconds=None,
        launch_payload=second,
    )

    assert new_id_a is not None
    assert new_id_b is None, "duplicate must be suppressed"
    [item] = read_all_items(project)
    assert item["launchPayload"] == first, (
        "first payload must win — frozen at first-append (AC-8)"
    )


# ---------------------------------------------------------------------------
# AC-9 parametrized null-safety across every documented source
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source", KNOWN_SOURCES)
def test_every_source_persists_null_when_payload_omitted(
    project: Path, source: str,
) -> None:
    """A legacy producer that doesn't supply launch_payload yields null on the wire.

    Drift protection: if anyone ever adds a default that isn't None, this
    parametrized check catches it for all 10 sources in one place.
    """
    append_triage_item_idempotent(
        project, source=source, severity="medium", kind="bug",
        title="t", detail="d", dedup_key=f"{source}-test",
    )
    [item] = read_all_items(project)
    assert item["launchPayload"] is None


@pytest.mark.parametrize("source", KNOWN_SOURCES)
def test_every_source_persists_payload_when_supplied(
    project: Path, source: str,
) -> None:
    """Any source MAY carry a payload — schema is open. Round-trips byte-identical."""
    payload = f"/shipwright-foo\n\nSource: {source}"
    append_triage_item_idempotent(
        project, source=source, severity="medium", kind="bug",
        title="t", detail="d", dedup_key=f"{source}-payload",
        launch_payload=payload,
    )
    [item] = read_all_items(project)
    assert item["launchPayload"] == payload


# ---------------------------------------------------------------------------
# Wire-format guard: launchPayload key present on every append event
# ---------------------------------------------------------------------------

def test_wire_event_carries_launch_payload_key_always(project: Path) -> None:
    """Producer→file on-disk: the JSONL line MUST carry `launchPayload`, even null.

    Forward-compat: consumers may read the field without a `.get()`. Tests
    the literal JSON shape, not the resolved-view dict.
    """
    append_triage_item(
        project, source="phaseQuality", severity="low", kind="bug",
        title="t", detail="d",
    )
    raw_lines = (project / ".shipwright" / TRIAGE_FILE).read_text(
        encoding="utf-8"
    ).splitlines()
    append_events = [
        json.loads(line)
        for line in raw_lines
        if line and json.loads(line).get("event") == "append"
    ]
    assert len(append_events) == 1
    assert "launchPayload" in append_events[0]
    assert append_events[0]["launchPayload"] is None


def test_wire_event_carries_supplied_payload_verbatim(project: Path) -> None:
    payload = "/shipwright-security\n\nMulti-line\n  with leading spaces\nand `backticks`."
    append_triage_item(
        project, source="github", severity="high", kind="bug",
        title="t", detail="d", launch_payload=payload,
    )
    raw_lines = (project / ".shipwright" / TRIAGE_FILE).read_text(
        encoding="utf-8"
    ).splitlines()
    append_events = [
        json.loads(line)
        for line in raw_lines
        if line and json.loads(line).get("event") == "append"
    ]
    assert append_events[0]["launchPayload"] == payload
