"""Infrastructure-category checks (Phase-Quality PR 3).

Implements I1-I4 — freshness gates for the generated ``compliance/*``
docs that downstream auditors rely on (RTM, test evidence, change
history, SBOM). All four checks compare a doc's mtime against the
latest ``phase_started`` / ``phase_completed`` event for the current
phase; when no event is recorded yet, we SKIP instead of FAIL to avoid
false positives on mid-flow audits (plan § 7 R11).

Tier classification (plan § 3):
- **I1-I3** — Tier-1, FAIL on missing or stale doc.
- **I4** — Tier-2, WARN only. Further gated on **actual** dependency
  changes (``pyproject.toml`` / ``package.json`` / ``requirements.txt``
  mtime newer than SBOM mtime) so clean runs don't produce noise.

Plan mapping:
- I1 → ``compliance/traceability-matrix.md`` > latest ``phase_completed`` ts
- I2 → ``compliance/test-evidence.md`` > latest ``phase_started`` ts
- I3 → ``compliance/change-history.md`` > latest ``phase_started`` ts
- I4 → ``compliance/sbom.md`` > latest ``phase_started`` ts, **only if**
  a dependency manifest has changed since the last SBOM write
"""

from __future__ import annotations

import sys
from datetime import datetime
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
from tools.verifiers.common import read_events_jsonl  # noqa: E402


I1_NAME = "I1 traceability-matrix.md fresh after phase_completed"
I2_NAME = "I2 test-evidence.md fresh after phase_started"
I3_NAME = "I3 change-history.md fresh after phase_started"
I4_NAME = "I4 sbom.md fresh when dependencies changed"

I1_REMEDIATION = (
    "Regenerate compliance/traceability-matrix.md via "
    "`uv run update_compliance.py --phase <phase>`."
)
I2_REMEDIATION = (
    "Regenerate compliance/test-evidence.md via "
    "`uv run update_compliance.py --phase test` (or the build/iterate "
    "equivalent); test results feed this doc."
)
I3_REMEDIATION = (
    "Regenerate compliance/change-history.md via "
    "`uv run update_compliance.py --phase <phase>`."
)
I4_REMEDIATION = (
    "Regenerate compliance/sbom.md (for example via "
    "`uv run update_compliance.py --phase build`) so dependency "
    "changes are captured."
)

# A ~10-second tolerance avoids FP when the doc is regenerated within the
# same second as the `phase_started` event (plan § 7 R11).
_MTIME_TOLERANCE_SECONDS = 10.0

_DEPENDENCY_FILES: tuple[str, ...] = (
    "pyproject.toml",
    "package.json",
    "requirements.txt",
)


def _iso_to_epoch(ts: str) -> float | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def latest_phase_event_epoch(
    project_root: Path,
    phase: str,
    event_type: str,
) -> float | None:
    """Return the epoch timestamp of the most recent matching phase event.

    ``event_type`` is ``phase_started`` or ``phase_completed``. Events
    written by Shipwright stamp either a ``phase`` or a ``source`` field
    depending on age — we accept both (mirroring
    ``get_latest_phase_completed_event`` in common.py).
    """
    latest_iso = ""
    for event in read_events_jsonl(project_root):
        if event.get("type") != event_type:
            continue
        if event.get("phase") != phase and event.get("source") != phase:
            continue
        ts = str(event.get("ts") or event.get("timestamp") or "")
        if ts > latest_iso:
            latest_iso = ts
    return _iso_to_epoch(latest_iso) if latest_iso else None


def _check_doc_fresh(
    project_root: Path,
    doc_relpath: str,
    phase: str,
    *,
    check_id: str,
    name: str,
    remediation: str,
    event_type: str,
    status_on_missing: str = STATUS_FAIL,
    status_on_stale: str = STATUS_FAIL,
) -> dict[str, Any]:
    """Shared mtime-vs-event-epoch comparison used by I1-I3."""
    doc = project_root / doc_relpath
    if not doc.exists():
        return make_finding(
            check_id, status_on_missing,
            f"{doc_relpath} missing",
            name=name,
            remediation=remediation,
        )

    anchor = latest_phase_event_epoch(project_root, phase, event_type)
    if anchor is None:
        return make_finding(
            check_id, STATUS_SKIP,
            f"no {event_type} event for phase={phase} — freshness "
            f"not verifiable yet",
            name=name,
            provenance="unverified_marker",
        )

    mtime = doc.stat().st_mtime
    if mtime + _MTIME_TOLERANCE_SECONDS < anchor:
        drift = int(anchor - mtime)
        return make_finding(
            check_id, status_on_stale,
            f"{doc_relpath} mtime {drift}s older than {event_type}@"
            f"phase={phase}",
            name=name,
            remediation=remediation,
        )
    return make_finding(
        check_id, STATUS_PASS,
        f"{doc_relpath} fresh ({event_type}@phase={phase})",
        name=name,
    )


