"""Merge-authority compliance audit spawned by `deliver_pr.py` on DELIVERED
(P2.59, branch-feedback authority). Best-effort — never raises."""

from __future__ import annotations

import sys
from pathlib import Path

from lib.compliance_audit_spawn import spawn_compliance_audit


def run_merge_compliance_audit(scripts_root: Path, project_root: Path, run_id: str,
                               pr: str, repo: str) -> dict:
    lifecycle = scripts_root / "tools" / "audit_compliance_lifecycle.py"
    # `uv run --with pyyaml` here, not `sys.executable`: the audit needs its own
    # dependency-controlled environment regardless of what interpreter spawned
    # this call — matching the Stop hook's `uv run --with pyyaml` invocation.
    result = spawn_compliance_audit(
        ["uv", "run", "--with", "pyyaml", str(lifecycle), "--scope", "merge",
         "--project-root", str(project_root), "--run-id", run_id, "--pr", pr, "--repo", repo],
    )
    if not result["ran"]:
        sys.stderr.write(f"[compliance] merge audit did not complete: {result['detail']}\n")
    return result
