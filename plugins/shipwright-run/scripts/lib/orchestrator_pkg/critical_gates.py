"""Phase-Quality critical-gate helpers for the orchestrator package.

Implements the W5/W6/W7 FAIL-blocking gate (plan § 4.4 / 9.2), opt-in
via ``SHIPWRIGHT_ENFORCE_CRITICAL_GATES=1``. Reads the latest per-phase
Phase-Quality finding written by the Stop hook and promotes any FAIL
in the allowlisted check-IDs to an ask-level issue.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .constants import _CRITICAL_GATE_CHECK_IDS


def _enforce_critical_gates_enabled() -> bool:
    """Return True when SHIPWRIGHT_ENFORCE_CRITICAL_GATES opts-in.

    Default OFF in code (plan § 9.1). Rollout week 6 flips it on for
    W5/W6/W7 FAILs (plan § 9.2).
    """
    raw = os.environ.get("SHIPWRIGHT_ENFORCE_CRITICAL_GATES", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _read_latest_phase_quality_finding(
    project_root: Path, phase: str,
) -> dict[str, Any] | None:
    """Return the most recent Phase-Quality finding JSON for ``phase``.

    The Stop hook writes per-run findings to
    ``.shipwright/compliance/skill-compliance/<phase>-<run_id>-<session>.json``. We
    pick the latest by mtime so the gate reflects the current run's
    audit (plan § 4.4).
    """
    finding_dir = project_root / ".shipwright" / "compliance" / "skill-compliance"
    if not finding_dir.is_dir():
        return None

    candidates = sorted(
        finding_dir.glob(f"{phase}-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _collect_critical_gate_issues(finding: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ask-level validation issues for any critical-gate FAIL.

    A "critical" FAIL is a finding whose ``id`` is in
    ``_CRITICAL_GATE_CHECK_IDS`` with status=FAIL. SKIP/WARN/PASS are
    ignored. Tier-2 findings are never considered — critical gating is
    Tier-1 only by design (plan § 9.2).
    """
    issues: list[dict[str, Any]] = []
    for category in ("workflow", "canon", "infrastructure",
                     "traceability", "quality", "spec"):
        for item in finding.get(category, []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("status") != "FAIL":
                continue
            check_id = item.get("id") or ""
            if check_id not in _CRITICAL_GATE_CHECK_IDS:
                continue
            if item.get("tier") == 2:  # safety belt — never gate Tier-2
                continue
            issues.append({
                "severity": "ask",
                "name": f"{check_id} ({category})",
                "reason": item.get("evidence") or "critical check failed",
                "remediation": item.get("remediation")
                    or "Re-run the validator or override via --force after fixing the root cause.",
            })
    return issues