def check_i1_rtm_fresh(project_root: Path, phase: str) -> dict[str, Any]:
    return _check_doc_fresh(
        project_root,
        "compliance/traceability-matrix.md",
        phase,
        check_id="I1",
        name=I1_NAME,
        remediation=I1_REMEDIATION,
        event_type="phase_completed",
    )


def check_i2_test_evidence_fresh(project_root: Path, phase: str) -> dict[str, Any]:
    return _check_doc_fresh(
        project_root,
        "compliance/test-evidence.md",
        phase,
        check_id="I2",
        name=I2_NAME,
        remediation=I2_REMEDIATION,
        event_type="phase_started",
    )


def check_i3_change_history_fresh(project_root: Path, phase: str) -> dict[str, Any]:
    return _check_doc_fresh(
        project_root,
        "compliance/change-history.md",
        phase,
        check_id="I3",
        name=I3_NAME,
        remediation=I3_REMEDIATION,
        event_type="phase_started",
    )


def _dependency_files_newer_than(project_root: Path, reference_mtime: float) -> list[str]:
    """Return dependency-manifest names modified after ``reference_mtime``."""
    changed: list[str] = []
    for name in _DEPENDENCY_FILES:
        candidate = project_root / name
        if not candidate.exists():
            continue
        try:
            if candidate.stat().st_mtime > reference_mtime + _MTIME_TOLERANCE_SECONDS:
                changed.append(name)
        except OSError:
            continue
    return changed


def check_i4_sbom_fresh_on_dep_change(
    project_root: Path,
    phase: str,
) -> dict[str, Any]:
    """Tier-2 heuristic — only surfaces when dependencies actually changed.

    Three outcomes:
    - SBOM missing **and** dependency files present → WARN
    - SBOM present, no dep file newer than SBOM → SKIP (clean run)
    - SBOM stale compared to dep files → WARN with remediation
    """
    sbom = project_root / "compliance" / "sbom.md"
    any_dep_file = any(
        (project_root / n).exists() for n in _DEPENDENCY_FILES
    )
    if not any_dep_file:
        return make_finding(
            "I4", STATUS_SKIP,
            "no dependency manifest (pyproject.toml/package.json/"
            "requirements.txt) — SBOM not applicable",
            name=I4_NAME,
        )

    if not sbom.exists():
        return make_finding(
            "I4", STATUS_WARN,
            "compliance/sbom.md missing but dependency manifest present",
            name=I4_NAME,
            remediation=I4_REMEDIATION,
        )

    sbom_mtime = sbom.stat().st_mtime
    changed = _dependency_files_newer_than(project_root, sbom_mtime)
    if not changed:
        return make_finding(
            "I4", STATUS_SKIP,
            "sbom.md newer than every dependency manifest — no regen needed",
            name=I4_NAME,
        )

    anchor = latest_phase_event_epoch(project_root, phase, "phase_started")
    if anchor is not None and sbom_mtime + _MTIME_TOLERANCE_SECONDS < anchor:
        return make_finding(
            "I4", STATUS_WARN,
            f"sbom.md stale vs phase_started (dep files changed: {changed})",
            name=I4_NAME,
            remediation=I4_REMEDIATION,
        )

    return make_finding(
        "I4", STATUS_WARN,
        f"dep files newer than sbom.md: {changed}",
        name=I4_NAME,
        remediation=I4_REMEDIATION,
    )


# ---------------------------------------------------------------------------
# Phase → check list dispatch (plan § 5.1 "Plugin-Coverage")
# ---------------------------------------------------------------------------

_PHASE_TO_CHECKS: dict[str, tuple[str, ...]] = {
    "build":     ("I1", "I2", "I3", "I4"),
    "iterate":   ("I1", "I2", "I3", "I4"),
    "test":      ("I2",),
    "changelog": ("I3",),
}


def run(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Return infrastructure findings for ``phase`` per the plan's
    Plugin-Coverage table. Phases without infra coverage return [].
    """
    checks = _PHASE_TO_CHECKS.get(phase)
    if not checks:
        return []

    findings: list[dict[str, Any]] = []
    for check_id in checks:
        if check_id == "I1":
            findings.append(check_i1_rtm_fresh(project_root, phase))
        elif check_id == "I2":
            findings.append(check_i2_test_evidence_fresh(project_root, phase))
        elif check_id == "I3":
            findings.append(check_i3_change_history_fresh(project_root, phase))
        elif check_id == "I4":
            findings.append(check_i4_sbom_fresh_on_dep_change(project_root, phase))
    return findings


__all__ = [
    "check_i1_rtm_fresh",
    "check_i2_test_evidence_fresh",
    "check_i3_change_history_fresh",
    "check_i4_sbom_fresh_on_dep_change",
    "latest_phase_event_epoch",
    "run",
]
