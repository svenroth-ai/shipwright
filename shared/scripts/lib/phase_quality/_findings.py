"""Finding-JSON schema + builders + atomic writer.

Single owner of the on-disk Finding-JSON shape:

    {"phase", "run_id", "session_id", "audited_at", "source",
     "canon": [...], "workflow": [...], ...}

* :func:`make_finding` — top-level builder used by per-phase wrappers.
* :func:`apply_skip_override` — env-var SKIP override surface.
* :func:`_check_result_to_finding` — adapts ``CheckResult`` (from
  ``tools/verifiers/common.py``) into the finding-dict shape.
* :func:`write_finding_json` / :func:`write_error_finding` — atomic
  tmp+rename writer.
* :func:`already_audited` — idempotency guard (plan § 5.4).

Iterate Campaign B (B3): split out of the 1108-LOC monolith.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from tools.verifiers.common import CheckResult, Severity  # noqa: E402

from ._constants import (
    CATEGORIES,
    FINDING_DIR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    TIER_2_CHECK_IDS,
)
from ._flags import override_reason, skipped_check_ids


# ---------------------------------------------------------------------------
# Path / filename helpers
# ---------------------------------------------------------------------------

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
# Finding builders — shared by phase-specific *_compliance.py wrappers
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
# Atomic JSON writer
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as JSON durably (tmp + fsync + os.replace via the shared
    :func:`durable_atomic_write`)."""
    durable_atomic_write(path, json.dumps(payload, indent=2, sort_keys=False))


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


__all__ = [
    "_atomic_write_json",
    "_check_result_to_finding",
    "_status_for",
    "already_audited",
    "apply_skip_override",
    "finding_filename",
    "finding_path",
    "make_finding",
    "now_iso",
    "write_error_finding",
    "write_finding_json",
]
