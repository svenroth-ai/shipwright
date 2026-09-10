"""Tests for shared/scripts/tools/write_grill_trace.py — the grill-trace
producer. Direct-call coverage for write_trace() (diff-coverage visible),
plus one --payload-file CLI subprocess test mirroring write_context_term.py's
precedent for the shell-injection-safety contract (P4.1 final review).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.grill_trace_format import GrillTraceError, read_trace_dir, trace_path
from tools.write_grill_trace import write_trace

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "shared" / "scripts" / "tools" / "write_grill_trace.py"


def _payload(**overrides) -> dict:
    payload = {
        "requirement_key": "login-rate-limit",
        "requirement_text": "The system SHOULD rate-limit login attempts to 5 per minute per IP.",
        "surface": "project",
        "evidence": ["turn 4: user described repeated failed sign-ins as a concern"],
        "dimensions": {
            "outcome": "answered",
            "purpose": "answered",
            "boundaries": "answered",
            "failure": "answered",
            "glossary": "n/a:no new term introduced",
            "rationale": "n/a:not hard to reverse",
            "out_of_scope": "answered",
        },
        "fit_criterion": "a sixth failed sign-in within a minute from one IP is refused",
        "glossary_delta": [],
        "confirmed_by": "user confirmed the shared understanding in turn 7",
        "terms_used": [],
    }
    payload.update(overrides)
    return payload


def test_write_trace_creates_a_new_file(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"

    result = write_trace(planning_dir, _payload(), lock_timeout=5.0)

    assert result["status"] == "created"
    path = trace_path(planning_dir, "login-rate-limit")
    assert path.exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["confirmed_by"] == "user confirmed the shared understanding in turn 7"


def test_write_trace_updates_an_existing_file_in_place(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    write_trace(planning_dir, _payload(), lock_timeout=5.0)

    result = write_trace(
        planning_dir, _payload(confirmed_by="revised confirmation, turn 9"), lock_timeout=5.0,
    )

    assert result["status"] == "updated"
    path = trace_path(planning_dir, "login-rate-limit")
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["confirmed_by"] == "revised confirmation, turn 9"
    # Still exactly one file for this requirement_key.
    assert list((planning_dir / "grill-traces").glob("*.json")) == [path]


def test_write_trace_rejects_a_malformed_payload_before_any_write(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"

    with pytest.raises(GrillTraceError):
        write_trace(planning_dir, _payload(confirmed_by="  "), lock_timeout=5.0)

    assert not (planning_dir / "grill-traces").exists()


def test_write_trace_is_idempotent_on_repeated_identical_payload(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    payload = _payload()

    write_trace(planning_dir, payload, lock_timeout=5.0)
    write_trace(planning_dir, payload, lock_timeout=5.0)

    path = trace_path(planning_dir, "login-rate-limit")
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["requirement_key"] == "login-rate-limit"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def test_cli_payload_file_writes_a_trace_with_an_embedded_single_quote(tmp_path):
    """The regression this --payload-file design exists for (write_context_term.py
    precedent): free interview text containing a single quote must never be
    substituted into a shell-quoted CLI argument."""
    payload = _payload(confirmed_by="it's confirmed — the user's own words")
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    proc = _run_cli(
        "--project-root", str(tmp_path),
        "--payload-file", str(payload_path),
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "created"
    written = json.loads(
        (tmp_path / ".shipwright" / "planning" / "grill-traces" / "login-rate-limit.json")
        .read_text(encoding="utf-8")
    )
    assert written["confirmed_by"] == "it's confirmed — the user's own words"


def test_producer_write_round_trips_through_the_sanctioned_reader(tmp_path):
    """ADR-024 affected-boundaries probe: the producer
    (write_grill_trace.write_trace) and the consumer
    (grill_trace_format.read_trace_dir) are two different code paths over
    the same serialized format — round-trip them for real, not just each
    tested in isolation against a hand-written fixture JSON."""
    planning_dir = tmp_path / ".shipwright" / "planning"
    payload = _payload(terms_used=["Order"], glossary_delta=[{"term": "Order", "recorded_in": "CONTEXT.md"}])

    write_trace(planning_dir, payload, lock_timeout=5.0)
    traces = read_trace_dir(planning_dir)

    assert len(traces) == 1
    trace = traces[0]
    assert trace.requirement_key == payload["requirement_key"]
    assert trace.requirement_text == payload["requirement_text"]
    assert trace.dimensions == payload["dimensions"]
    assert trace.fit_criterion == payload["fit_criterion"]
    assert trace.confirmed_by == payload["confirmed_by"]
    assert trace.terms_used == ("Order",)
    assert trace.glossary_delta == ({"term": "Order", "recorded_in": "CONTEXT.md"},)


def test_cli_rejects_a_missing_project_root(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(_payload()), encoding="utf-8")

    proc = _run_cli(
        "--project-root", str(tmp_path / "does-not-exist"),
        "--payload-file", str(payload_path),
    )

    assert proc.returncode == 1
    assert "does not exist" in proc.stderr
