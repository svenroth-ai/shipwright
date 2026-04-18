"""Phase-Quality-Audit infrastructure.

Finding-JSON schema, atomic writes, aggregate rewrites, dashboard
regeneration and helpers for the Stop-hook consolidated audit entry
point (``shared/scripts/hooks/audit_phase_quality_on_stop.py``).

This module is PR 1 of a 4-PR epic. PR 1 ships the hook mechanic plus
C1-C5 Canon integration; PR 2-4 add Workflow / Infrastructure / Trace /
Quality / Spec categories. All category runners except ``canon`` return
empty lists in PR 1 — the dispatcher stays stable so later PRs only
have to fill in the slots.

Design rules:

- Never block: every public function is best-effort; callers exit 0.
- Deterministic regeneration: dashboard + aggregate report are rewritten
  from per-run finding JSON files, not mutated in place.
- Cross-platform locks via ``shared/scripts/lib/file_lock.py``.
- Greenfield-safe: ``is_shipwright_project`` gates the whole pipeline,
  so running this in a non-Shipwright repo is a silent no-op.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.file_lock import LockTimeout, file_lock  # noqa: E402
from tools.verifiers.common import (  # noqa: E402
    CheckResult,
    Severity,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_c3_session_handoff_fresh_after_phase,
    check_c4_decision_log_has_phase_adr,
    check_c5_changelog_unreleased_has_phase_entry,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLUGIN_TO_PHASE: dict[str, str] = {
    "shipwright-project": "project",
    "shipwright-design": "design",
    "shipwright-plan": "plan",
    "shipwright-build": "build",
    "shipwright-test": "test",
    "shipwright-security": "security",
    "shipwright-deploy": "deploy",
    "shipwright-changelog": "changelog",
    "shipwright-compliance": "compliance",
    "shipwright-iterate": "iterate",
}

# Phases that take ADR-worthy decisions (C4 applies).
C4_PHASES: frozenset[str] = frozenset({"project", "plan", "build", "iterate"})

# User-facing phases that prepend a CHANGELOG bullet (C5 applies).
C5_PHASES: frozenset[str] = frozenset({"project", "design", "build", "deploy", "iterate"})

# C5 Keep-a-Changelog category per phase.
C5_CATEGORY: dict[str, str] = {
    "project": "Added",
    "design": "Added",
    "build": "Added",
    "deploy": "Changed",
    "iterate": "Added",
}

# Tier classification — Tier-2 means "heuristic, never enforcement" (plan § 3).
# C1-C5 are all Tier-1.
TIER_2_CHECK_IDS: frozenset[str] = frozenset({
    "W1", "I4", "T2", "Q1", "S3", "S4", "S5", "S7", "S9", "S10", "Cmp1", "D2",
})

CATEGORIES: tuple[str, ...] = (
    "canon", "workflow", "infrastructure", "traceability", "quality", "spec",
)

MAX_REPORT_RUNS = 10
MAX_SESSION_SUMMARY_RUNS = 5
GC_AGE_DAYS = 90

FINDING_DIR = "compliance/skill-compliance"
REPORT_PATH = "compliance/skill-compliance-report.md"
SUMMARY_PATH = "agent_docs/skill-compliance-findings.md"
DASHBOARD_PATH = "compliance/skill-compliance-dashboard.md"
LOCK_PATH = ".shipwright/locks/phase-quality.lock"


# ---------------------------------------------------------------------------
# Enforcement flags (PR 1: all default OFF in code; PR 2-4 wire them in).
# ---------------------------------------------------------------------------

def flag_enabled(name: str, default: bool = False) -> bool:
    """Read a Shipwright enforcement flag from the environment.

    Default is ``False`` for every ``ENFORCE_*`` flag so PR 1 ships with
    audit-only behaviour — no user-visible effect without explicit opt-in.
    """
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def phase_quality_enabled() -> bool:
    """Whether the Stop-hook audit should run at all.

    Default ``on``. Setting ``SHIPWRIGHT_PHASE_QUALITY=0`` (or ``false``)
    is the documented rollback lever (plan § 9.2).
    """
    raw = os.environ.get("SHIPWRIGHT_PHASE_QUALITY", "").strip().lower()
    if not raw:
        return True
    return raw not in ("0", "false", "no", "off")


def skipped_check_ids() -> set[str]:
    """Parse ``SHIPWRIGHT_SKIP_QUALITY_CHECK`` into a set of check ids."""
    raw = os.environ.get("SHIPWRIGHT_SKIP_QUALITY_CHECK", "").strip()
    if not raw:
        return set()
    return {tok.strip() for tok in raw.split(",") if tok.strip()}


def override_reason() -> str:
    return os.environ.get("SHIPWRIGHT_AUDIT_OVERRIDE_REASON", "").strip()


# ---------------------------------------------------------------------------
# Project / phase resolution
# ---------------------------------------------------------------------------

_CONFIG_MARKERS: tuple[str, ...] = (
    "shipwright_run_config.json",
    "shipwright_project_config.json",
    "shipwright_plan_config.json",
    "shipwright_build_config.json",
    "shipwright_events.jsonl",
)


def is_shipwright_project(project_root: Path) -> bool:
    """Return True when ``project_root`` looks like a Shipwright project.

    Matches the contract used by ``generate_handoff_on_stop.py`` and
    ``check_rtm_coverage.py`` so all Stop hooks agree on what counts as
    greenfield. We require at least one marker OR ``agent_docs/`` so
    fresh projects between ``/shipwright-project`` init and the first
    config write aren't skipped.
    """
    if any((project_root / m).exists() for m in _CONFIG_MARKERS):
        return True
    return (project_root / "agent_docs").is_dir()


def phase_from_plugin_root(plugin_root: str | os.PathLike[str] | None) -> str | None:
    """Map ``CLAUDE_PLUGIN_ROOT`` to the Shipwright phase name."""
    if not plugin_root:
        return None
    name = Path(plugin_root).name
    return PLUGIN_TO_PHASE.get(name)


def resolve_run_id(project_root: Path, session_id: str) -> str:
    """Composite-fallback run_id resolution (plan § 5.3).

    Priority:
    1. ``shipwright_run_config.json::run_id``
    2. ``events.jsonl`` latest ``run_started`` event
    3. ``SHIPWRIGHT_LOOP_ID`` + ``SHIPWRIGHT_LOOP_UNIT_ID``
    4. ``session_id`` itself (standalone)
    """
    run_config = project_root / "shipwright_run_config.json"
    if run_config.exists():
        try:
            data = json.loads(run_config.read_text(encoding="utf-8"))
            run_id = data.get("run_id")
            if isinstance(run_id, str) and run_id:
                return run_id
        except (json.JSONDecodeError, OSError):
            pass

    events_path = project_root / "shipwright_events.jsonl"
    if events_path.exists():
        try:
            content = events_path.read_text(encoding="utf-8", errors="ignore")
            latest_run_id: str | None = None
            for raw in content.splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") == "run_started":
                    rid = obj.get("run_id") or obj.get("id")
                    if isinstance(rid, str) and rid:
                        latest_run_id = rid
            if latest_run_id:
                return latest_run_id
        except OSError:
            pass

    loop_id = os.environ.get("SHIPWRIGHT_LOOP_ID", "").strip()
    loop_unit = os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID", "").strip()
    if loop_id and loop_unit:
        return f"{loop_id}-{loop_unit}"
    if loop_id:
        return loop_id

    return session_id or "unknown"


def resolve_source(project_root: Path, phase: str) -> str:
    """Infer the audit source (orchestrator / standalone / iterate).

    Used for operator telemetry — does not gate any logic. ``iterate`` is
    always tagged regardless of orchestrated state because iterate runs
    on a separate finalize path.
    """
    if phase == "iterate":
        return "iterate"
    run_config = project_root / "shipwright_run_config.json"
    if not run_config.exists():
        return "standalone"
    try:
        data = json.loads(run_config.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "standalone"
    if data.get("standalone") is True:
        return "standalone"
    if not data.get("current_step"):
        return "standalone"
    return "orchestrator"


# ---------------------------------------------------------------------------
# Finding schema helpers
# ---------------------------------------------------------------------------

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_WARN = "WARN"
STATUS_SKIP = "SKIP"


def _sanitize_filename(s: str) -> str:
    """Return a filesystem-safe fragment for finding filenames."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "unknown"


