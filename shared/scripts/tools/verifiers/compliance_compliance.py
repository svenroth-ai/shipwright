"""Compliance-phase workflow compliance checks (Phase-Quality PR 2).

Implements Cmp1 (dashboard-per-phase coverage — Tier-2, heuristic) and
Cmp2 (RTM coverage threshold — wrapper around existing compliance
hook logic in ``check_rtm_coverage.py``).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    make_finding,
)
from tools.verifiers.common import read_run_config  # noqa: E402


COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"

CMP1_NAME = "Cmp1 dashboard covers completed phases (Tier-2)"
CMP2_NAME = "Cmp2 RTM coverage meets threshold"

CMP1_REMEDIATION = (
    f"Regenerate {COMPLIANCE_DIR}/dashboard.md via update_compliance.py so "
    "every completed phase is represented."
)
CMP2_REMEDIATION = (
    "Raise RTM coverage (link FRs to commits) or lower the threshold "
    "in shipwright_compliance_config.json.enforcement.rtm_coverage_min."
)

_DEFAULT_RTM_MIN_PCT = 80
_COVERAGE_RE = re.compile(r"Traceability coverage\s*\|\s*(\d+)%")


def check_cmp1_dashboard_covers_phases(project_root: Path) -> dict[str, Any]:
    """Tier-2 heuristic: ``.shipwright/compliance/dashboard.md`` mentions every
    phase listed in ``shipwright_run_config.json.completed_steps``."""
    dashboard = project_root / COMPLIANCE_DIR / "dashboard.md"
    if not dashboard.exists():
        return make_finding(
            "Cmp1", STATUS_WARN,
            f"{COMPLIANCE_DIR}/dashboard.md missing",
            name=CMP1_NAME,
            remediation=CMP1_REMEDIATION,
        )
    data = read_run_config(project_root)
    completed = data.get("completed_steps") if data else None
    if not isinstance(completed, list) or not completed:
        return make_finding(
            "Cmp1", STATUS_SKIP,
            "no completed_steps in run_config — nothing to compare",
            name=CMP1_NAME,
        )
    try:
        text = dashboard.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError as exc:
        return make_finding(
            "Cmp1", STATUS_WARN,
            f"read error: {exc}",
            name=CMP1_NAME,
            remediation=CMP1_REMEDIATION,
        )
    missing = [p for p in completed if p.lower() not in text]
    if missing:
        return make_finding(
            "Cmp1", STATUS_WARN,
            f"{len(missing)} completed phase(s) not mentioned: {missing[:5]}",
            name=CMP1_NAME,
            remediation=CMP1_REMEDIATION,
        )
    return make_finding(
        "Cmp1", STATUS_PASS,
        f"{len(completed)} completed phase(s) all present in dashboard",
        name=CMP1_NAME,
    )


def _load_rtm_threshold_pct(project_root: Path) -> int:
    cfg = project_root / "shipwright_compliance_config.json"
    if not cfg.exists():
        return _DEFAULT_RTM_MIN_PCT
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _DEFAULT_RTM_MIN_PCT
    raw = data.get("enforcement", {}).get("rtm_coverage_min")
    if isinstance(raw, (int, float)):
        if raw <= 1.0:
            return int(raw * 100)
        return int(raw)
    return _DEFAULT_RTM_MIN_PCT


def _read_rtm_coverage(project_root: Path) -> int | None:
    rtm = project_root / COMPLIANCE_DIR / "traceability-matrix.md"
    if not rtm.exists():
        return None
    try:
        text = rtm.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = _COVERAGE_RE.search(text)
    return int(m.group(1)) if m else None


def check_cmp2_rtm_coverage(project_root: Path) -> dict[str, Any]:
    threshold = _load_rtm_threshold_pct(project_root)
    coverage = _read_rtm_coverage(project_root)
    if coverage is None:
        return make_finding(
            "Cmp2", STATUS_SKIP,
            f"{COMPLIANCE_DIR}/traceability-matrix.md missing or no coverage row",
            name=CMP2_NAME,
            remediation=CMP2_REMEDIATION,
        )
    if coverage < threshold:
        return make_finding(
            "Cmp2", STATUS_FAIL,
            f"coverage={coverage}% < threshold={threshold}%",
            name=CMP2_NAME,
            remediation=CMP2_REMEDIATION,
        )
    return make_finding(
        "Cmp2", STATUS_PASS,
        f"coverage={coverage}% >= threshold={threshold}%",
        name=CMP2_NAME,
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    del run_id
    return [
        check_cmp1_dashboard_covers_phases(project_root),
        check_cmp2_rtm_coverage(project_root),
    ]


__all__ = [
    "check_cmp1_dashboard_covers_phases",
    "check_cmp2_rtm_coverage",
    "run",
]
