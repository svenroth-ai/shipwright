"""Iterate-phase workflow compliance checks (Phase-Quality PR 2).

Implements W2 (F11 external-review marker) and W3 (F5a/F5b evidence).

Both checks honour the complexity-gate — ``small`` iterates skip
external review (W2) entirely. Marker-based checks carry
``provenance: "unverified_marker"`` so the dashboard surfaces them as
spoof-susceptible (plan § 4.5, R9).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    make_finding,
)
from tools.verifiers.common import read_events_jsonl, read_run_config  # noqa: E402


W2_NAME = "W2 F11 external-review marker"
W3_NAME = "W3 F5a/F5b work_completed + test-evidence"

W2_REMEDIATION = (
    "Run external review for this iterate (SKILL.md F10), then "
    "write planning/iterate/{run_id}-external-review.json OR update "
    "planning/iterate/external_review_state.json."
)
W3_REMEDIATION = (
    "Call record_event --type work_completed --source iterate and "
    "regenerate compliance/test-evidence.md via update_compliance.py."
)


_SMALL_COMPLEXITIES: frozenset[str] = frozenset({"small", "tiny", "trivial"})


def _latest_iterate_entry(project_root: Path, run_id: str) -> dict[str, Any] | None:
    data = read_run_config(project_root)
    if not data:
        return None
    history = data.get("iterate_history")
    if not isinstance(history, list):
        return None
    for entry in reversed(history):
        if entry.get("run_id") == run_id:
            return entry
    return history[-1] if history else None


def check_w2_external_review_marker(
    project_root: Path,
    run_id: str,
) -> dict[str, Any]:
    """W2 — external-review marker exists and is newer than the spec.

    SKIP for small iterates (by plan + SKILL.md). If no iterate entry
    exists yet (first run, config not written), SKIP to avoid FP during
    mid-flow audits.
    """
    entry = _latest_iterate_entry(project_root, run_id)
    if entry is not None:
        complexity = str(entry.get("complexity", "")).lower()
        if complexity in _SMALL_COMPLEXITIES:
            return make_finding(
                "W2", STATUS_SKIP,
                f"complexity={complexity} — external review not required",
                name=W2_NAME,
            )

    planning_dir = project_root / "planning" / "iterate"
    if not planning_dir.is_dir():
        return make_finding(
            "W2", STATUS_SKIP,
            "planning/iterate/ missing — nothing to verify yet",
            name=W2_NAME,
            provenance="unverified_marker",
        )

    per_run = planning_dir / f"{run_id}-external-review.json"
    state_file = planning_dir / "external_review_state.json"

    spec_files = [
        p for p in planning_dir.glob(f"*{run_id}*.md")
        if "miniplan" not in p.name
    ]
    spec_mtime = max((p.stat().st_mtime for p in spec_files), default=0.0)

    if per_run.exists():
        if not spec_mtime or per_run.stat().st_mtime >= spec_mtime:
            return make_finding(
                "W2", STATUS_PASS,
                f"{per_run.name} present",
                name=W2_NAME,
                provenance="unverified_marker",
            )
        return make_finding(
            "W2", STATUS_FAIL,
            f"{per_run.name} older than spec (mtime drift)",
            name=W2_NAME,
            remediation=W2_REMEDIATION,
            provenance="unverified_marker",
        )

    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return make_finding(
                "W2", STATUS_FAIL,
                "external_review_state.json malformed",
                name=W2_NAME,
                remediation=W2_REMEDIATION,
            )
        status = str(state.get("status", ""))
        if status == "completed":
            if not spec_mtime or state_file.stat().st_mtime >= spec_mtime:
                return make_finding(
                    "W2", STATUS_PASS,
                    f"external_review_state.json status={status}",
                    name=W2_NAME,
                    provenance="unverified_marker",
                )
            return make_finding(
                "W2", STATUS_FAIL,
                "external_review_state.json older than spec",
                name=W2_NAME,
                remediation=W2_REMEDIATION,
                provenance="unverified_marker",
            )
        if status.startswith("skipped_"):
            reason = state.get("reason") or "<no reason>"
            return make_finding(
                "W2", STATUS_PASS,
                f"status={status} (reason: {reason})",
                name=W2_NAME,
                provenance="unverified_marker",
            )

    return make_finding(
        "W2", STATUS_FAIL,
        f"no external-review marker for run_id={run_id}",
        name=W2_NAME,
        remediation=W2_REMEDIATION,
    )


def check_w3_work_completed_and_evidence(
    project_root: Path,
    run_id: str,
) -> dict[str, Any]:
    """W3 — work_completed event recorded + compliance/test-evidence.md fresh."""
    events = read_events_jsonl(project_root)
    matched = [
        e for e in events
        if e.get("type") == "work_completed"
        and e.get("source") == "iterate"
        and (not run_id or run_id in (e.get("run_id", ""), e.get("iterate_run_id", ""))
             or run_id in str(e.get("description", "")))
    ]
    if not matched and run_id:
        # Fall back to any iterate work_completed — run_id isn't always stamped
        matched = [
            e for e in events
            if e.get("type") == "work_completed" and e.get("source") == "iterate"
        ]

    if not matched:
        return make_finding(
            "W3", STATUS_FAIL,
            "no iterate work_completed event in shipwright_events.jsonl",
            name=W3_NAME,
            remediation=W3_REMEDIATION,
        )

    evidence_file = project_root / "compliance" / "test-evidence.md"
    if not evidence_file.exists():
        return make_finding(
            "W3", STATUS_FAIL,
            "compliance/test-evidence.md missing",
            name=W3_NAME,
            remediation=W3_REMEDIATION,
        )

    age = time.time() - evidence_file.stat().st_mtime
    latest_ts = max((e.get("ts", "") for e in matched), default="")
    # 24h freshness window — iterate runs can span a workday
    if age > 86400:
        return make_finding(
            "W3", STATUS_FAIL,
            f"test-evidence.md mtime stale ({int(age)}s > 86400s)",
            name=W3_NAME,
            remediation=W3_REMEDIATION,
        )
    return make_finding(
        "W3", STATUS_PASS,
        f"work_completed@{latest_ts}, test-evidence.md age {int(age)}s",
        name=W3_NAME,
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    return [
        check_w2_external_review_marker(project_root, run_id),
        check_w3_work_completed_and_evidence(project_root, run_id),
    ]


__all__ = [
    "check_w2_external_review_marker",
    "check_w3_work_completed_and_evidence",
    "run",
]