def finding_filename(phase: str, run_id: str, session_id: str) -> str:
    return f"{_sanitize_filename(phase)}-{_sanitize_filename(run_id)}-{_sanitize_filename(session_id)}.json"


def finding_path(project_root: Path, phase: str, run_id: str, session_id: str) -> Path:
    return project_root / FINDING_DIR / finding_filename(phase, run_id, session_id)


def already_audited(project_root: Path, phase: str, run_id: str, session_id: str) -> bool:
    """Idempotency guard (plan § 5.4).

    Returns True when a valid Finding-JSON already exists for the
    ``(phase, run_id, session_id)`` triple. Corrupt JSONs count as "not
    audited" so we overwrite rather than skip (plan § 4.13).
    """
    path = finding_path(project_root, phase, run_id, session_id)
    if not path.exists():
        return False
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# CheckResult → Finding conversion
# ---------------------------------------------------------------------------

_CHECK_ID_RE = re.compile(r"^(?P<id>[A-Z][A-Za-z0-9]*\d+)\b")


def _check_result_to_finding(
    result: CheckResult,
    default_id: str = "",
    remediation: str = "",
    provenance: str = "",
) -> dict[str, Any]:
    """Convert a ``CheckResult`` into the finding-dict shape."""
    status = _status_for(result)
    check_id = default_id
    if not check_id:
        m = _CHECK_ID_RE.match(result.name)
        if m:
            check_id = m.group("id")
    finding: dict[str, Any] = {
        "id": check_id or result.name,
        "name": result.name,
        "status": status,
        "evidence": result.detail or "",
    }
    if remediation:
        finding["remediation"] = remediation
    if provenance:
        finding["provenance"] = provenance
    if check_id in TIER_2_CHECK_IDS:
        finding["tier"] = 2
    return finding


