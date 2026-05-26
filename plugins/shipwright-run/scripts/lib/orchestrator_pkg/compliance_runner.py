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

    try:
        result = subprocess.run(
            [sys.executable, str(compliance_script),
             "--project-root", str(project_root),
             "--phase", phase],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
            cwd=str(project_root),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        # Non-zero exit or empty stdout — log for diagnostics
        sys.stderr.write(json.dumps({
            "level": "warn",
            "message": f"Compliance update failed for phase '{phase}'",
            "returncode": result.returncode,
            "stderr": (result.stderr or "")[:500],
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
