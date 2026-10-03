"""F11 warning: this run's F0 evidence was RESUMED, so part of it was reused, not executed.

``stage_f0_evidence`` marks a resumed F0 run as ``resumed_local`` in the staged provenance
sidecar; the evidence index tags the carried-over testcases ``reused``. This check makes that
visible at finalization. It NEVER blocks (WARNING, ``strict_exempt``): resume keeps its
speed-up and CI's full run is the safety net (operator decision, iterate-2026-10-02).
"""

from __future__ import annotations

from pathlib import Path

from .common import CheckResult, Severity

_NAME = "F0 evidence is resumed-local (reused results)"
FAILED_ONLY = "failed-only"


def _describe(unit: str, entry: object) -> str:
    if isinstance(entry, dict) and entry.get("mode") == FAILED_ONLY:
        reran = entry.get("rerun_tests")
        return f"{unit} (re-ran {len(reran) if isinstance(reran, list) else 0} red test(s), rest reused)"
    return f"{unit} (green result reused)"


def check_resumed_evidence(project_root: Path, run_id: str) -> CheckResult:
    """Warn when this run's staged F0 evidence carries a ``resumed_local`` marker.

    Never raises: it is warning-only, so an unreadable or malformed sidecar must not turn
    into a blocking crash of the F11 verifier - it degrades to a skipped result.
    """
    try:
        return _check(project_root, run_id)
    except Exception as exc:  # noqa: BLE001 - advisory check must never block F11
        return CheckResult(_NAME, True, f"skipped (could not read provenance: {type(exc).__name__})",
                           severity=Severity.SKIPPED.value)


def _check(project_root: Path, run_id: str) -> CheckResult:
    from lib import evidence_drop  # noqa: PLC0415 - lazy: needs shared/scripts on sys.path (ADR-045)

    if not evidence_drop.evidence_is_fresh(project_root, run_id):
        return CheckResult(_NAME, True, "skipped (no staged evidence for this run)",
                           severity=Severity.SKIPPED.value)
    marker = (evidence_drop.read_provenance(project_root) or {}).get("resumed_local")
    if not isinstance(marker, dict):
        return CheckResult(_NAME, True, "full run - nothing reused")
    units = marker.get("units")
    units = units if isinstance(units, dict) else {}
    named = "; ".join(_describe(u, e) for u, e in sorted(units.items())) or "units not recorded"
    return CheckResult(
        _NAME, False,
        f"F0 evidence for {run_id} is RESUMED, not a full run: {named}. Reused testcases passed "
        "on an older tree (tagged `reused` in the evidence index); CI's full run is the net.",
        severity=Severity.WARNING.value, strict_exempt=True,
    )