def _status_for(result: CheckResult) -> str:
    if result.is_skipped:
        return STATUS_SKIP
    if result.ok is True:
        return STATUS_PASS
    if result.severity == Severity.WARNING.value:
        return STATUS_WARN
    return STATUS_FAIL


# ---------------------------------------------------------------------------
# Canon category runner (C1-C5)
# ---------------------------------------------------------------------------

CANON_REMEDIATION: dict[str, str] = {
    "C1": "Run record_event.py --type phase_completed --source <phase>",
    "C2": "Run update_build_dashboard.py --phase <phase>",
    "C3": "Regenerate session_handoff.md via generate_session_handoff.py --reason '<phase>: ...'",
    "C4": "Add an ADR to agent_docs/decision_log.md via write_decision_log.py",
    "C5": "Prepend an Unreleased bullet via append_changelog_entry.py",
}


def run_canon_checks(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Run the C1-C5 Canon checks for ``phase`` and return finding dicts.

    Thin wrapper around ``tools/verifiers/common.py`` helpers so PR 1
    covers the standalone-Canon gap (plan § 1). Phase-specific verifier
    modules stay authoritative for the orchestrated path — this wrapper
    only runs the generic C1-C5 so it works uniformly for every plugin
    (including security + compliance which have no phase module).
    """
    skip_ids = skipped_check_ids()
    findings: list[dict[str, Any]] = []

    def _emit(check_id: str, result: CheckResult) -> None:
        if check_id in skip_ids:
            override = override_reason() or "skipped via SHIPWRIGHT_SKIP_QUALITY_CHECK"
            skip_result = CheckResult(
                name=result.name,
                ok=None,
                detail=override,
                severity=Severity.SKIPPED.value,
            )
            findings.append(_check_result_to_finding(
                skip_result, default_id=check_id,
                remediation=CANON_REMEDIATION.get(check_id, ""),
                provenance="override",
            ))
            return
        findings.append(_check_result_to_finding(
            result, default_id=check_id,
            remediation=CANON_REMEDIATION.get(check_id, ""),
        ))

    _emit("C1", check_c1_phase_event_recorded(project_root, phase))
    _emit("C2", check_c2_dashboard_reflects_phase(project_root, phase))
    _emit("C3", check_c3_session_handoff_fresh_after_phase(project_root, phase))

    if phase in C4_PHASES:
        _emit("C4", check_c4_decision_log_has_phase_adr(project_root, phase))
    else:
        findings.append({
            "id": "C4", "name": f"C4 decision_log has {phase} ADR",
            "status": STATUS_SKIP,
            "evidence": f"not applicable for phase={phase}",
        })

    if phase in C5_PHASES:
        category = C5_CATEGORY.get(phase, "Added")
        _emit("C5", check_c5_changelog_unreleased_has_phase_entry(
            project_root, phase, category,
        ))
    else:
        findings.append({
            "id": "C5", "name": f"C5 CHANGELOG [Unreleased] has entry",
            "status": STATUS_SKIP,
            "evidence": f"not applicable for phase={phase}",
        })

    return findings


# ---------------------------------------------------------------------------
# Finding-dict builder — shared by phase-specific *_compliance.py wrappers
# ---------------------------------------------------------------------------

def make_finding(
    check_id: str,
    status: str,
    evidence: str,
    *,
    name: str = "",
    remediation: str = "",
    provenance: str = "",
    tier: int | None = None,
) -> dict[str, Any]:
    """Build a finding dict with Tier-2 tagging auto-applied from
    ``TIER_2_CHECK_IDS`` unless a caller supplies an explicit ``tier``.
    """
    finding: dict[str, Any] = {
        "id": check_id,
        "name": name or check_id,
        "status": status,
        "evidence": evidence,
    }
    if remediation:
        finding["remediation"] = remediation
    if provenance:
        finding["provenance"] = provenance
    effective_tier = tier if tier is not None else (2 if check_id in TIER_2_CHECK_IDS else None)
    if effective_tier is not None:
        finding["tier"] = effective_tier
    return finding


def apply_skip_override(
    finding: dict[str, Any],
    skip_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Replace a finding with a SKIP if its id is in the env-var skip list."""
    ids = skip_ids if skip_ids is not None else skipped_check_ids()
    if finding.get("id") not in ids:
        return finding
    override = override_reason() or "skipped via SHIPWRIGHT_SKIP_QUALITY_CHECK"
    new = dict(finding)
    new["status"] = STATUS_SKIP
    new["evidence"] = override
    new["provenance"] = "override"
    return new


# ---------------------------------------------------------------------------
# Workflow dispatcher — per-phase wrappers live in tools/verifiers/*_compliance
# ---------------------------------------------------------------------------

# Lazy imports to avoid circular-import pain and keep startup cost low when
# a phase has no workflow checks (e.g. project). Each wrapper module exposes
# ``run(project_root, run_id) -> list[dict]``.
_WORKFLOW_PHASE_DISPATCH: dict[str, str] = {
    "build": "build_compliance",
    "iterate": "iterate_compliance",
    "test": "test_compliance",
    "plan": "plan_compliance",
    "changelog": "changelog_compliance",
    "deploy": "deploy_compliance",
    "security": "security_compliance",
    "compliance": "compliance_compliance",
    "design": "design_compliance",
}


def run_workflow_checks(phase: str, project_root: Path, run_id: str) -> list[dict[str, Any]]:
    """Dispatch to the per-phase ``*_compliance.py`` wrapper.

    Phases without workflow checks (``project``) return an empty list. Any
    internal failure inside a wrapper is converted into a single error
    finding so the Stop hook stays non-blocking (plan § 5.5).
    """
    module_name = _WORKFLOW_PHASE_DISPATCH.get(phase)
    if not module_name:
        return []
    skip_ids = skipped_check_ids()
    try:
        import importlib
        module = importlib.import_module(f"tools.verifiers.{module_name}")
        findings = module.run(project_root, run_id)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[phase-quality] workflow wrapper {module_name} raised "
            f"{type(exc).__name__}: {exc}\n"
        )
        return [{
            "id": f"WF-{phase}",
            "name": f"workflow runner for {phase}",
            "status": STATUS_FAIL,
            "evidence": f"wrapper crashed: {type(exc).__name__}: {exc}",
            "provenance": "error",
        }]
    return [apply_skip_override(f, skip_ids) for f in findings]


