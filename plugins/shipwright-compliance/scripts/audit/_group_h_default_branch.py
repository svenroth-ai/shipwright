"""H2 support — default-branch LOC lookup (webui incident 2026-09-09).

Split out of ``group_h.py`` to keep it under the 300-LOC guideline.

PRs #450/#453/#456: a Group-H2 suggestion tightened
``shipwright_bloat_baseline.json`` to a value measured on ONE tree at ONE
instant. A concurrent, already-in-flight branch landed the same file bigger,
and after both merged trunk's own anti-ratchet broke on a zero-diff PR. H2
must not suggest a tightening the shared trunk itself already exceeds.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.audit.audit_adapters import load_shared_lib

_branch_base = load_shared_lib("branch_base")


def default_branch_lines(project_root: Path, rel_path: str) -> int | None:
    """LOC of ``rel_path`` on ``origin/<default>``, or ``None`` when it
    cannot be determined (no repo, no such remote ref, path absent there).

    ``None`` means "unknown" — callers must not treat it as zero. This is
    what keeps a bare-directory fixture (no ``.git`` at all) behaving
    exactly as before this check was added.
    """
    try:
        default_branch = _branch_base.resolve_default_branch()
        result = subprocess.run(
            ["git", "-C", str(project_root), "show",
             f"origin/{default_branch}:{rel_path}"],
            capture_output=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.count(b"\n")
