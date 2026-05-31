#!/usr/bin/env python3
"""Stop hook: compliance detective-audit triage emit/dismiss.

Closes the gap where ``source=compliance`` triage items (F2/F4/F5/F6/F7,
B-group, etc.) stayed in ``status=triage`` until someone manually ran
``/shipwright-compliance`` — ``audit_detector.mirror_findings_to_triage``
(the auto-dismiss-when-finding-cleared path) had no automatic trigger
while every other triage producer did (Option A1, 2026-05-23 design).

Stop contract (mirrors ``audit_phase_quality_on_stop.py``):

- **Never blocks** — always exits 0, even on internal error.
- **Idempotent per (HEAD-sha, session_id)** — re-running on the same
  commit in the same session is a no-op (marker under the gitignored
  ``.shipwright/agent_docs/runtime/`` tree).
- **Greenfield-safe** — silent no-op off a Shipwright-managed project.
- **Disabled when** ``SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP=0``.

CRITICAL SAFETY GATE — full-coverage-before-dismiss: ``mirror_findings_to_triage``
auto-dismisses any currently-``triage`` compliance item whose ``check_id``
is absent from THIS run's failures. The dismiss is *groupless*: a
crashed/skipped group's findings vanish and its triage items would be
wrongly dismissed (running only group F would dismiss B7/B2). So we run
the FULL audit (groups A-G) with ``emit_to_triage=False``, verify every
group ran (no ``import_gate_error``), and ONLY THEN mirror. Partial
coverage → skip mirroring (never a false dismiss) + stderr diagnostic.
Strictly safer than ``run_audit.py``'s unconditional emit.

Wire AFTER finalize + phase_quality and BEFORE ``aggregate_triage_on_stop``:

    uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/audit_compliance_on_stop.py"
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import phase_quality as pq  # noqa: E402
from lib.artifact_paths import runtime_dir  # noqa: E402
from lib.project_root import resolve_project_root  # noqa: E402

_DISABLE_ENV = "SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP"
_EXPECTED_GROUPS = frozenset({"A", "B", "C", "D", "E", "F", "G"})
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp", delete=False,
    ) as fh:
        tmp = Path(fh.name)
        json.dump(payload, fh, indent=2)
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)


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


def _load_audit_api() -> tuple[Callable | None, Callable | None, Callable | None]:
    """Import (register_all, run_all, mirror_findings_to_triage).

    Returns ``(None, None, None)`` on any import failure — the audit chain
    is first-party + stdlib, so this only trips on a broken install, in
    which case the hook no-ops (never blocks).
    """
    plugin_root = _ROOT_FROM_SHARED / "plugins" / "shipwright-compliance"
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))
    try:
        from scripts.audit._registry import register_all  # noqa: PLC0415
        from scripts.audit.audit_detector import (  # noqa: PLC0415
            mirror_findings_to_triage,
            run_all,
        )
        return register_all, run_all, mirror_findings_to_triage
    except Exception:  # noqa: BLE001
        return None, None, None


def coverage_ok(report: Any) -> tuple[bool, str]:
    """Whether ``report`` is safe to mirror: import gate passed AND all A-G ran.

    Anything less means findings are missing and mirroring would wrongly
    auto-dismiss the missing groups' triage items.
    """
    gate_err = getattr(report, "import_gate_error", None)
    if gate_err:
        return False, f"import_gate_error: {gate_err}"
    ran = {str(g).upper() for g in getattr(report, "groups_run", [])}
    missing = sorted(_EXPECTED_GROUPS - ran)
    if missing:
        return False, (
            f"incomplete coverage; missing={missing} "
            f"skipped={getattr(report, 'groups_skipped', [])}"
        )
    return True, "full coverage A-G"


def emit_if_full_coverage(
    project_root: Path, report: Any, *,
    run_id: str | None, commit: str | None,
    mirror_fn: Callable[..., dict[str, int]],
) -> dict[str, Any]:
    """Apply the safety gate, then mirror only on full coverage.

    ``mirror_fn`` is injected for testability. Returns a telemetry dict.
    """
    ok, reason = coverage_ok(report)
    if not ok:
        return {"mirrored": False, "reason": reason}
    try:
        stats = mirror_fn(project_root, report, run_id=run_id, commit=commit)
    except Exception as exc:  # noqa: BLE001 — never block on triage failure
        return {"mirrored": False, "reason": f"mirror error: {type(exc).__name__}: {exc}"}
    return {"mirrored": True, "reason": reason, **(stats or {})}


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


def _resolve_project_root() -> Path:
    try:
        return resolve_project_root()
    except Exception:  # noqa: BLE001
        return Path.cwd()


def main() -> int:
    _consume_stdin()

    if not audit_on_stop_enabled():
        return 0
    if pq.phase_from_plugin_root(os.environ.get("CLAUDE_PLUGIN_ROOT", "")) is None:
        return 0  # non-Shipwright plugin — silent no-op

    project_root = _resolve_project_root()
    if not pq.is_shipwright_project(project_root):
        return 0

    # Monorepo auto-descent guard (matches phase_quality).
    if pq.cwd_is_strict_ancestor_of(Path.cwd(), project_root) \
            and not pq.project_root_was_explicitly_selected(project_root):
        return 0

    session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "").strip() or "unknown"
    head_sha = _git_head_sha(project_root)

    if already_audited(project_root, head_sha, session_id):
        _diag(f"[compliance-audit] already audited sha={head_sha[:8] or 'nogit'} "
              f"session={session_id} — skipped")
        return 0

    register_all, run_all, mirror = _load_audit_api()
    if not (register_all and run_all and mirror):
        _diag("[compliance-audit] audit API unavailable — skipped (no-op)")
        return 0

    run_id = pq.resolve_run_id(project_root, session_id)
    started = time.monotonic()
    try:
        register_all()
        # emit_to_triage=False: interpose the full-coverage gate between
        # detection and the triage mirror (see module docstring).
        report = run_all(project_root, emit_to_triage=False, run_gate=True,
                         run_id=run_id, commit=head_sha)
        result = emit_if_full_coverage(
            project_root, report, run_id=run_id, commit=head_sha, mirror_fn=mirror)
        _write_marker(project_root, head_sha, session_id, {
            "head_sha": head_sha, "session_id": session_id, "run_id": run_id,
            "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "groups_run": sorted(str(g).upper() for g in report.groups_run),
            "result": result,
        })
        ms = int((time.monotonic() - started) * 1000)
        if result.get("mirrored"):
            _diag(f"[compliance-audit] sha={head_sha[:8] or 'nogit'} "
                  f"appended={result.get('appended', 0)} "
                  f"dismissed={result.get('dismissed', 0)} ({ms}ms)")
        else:
            _diag(f"[compliance-audit] NOT mirrored ({result.get('reason')}) "
                  f"({ms}ms) — triage left untouched")
    except Exception as exc:  # noqa: BLE001 — never block the Stop chain
        _diag(f"[compliance-audit] error: {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