def _dispatch_shared_category(
    phase: str,
    project_root: Path,
    module_name: str,
) -> list[dict[str, Any]]:
    """Shared wrapper for the Infra/Trace/Quality cross-phase modules.

    Mirrors ``run_workflow_checks``: lazy import, per-check SKIP-override,
    and try/except so a broken module surfaces as one error-finding
    rather than crashing the Stop hook (plan § 5.5).
    """
    skip_ids = skipped_check_ids()
    try:
        import importlib
        module = importlib.import_module(f"tools.verifiers.{module_name}")
        findings = module.run(phase, project_root)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[phase-quality] {module_name} raised "
            f"{type(exc).__name__}: {exc}\n"
        )
        return [{
            "id": f"{module_name.upper()[:3]}-{phase}",
            "name": f"{module_name} runner for {phase}",
            "status": STATUS_FAIL,
            "evidence": f"wrapper crashed: {type(exc).__name__}: {exc}",
            "provenance": "error",
        }]
    return [apply_skip_override(f, skip_ids) for f in findings]


def run_infrastructure_checks(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Dispatch I1-I4 per the Plugin-Coverage table (plan § 5.1).

    Phases covered: build, iterate (I1-I4); test (I2); changelog (I3).
    Other phases return an empty list — infrastructure doesn't apply.
    """
    return _dispatch_shared_category(phase, project_root, "infrastructure_checks")


def run_traceability_checks(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Dispatch T1-T2 per the Plugin-Coverage table (plan § 5.1).

    Phases covered: project, iterate. Other phases return [].
    """
    return _dispatch_shared_category(phase, project_root, "traceability_checks")


def run_quality_checks(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Dispatch Q1-Q2 per the Plugin-Coverage table (plan § 5.1).

    Phases covered: project (Q1), plan (Q1), build (Q1+Q2),
    iterate (Q1). Other phases return [].
    """
    return _dispatch_shared_category(phase, project_root, "quality_checks")


def run_spec_checks(phase: str, project_root: Path, run_id: str) -> list[dict[str, Any]]:
    del phase, project_root, run_id
    return []


# ---------------------------------------------------------------------------
# Finding JSON writer (atomic)
# ---------------------------------------------------------------------------

def write_finding_json(
    project_root: Path,
    phase: str,
    run_id: str,
    session_id: str,
    findings_by_category: dict[str, list[dict[str, Any]]],
    *,
    source: str = "standalone",
    audited_at: str | None = None,
) -> Path:
    """Write the per-run finding JSON atomically.

    Per-finding files are disjoint (one per ``(phase, run_id, session_id)``
    triple) so no lock is needed here; the lock covers only the aggregate
    rewrites (plan § 5.2).
    """
    payload: dict[str, Any] = {
        "phase": phase,
        "run_id": run_id,
        "session_id": session_id,
        "audited_at": audited_at or now_iso(),
        "source": source,
    }
    for category in CATEGORIES:
        payload[category] = list(findings_by_category.get(category, []))

    path = finding_path(project_root, phase, run_id, session_id)
    _atomic_write_json(path, payload)
    return path


def write_error_finding(
    project_root: Path,
    phase: str,
    run_id: str,
    session_id: str,
    error: BaseException,
) -> Path | None:
    """Record a hook-level failure as an error-finding so the audit trail
    doesn't silently lose the run (plan § 5.5).
    """
    try:
        path = finding_path(project_root, phase, run_id, session_id)
        payload = {
            "phase": phase,
            "run_id": run_id,
            "session_id": session_id,
            "audited_at": now_iso(),
            "source": "error",
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }
        for category in CATEGORIES:
            payload[category] = []
        _atomic_write_json(path, payload)
        return path
    except Exception:
        return None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8",
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp",
        delete=False,
    ) as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.flush()
        os.fsync(fh.fileno())
        tmp_name = fh.name
    os.replace(tmp_name, path)


# ---------------------------------------------------------------------------
# Finding loading + aggregate regeneration
# ---------------------------------------------------------------------------

@dataclass
class LoadedFinding:
    path: Path
    phase: str
    run_id: str
    session_id: str
    audited_at: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def sort_key(self) -> tuple[str, float]:
        return (self.audited_at, self.path.stat().st_mtime if self.path.exists() else 0.0)


def load_findings(project_root: Path) -> list[LoadedFinding]:
    """Load every valid Finding-JSON under ``compliance/skill-compliance``.

    Corrupt files are skipped with a stderr warning (plan § 4.13).
    """
    base = project_root / FINDING_DIR
    if not base.is_dir():
        return []
    loaded: list[LoadedFinding] = []
    for path in base.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            sys.stderr.write(
                f"[audit_phase_quality] skipping corrupt finding {path}: {exc}\n"
            )
            continue
        if not isinstance(data, dict):
            continue
        loaded.append(LoadedFinding(
            path=path,
            phase=data.get("phase") or "unknown",
            run_id=data.get("run_id") or "unknown",
            session_id=data.get("session_id") or "unknown",
            audited_at=data.get("audited_at") or "",
            source=data.get("source") or "unknown",
            payload=data,
        ))
    loaded.sort(key=lambda f: f.sort_key, reverse=True)
    return loaded


def count_by_status(findings: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_WARN: 0, STATUS_SKIP: 0}
    for item in findings:
        status = item.get("status") or STATUS_SKIP
        if status in counts:
            counts[status] += 1
    return counts


def _roll_up_counts(payload: dict[str, Any]) -> dict[str, int]:
    total = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_WARN: 0, STATUS_SKIP: 0}
    for category in CATEGORIES:
        for k, v in count_by_status(payload.get(category, [])).items():
            total[k] += v
    return total


def rewrite_aggregated_report(project_root: Path) -> Path | None:
    """Regenerate ``compliance/skill-compliance-report.md`` from the
    most-recent ``MAX_REPORT_RUNS`` finding JSONs.
    """
    findings = load_findings(project_root)[:MAX_REPORT_RUNS]
    path = project_root / REPORT_PATH
    if not findings:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Skill Compliance Report\n\n_No audits recorded yet._\n",
            encoding="utf-8",
        )
        return path

    lines = [
        "# Skill Compliance Report",
        "",
        f"_Regenerated {now_iso()} from last {len(findings)} run(s)._",
        "",
        "| Phase | Run | Audited | Source | PASS | FAIL | WARN | SKIP |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for f in findings:
        counts = _roll_up_counts(f.payload)
        lines.append(
            f"| {f.phase} | `{f.run_id}` | {f.audited_at} | {f.source} | "
            f"{counts[STATUS_PASS]} | {counts[STATUS_FAIL]} | "
            f"{counts[STATUS_WARN]} | {counts[STATUS_SKIP]} |"
        )
    lines.append("")
    for f in findings:
        lines.append(f"## {f.phase} — {f.run_id} ({f.audited_at})")
        lines.append("")
        any_emitted = False
        for category in CATEGORIES:
            items = f.payload.get(category, [])
            if not items:
                continue
            any_emitted = True
            lines.append(f"### {category}")
            for item in items:
                status = item.get("status", "?")
                check_id = item.get("id", "?")
                evidence = item.get("evidence", "")
                tier = item.get("tier")
                tier_suffix = " _(tier-2)_" if tier == 2 else ""
                lines.append(f"- **{check_id}** — {status}{tier_suffix}: {evidence}")
            lines.append("")
        if not any_emitted:
            lines.append("_No checks recorded for this run._")
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def rewrite_session_findings_summary(project_root: Path) -> Path | None:
    """Regenerate ``agent_docs/skill-compliance-findings.md`` — the
    short-form digest consumed by the future SessionStart-Injection hook
    (PR 4).
    """
    findings = load_findings(project_root)[:MAX_SESSION_SUMMARY_RUNS]
    path = project_root / SUMMARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not findings:
        path.write_text(
            "# Skill Compliance — Recent Findings\n\n_No audits recorded yet._\n",
            encoding="utf-8",
        )
        return path

    lines = [
        "# Skill Compliance — Recent Findings",
        "",
        f"_Regenerated {now_iso()} from last {len(findings)} run(s)._",
        "",
    ]
    for f in findings:
        counts = _roll_up_counts(f.payload)
        lines.append(
            f"## {f.phase} — {f.run_id}"
        )
        lines.append(
            f"- audited_at: {f.audited_at}"
        )
        lines.append(
            f"- source: {f.source}"
        )
        lines.append(
            f"- totals: {counts[STATUS_PASS]} PASS · "
            f"{counts[STATUS_FAIL]} FAIL · {counts[STATUS_WARN]} WARN · "
            f"{counts[STATUS_SKIP]} SKIP"
        )
        fails: list[dict[str, Any]] = []
        for category in CATEGORIES:
            for item in f.payload.get(category, []):
                if item.get("status") == STATUS_FAIL and item.get("tier") != 2:
                    fails.append(item)
        if fails:
            lines.append("- open FAILs:")
            for item in fails[:5]:
                lines.append(
                    f"  - **{item.get('id','?')}** {item.get('evidence','')}"
                )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_quality_dashboard_file(project_root: Path) -> Path | None:
    """Regenerate ``compliance/skill-compliance-dashboard.md``.

    Table: one row per phase, one column per category. Newest finding per
    phase wins. Heuristic (Tier-2) checks are reported as a separate
    count so reviewers can ignore low-signal noise (plan § 3).
    """
    all_findings = load_findings(project_root)
    latest_per_phase: dict[str, LoadedFinding] = {}
    for f in all_findings:
        latest_per_phase.setdefault(f.phase, f)

    path = project_root / DASHBOARD_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not latest_per_phase:
        path.write_text(
            "# Skill Compliance Dashboard\n\n_No audits recorded yet._\n",
            encoding="utf-8",
        )
        return path

    lines = [
        "# Skill Compliance Dashboard",
        "",
        f"_Regenerated {now_iso()}. Newest finding per phase._",
        "",
        "| Phase | Audited | Run | canon | workflow | infra | trace | quality | spec | Tier-2 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for phase in sorted(latest_per_phase):
        f = latest_per_phase[phase]
        cells: list[str] = []
        tier2_total = 0
        for category in CATEGORIES:
            items = f.payload.get(category, [])
            if not items:
                cells.append("—")
                continue
            counts = count_by_status(items)
            tier2_total += sum(1 for it in items if it.get("tier") == 2)
            cells.append(
                f"{counts[STATUS_PASS]}P/{counts[STATUS_FAIL]}F"
                + (f"/{counts[STATUS_WARN]}W" if counts[STATUS_WARN] else "")
            )
        lines.append(
            f"| {phase} | {f.audited_at} | `{f.run_id}` | "
            + " | ".join(cells)
            + f" | {tier2_total} |"
        )
    lines.append("")
    lines.append(
        "_Legend: `NP/NF[/NW]` = PASS / FAIL / WARN counts per category._ "
        "_Tier-2 column counts heuristic (low-signal) checks; never triggers enforcement._"
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# GC
# ---------------------------------------------------------------------------

def gc_old_findings(
    project_root: Path,
    *,
    max_age_days: int = GC_AGE_DAYS,
) -> int:
    """Move findings older than ``max_age_days`` to ``archive/``.

    Returns the number of files archived. Best-effort: failures on
    individual moves are swallowed so GC never blocks the hook.
    """
    base = project_root / FINDING_DIR
    if not base.is_dir():
        return 0
    archive = base / "archive"
    cutoff = time.time() - (max_age_days * 86400)
    moved = 0
    for path in base.glob("*.json"):
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            archive.mkdir(parents=True, exist_ok=True)
            target = archive / path.name
            try:
                os.replace(path, target)
                moved += 1
            except OSError:
                continue
        except OSError:
            continue
    return moved


# ---------------------------------------------------------------------------
# Top-level rewrite helper (locked)
# ---------------------------------------------------------------------------

def regenerate_all_aggregates(project_root: Path, *, timeout_seconds: float = 5.0) -> None:
    """Run the three aggregate rewrites under a single file lock.

    Locking only the aggregate step is intentional — per-run Finding
    JSONs are already disjoint, so contention only exists when multiple
    sessions finish at the same time and fight over the summary files
    (plan § 5.2).
    """
    lock_path = project_root / LOCK_PATH
    try:
        with file_lock(lock_path, timeout_seconds=timeout_seconds):
            rewrite_aggregated_report(project_root)
            rewrite_session_findings_summary(project_root)
            write_quality_dashboard_file(project_root)
    except LockTimeout as exc:
        sys.stderr.write(
            f"[audit_phase_quality] aggregate rewrite skipped: {exc}\n"
        )


__all__ = [
    "C4_PHASES",
    "C5_PHASES",
    "C5_CATEGORY",
    "CATEGORIES",
    "DASHBOARD_PATH",
    "FINDING_DIR",
    "LOCK_PATH",
    "MAX_REPORT_RUNS",
    "MAX_SESSION_SUMMARY_RUNS",
    "PLUGIN_TO_PHASE",
    "REPORT_PATH",
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_SKIP",
    "STATUS_WARN",
    "SUMMARY_PATH",
    "TIER_2_CHECK_IDS",
    "LoadedFinding",
    "already_audited",
    "apply_skip_override",
    "count_by_status",
    "finding_path",
    "flag_enabled",
    "gc_old_findings",
    "is_shipwright_project",
    "load_findings",
    "make_finding",
    "phase_from_plugin_root",
    "phase_quality_enabled",
    "regenerate_all_aggregates",
    "resolve_run_id",
    "resolve_source",
    "rewrite_aggregated_report",
    "rewrite_session_findings_summary",
    "run_canon_checks",
    "run_infrastructure_checks",
    "run_quality_checks",
    "run_spec_checks",
    "run_traceability_checks",
    "run_workflow_checks",
    "skipped_check_ids",
    "write_error_finding",
    "write_finding_json",
    "write_quality_dashboard_file",
]
