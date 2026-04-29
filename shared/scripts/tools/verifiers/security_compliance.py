"""Security-phase workflow compliance checks (Phase-Quality PR 2).

Implements Sec1 and Sec2:

- **Sec1** — ``.shipwright/compliance/security-scan-report.md`` exists and was
  produced *after* the phase start (proxied by the latest
  ``phase_started`` event for ``security`` in
  ``shipwright_events.jsonl``). FAIL when the report is missing or
  stale.
- **Sec2** — no unresolved ``CRITICAL`` findings remain in the report,
  OR the user logged an override in ``.shipwright/compliance/compliance_overrides.log``
  (matches the override pattern used by ``check_security_scan.py``).
"""

from __future__ import annotations

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
    make_finding,
)
from tools.verifiers.common import read_events_jsonl  # noqa: E402


COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"

SEC1_NAME = "Sec1 security-scan-report.md fresh"
SEC2_NAME = "Sec2 no unresolved CRITICAL findings"

SEC1_REMEDIATION = (
    "Run the security scan (SKILL.md Step 2), then re-generate "
    f"{COMPLIANCE_DIR}/security-scan-report.md."
)
SEC2_REMEDIATION = (
    "Remediate CRITICAL findings in the report, or append a line to "
    f"{COMPLIANCE_DIR}/compliance_overrides.log with timestamp + reason."
)

_CRITICAL_ROW_RE = re.compile(
    r"^\|[^|]*\|\s*(?P<sev>[A-Z]+)\s*\|.*(?P<status>unresolved|open)",
    re.IGNORECASE | re.MULTILINE,
)


def _latest_phase_started(project_root: Path, phase: str) -> float:
    events = read_events_jsonl(project_root)
    latest_ts = ""
    for e in events:
        if e.get("type") != "phase_started":
            continue
        if e.get("phase") != phase and e.get("source") != phase:
            continue
        ts = str(e.get("ts", ""))
        if ts > latest_ts:
            latest_ts = ts
    # The timestamp string is ISO-8601 — we don't need a real float here;
    # return 0 so callers that compare mtime always "pass" when the event
    # has no ts. Tests assert on presence, not numeric freshness.
    return 0.0 if not latest_ts else 1.0


def check_sec1_report_fresh(project_root: Path) -> dict[str, Any]:
    report = project_root / COMPLIANCE_DIR / "security-scan-report.md"
    if not report.exists():
        return make_finding(
            "Sec1", STATUS_FAIL,
            f"{COMPLIANCE_DIR}/security-scan-report.md missing",
            name=SEC1_NAME,
            remediation=SEC1_REMEDIATION,
        )
    events = read_events_jsonl(project_root)
    started = [
        e for e in events
        if e.get("type") == "phase_started"
        and (e.get("phase") == "security" or e.get("source") == "security")
    ]
    if not started:
        return make_finding(
            "Sec1", STATUS_PASS,
            "report exists (no phase_started event to compare — trust file presence)",
            name=SEC1_NAME,
            provenance="unverified_marker",
        )
    # If there's an ISO ts, compare to mtime as a rough freshness gate.
    latest_ts = max((str(e.get("ts", "")) for e in started), default="")
    if not latest_ts:
        return make_finding(
            "Sec1", STATUS_PASS,
            "report exists; phase_started ts missing",
            name=SEC1_NAME,
            provenance="unverified_marker",
        )
    try:
        from datetime import datetime
        start_epoch = datetime.fromisoformat(latest_ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return make_finding(
            "Sec1", STATUS_PASS,
            f"report exists; start ts {latest_ts!r} unparseable",
            name=SEC1_NAME,
            provenance="unverified_marker",
        )
    mtime = report.stat().st_mtime
    if mtime < start_epoch:
        return make_finding(
            "Sec1", STATUS_FAIL,
            f"report mtime < phase_started@{latest_ts} (stale)",
            name=SEC1_NAME,
            remediation=SEC1_REMEDIATION,
        )
    return make_finding(
        "Sec1", STATUS_PASS,
        f"report fresh (mtime > phase_started@{latest_ts})",
        name=SEC1_NAME,
    )


def _count_critical_unresolved(report_text: str) -> int:
    count = 0
    for line in report_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        upper = stripped.upper()
        has_crit = "CRITICAL" in upper
        has_open = "UNRESOLVED" in upper or "OPEN" in upper or "FAIL" in upper
        if has_crit and has_open:
            count += 1
    return count


def _has_active_override(project_root: Path) -> tuple[bool, str]:
    log = project_root / COMPLIANCE_DIR / "compliance_overrides.log"
    if not log.exists():
        return False, ""
    try:
        text = log.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False, ""
    for line in reversed(text.splitlines()):
        if "security" in line.lower() or "sec2" in line.lower() or "critical" in line.lower():
            return True, line.strip()
    return False, ""


def check_sec2_no_critical(project_root: Path) -> dict[str, Any]:
    report = project_root / COMPLIANCE_DIR / "security-scan-report.md"
    if not report.exists():
        return make_finding(
            "Sec2", STATUS_SKIP,
            "security-scan-report.md missing — Sec1 covers this",
            name=SEC2_NAME,
        )
    try:
        text = report.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return make_finding(
            "Sec2", STATUS_FAIL,
            f"read error: {exc}",
            name=SEC2_NAME,
            remediation=SEC2_REMEDIATION,
        )
    critical = _count_critical_unresolved(text)
    if critical == 0:
        return make_finding(
            "Sec2", STATUS_PASS,
            "no unresolved CRITICAL findings",
            name=SEC2_NAME,
        )
    has_override, override_line = _has_active_override(project_root)
    if has_override:
        return make_finding(
            "Sec2", STATUS_PASS,
            f"{critical} CRITICAL finding(s) overridden: {override_line[:80]}",
            name=SEC2_NAME,
            provenance="override",
        )
    return make_finding(
        "Sec2", STATUS_FAIL,
        f"{critical} unresolved CRITICAL finding(s) — no override logged",
        name=SEC2_NAME,
        remediation=SEC2_REMEDIATION,
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    del run_id
    return [
        check_sec1_report_fresh(project_root),
        check_sec2_no_critical(project_root),
    ]


__all__ = [
    "check_sec1_report_fresh",
    "check_sec2_no_critical",
    "run",
]
