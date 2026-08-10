#!/usr/bin/env python3
"""Stop hook: branch-local compliance detective-audit diagnostics.

The hook runs the full A-I audit on the resolved active worktree and reports findings
to that run, but never calls the triage mirror. Delivery and release invoke the
lifecycle tool with their separate authority and coverage contracts.

Stop contract:

- **Never blocks** — always exits 0, even on internal error.
- **Idempotent per (HEAD-sha, session_id)** — re-running on the same
  commit in the same session is a no-op (marker under the gitignored
  `.shipwright/agent_docs/runtime/` tree).
- **Greenfield-safe** — silent no-op off a Shipwright-managed project.
- **Disabled when** `SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP=0`.

The full A-I report remains visible as local diagnostics even when Group E contains
expected pending-release drift. Its marker carries coverage data for operator inspection;
it is never a backlog write.

Wire AFTER finalize + phase_quality and BEFORE `aggregate_triage_on_stop`:

    uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/audit_compliance_on_stop.py"
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import phase_quality as pq  # noqa: E402
from lib.artifact_paths import runtime_dir  # noqa: E402
from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.compliance_lifecycle import coverage_for  # noqa: E402

_DISABLE_ENV = "SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP"
_MARKER_SUBDIR = "compliance_audit"
_ROOT_FROM_SHARED = _SCRIPTS_ROOT.parent.parent  # repo root OR cache/shipwright


def audit_on_stop_enabled() -> bool:
    """Default ON; ``SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP=0`` is the rollback lever."""
    raw = os.environ.get(_DISABLE_ENV, "").strip().lower()
    return True if not raw else raw not in ("0", "false", "no", "off")


def _sanitize(token: str) -> str:
    return "".join(c if (c.isalnum() or c in "._-") else "-" for c in token) or "unknown"


def _marker_path(project_root: Path, head_sha: str, session_id: str) -> Path:
    sha = (head_sha or "nogit")[:40]
    return runtime_dir(project_root) / _MARKER_SUBDIR / f"{sha}-{_sanitize(session_id)}.json"


def already_audited(project_root: Path, head_sha: str, session_id: str) -> bool:
    """True when a valid marker exists for (sha, session). Corrupt → re-run."""
    path = _marker_path(project_root, head_sha, session_id)
    if not path.exists():
        return False
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return True


def _write_marker(project_root: Path, head_sha: str, session_id: str,
                  payload: dict[str, Any]) -> None:
    path = _marker_path(project_root, head_sha, session_id)
    durable_atomic_write(path, json.dumps(payload, indent=2))


def _git_head_sha(project_root: Path) -> str:
    """Current HEAD sha; ``""`` on any failure (dirty-tree safe)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root), capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _load_audit_api() -> tuple[Callable | None, Callable | None]:
    """Import (register_all, run_all). Branch feedback never mirrors, so the
    hook has no need of ``mirror_findings_to_triage`` at all.

    Returns ``(None, None)`` on any import failure — the audit chain is
    first-party + stdlib, so this only trips on a broken install, in which
    case the hook no-ops (never blocks). Also returns ``(None, None)`` if the
    imported ``run_all`` still carries the pre-P2.59 ``emit_to_triage``
    parameter: this hook and the compliance plugin sync independently
    (CLAUDE.md's plugin-cache-skew problem class), so a partial sync could
    otherwise pair this hook's bare ``run_all(project_root, run_gate=True)``
    call with a stale detector whose ``emit_to_triage`` default is ``True`` —
    mirroring into the branch's tracked backlog from branch feedback, exactly
    the authority split this file exists to prevent.
    """
    plugin_root = _ROOT_FROM_SHARED / "plugins" / "shipwright-compliance"
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))
    try:
        from scripts.audit._registry import register_all  # noqa: PLC0415
        from scripts.audit.audit_detector import run_all  # noqa: PLC0415
        if "emit_to_triage" in inspect.signature(run_all).parameters:
            return None, None
        return register_all, run_all
    except Exception:  # noqa: BLE001
        return None, None


def _consume_stdin() -> None:
    try:
        json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        pass


def _diag(message: str) -> None:
    try:
        sys.stderr.write(f"{message}\n")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    _consume_stdin()

    if not audit_on_stop_enabled():
        return 0
    if pq.phase_from_plugin_root(os.environ.get("CLAUDE_PLUGIN_ROOT", "")) is None:
        return 0  # non-Shipwright plugin — silent no-op

    session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "").strip() or "unknown"
    cwd = Path.cwd()
    # `resolve_project_roots` is the shared contract the sibling
    # `audit_phase_quality_on_stop.py` uses: SHIPWRIGHT_PROJECT_ROOT wins
    # first (an explicit opt-in must not be silently outranked by a pointer
    # redirect), and `plain_root` — never `project_root` — is what the
    # greenfield/auto-descent guards below check, since a fresh linked
    # worktree can lack the markers `plain_root` was built to detect.
    project_root, pointer_redirected, plain_root = pq.resolve_project_roots(cwd, session_id)
    if not pq.is_shipwright_project(plain_root):
        return 0

    # A verified pointer deliberately redirects from main into a linked
    # worktree. It is not unsafe auto-descent, so it must bypass this guard.
    if pq.cwd_is_strict_ancestor_of(cwd, project_root) \
            and not (pq.project_root_was_explicitly_selected(project_root) or pointer_redirected):
        return 0

    head_sha = _git_head_sha(project_root)

    if already_audited(project_root, head_sha, session_id):
        _diag(f"[compliance-audit] already audited sha={head_sha[:8] or 'nogit'} "
              f"session={session_id} — skipped")
        return 0

    register_all, run_all = _load_audit_api()
    if not (register_all and run_all):
        _diag("[compliance-audit] audit API unavailable — skipped (no-op)")
        return 0

    run_id = pq.resolve_run_id(project_root, session_id)
    started = time.monotonic()
    try:
        register_all()
        # Detection has no triage write path; this hook records only local diagnostics.
        report = run_all(project_root, run_gate=True)
        coverage = coverage_for(report, "branch_feedback")
        result = {
            "mirrored": False,
            "reason": "branch_feedback: local diagnostics only",
            "coverage": coverage.to_dict(),
            "local_failures": [f"{f.group}/{f.check_id}" for f in getattr(report, "findings", ()) if f.status == "fail"],
        }
        _write_marker(project_root, head_sha, session_id, {
            "head_sha": head_sha, "session_id": session_id, "run_id": run_id,
            "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "groups_run": sorted(str(g).upper() for g in report.groups_run),
            "result": result,
        })
        ms = int((time.monotonic() - started) * 1000)
        local = ", ".join(result["local_failures"]) or "none"
        _diag(f"[compliance-audit] local findings={local}; "
              f"NOT mirrored ({result['reason']}) ({ms}ms) — global triage left untouched")
    except Exception as exc:  # noqa: BLE001 — never block the Stop chain
        _diag(f"[compliance-audit] error: {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
