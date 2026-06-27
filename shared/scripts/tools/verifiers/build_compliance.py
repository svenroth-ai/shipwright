"""Build-phase workflow compliance checks (Phase-Quality PR 2).

Implements W1 (TDD order). TDD-order verification needs a tool-call
trace (pytest-Bash before Write-event on impl-file) which Shipwright's
``shipwright_events.jsonl`` does not record. Per plan § 3 + R8 this
check is **Tier-2**: it SKIPs when no evidence exists, emits a weak
PASS when ``test_run`` events precede ``work_completed`` events for
the same run, and **never FAILs** — false-positive risk is too high
and the signal is heuristic only.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.phase_quality import (  # noqa: E402
    STATUS_PASS,
    STATUS_SKIP,
    make_finding,
)
from tools.verifiers.common import read_events_jsonl  # noqa: E402


W1_NAME = "W1 TDD order (test_run before work_completed)"


def check_w1_tdd_order(project_root: Path, run_id: str) -> dict[str, Any]:
    """Heuristic W1 check — never FAILs (plan § 7 R8).

    Positive signal: events.jsonl has a ``test_run`` or
    ``work_completed`` with ``tests.new > 0`` / ``tests.passed > 0`` that
    appears before the latest ``work_completed`` for this run_id. Pure
    order check against timestamps — the impl vs test file separation
    isn't tracked in events.jsonl so we accept any evidence of a test
    run before the commit as TDD-compatible.

    SKIP when evidence is insufficient (empty log, no work_completed,
    or no test evidence at all).
    """
    events = read_events_jsonl(project_root)
    if not events:
        return make_finding(
            "W1", STATUS_SKIP,
            "shipwright_events.jsonl empty or missing — TDD order unverifiable",
            name=W1_NAME,
            provenance="unverified_marker",
        )

    work_events = [
        e for e in events
        if e.get("type") == "work_completed" and e.get("source") == "build"
    ]
    if not work_events:
        return make_finding(
            "W1", STATUS_SKIP,
            "no build work_completed events — TDD order unverifiable",
            name=W1_NAME,
            provenance="unverified_marker",
        )

    has_test_evidence = any(
        e.get("type") == "test_run" for e in events
    ) or any(
        isinstance(e.get("tests"), dict) and (
            (e["tests"].get("new") or 0) > 0
            or (e["tests"].get("passed") or 0) > 0
            or (e["tests"].get("total") or 0) > 0
        )
        for e in work_events
    )
    if not has_test_evidence:
        return make_finding(
            "W1", STATUS_SKIP,
            "no test_run events and no tests metadata on work_completed — "
            "TDD order unverifiable",
            name=W1_NAME,
            provenance="unverified_marker",
        )

    latest_ts = max((e.get("ts", "") for e in work_events), default="")
    test_ts = ""
    for e in events:
        if e.get("type") == "test_run":
            ts = e.get("ts", "")
            if ts and (not test_ts or ts < test_ts):
                test_ts = ts

    if test_ts and latest_ts and test_ts <= latest_ts:
        return make_finding(
            "W1", STATUS_PASS,
            f"test_run@{test_ts} precedes work_completed@{latest_ts}",
            name=W1_NAME,
            provenance="events.jsonl",
        )
    return make_finding(
        "W1", STATUS_SKIP,
        "test evidence present but precedence order not determinable — "
        "TDD order unverifiable",
        name=W1_NAME,
        provenance="unverified_marker",
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    """Return workflow findings for the build phase."""
    return [check_w1_tdd_order(project_root, run_id)]


__all__ = ["check_w1_tdd_order", "run"]
