"""Compliance-update subprocess wrapper for the orchestrator package.

After a phase completes, the orchestrator delegates to
``plugins/shipwright-compliance/scripts/tools/update_compliance.py`` for
the incremental RTM/SBOM refresh. This module is the thin
subprocess/JSON shim.

Tests patch ``orchestrator._COMPLIANCE_SCRIPT`` and
``orchestrator._record_compliance_update_failed`` to assert on the
fail-path. To honor those patches after the B5 split, ``run_compliance_update``
goes through the ``orchestrator`` shim module via a late ``sys.modules``
lookup for those two names.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Inner timeout for the compliance update subprocess. The Stop-fallback that
# spawns ``orchestrator update-step`` (generate_handoff_on_stop) MUST allow
# STRICTLY more than this, or the orchestrator is killed mid-write before
# ``save_run_config`` runs and the phase is never marked complete
# (audit WP2/F13). Enforced by test_runconfig_timeout_invariant.py. Headroom
# above 30s: since this launches `uv run --project <compliance_plugin>`
# rather than `sys.executable`, a first-ever sync of that plugin's venv may
# need to resolve/install jsonschema/pyyaml, which the old call never did.
COMPLIANCE_SUBPROCESS_TIMEOUT_SECONDS = 60


def _generator_error_detail(result: subprocess.CompletedProcess) -> str:
    """Best diagnostic for a non-zero ``update_compliance.py`` exit.

    On a generator-error exit it writes ``{"success": false, "generator_errors":
    [...]}`` to STDOUT and leaves stderr EMPTY (the failure is a caught exception
    turned into structured JSON, never a traceback) — the reverse of where a
    caller looks by default. Prefer that structured detail; fall back to stderr
    for any other failure (missing script, uv/venv error, timeout).
    """
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        payload = None
    errors = payload.get("generator_errors") if isinstance(payload, dict) else None
    valid = [e for e in errors if isinstance(e, dict)] if isinstance(errors, list) else []
    if valid:
        return "; ".join(
            f"{e.get('report')}: {e.get('error')}: {e.get('detail')}" for e in valid
        )
    return (result.stderr or "")[:500]


def _shim():
    """Return the imported ``orchestrator`` shim if present, else None.

    Late lookup so test patches on ``orchestrator._COMPLIANCE_SCRIPT`` /
    ``orchestrator._record_compliance_update_failed`` are respected.
    """
    return sys.modules.get("orchestrator")


def run_compliance_update(project_root: Path, phase: str) -> dict[str, Any] | None:
    """Run incremental compliance update after a phase completes.

    Returns parsed JSON output on success, None if compliance plugin not found
    or on error (non-blocking).
    """
    shim = _shim()
    if shim is not None:
        compliance_script = shim._COMPLIANCE_SCRIPT
        record_failed = shim._record_compliance_update_failed
    else:
        from .constants import _COMPLIANCE_SCRIPT
        from .events import _record_compliance_update_failed
        compliance_script = _COMPLIANCE_SCRIPT
        record_failed = _record_compliance_update_failed

    if not compliance_script.exists():
        # Loud-fail (plan v7). Historically this branch returned None
        # silently, which hid missing-plugin installs from users.
        sys.stderr.write(json.dumps({
            "level": "warn",
            "message": "compliance update script missing",
            "path": str(compliance_script),
            "phase": phase,
        }) + "\n")
        record_failed(project_root, phase, reason="script_missing")
        return None

    # `uv run --project`, not `sys.executable`: `update_compliance.py` needs
    # jsonschema/pyyaml, declared only in the compliance plugin's own
    # pyproject.toml. `sys.executable` is the orchestrator's own venv, which
    # carries neither — cross-plugin ModuleNotFoundError otherwise (same
    # class of bug as finalize_iterate.py._update_compliance). `compliance_script`
    # is `<compliance_plugin>/scripts/tools/update_compliance.py`.
    compliance_plugin = compliance_script.parents[2]
    try:
        result = subprocess.run(
            ["uv", "run", "--project", str(compliance_plugin), "python",
             str(compliance_script),
             "--project-root", str(project_root),
             "--phase", phase],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=COMPLIANCE_SUBPROCESS_TIMEOUT_SECONDS,
            cwd=str(project_root),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        # Non-zero exit or empty stdout — log for diagnostics
        sys.stderr.write(json.dumps({
            "level": "warn",
            "message": f"Compliance update failed for phase '{phase}'",
            "returncode": result.returncode,
            # May be parsed from stdout (generator_errors) rather than the
            # process's actual stderr — see _generator_error_detail.
            "detail": _generator_error_detail(result),
        }) + "\n")
        record_failed(
            project_root, phase,
            reason=f"subprocess_exit_{result.returncode}",
        )
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(json.dumps({
            "level": "warn",
            "message": f"Compliance update error for phase '{phase}'",
            "error": str(exc),
        }) + "\n")
        record_failed(
            project_root, phase, reason=f"subprocess_error:{type(exc).__name__}",
        )
    return None
