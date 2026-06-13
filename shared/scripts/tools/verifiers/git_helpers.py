"""Generic git-invocation helpers shared across iterate verifier modules.

Extracted from ``iterate_checks.py``
(iterate-2026-06-13-risk-detector-extract) so the integration-coverage gate
(``integration_coverage.py``) and the iterate finalization checks
(``iterate_checks.py``) share ONE copy instead of duplicating the wrappers or
forcing a circular import. All functions are read-only and never raise.
"""

from __future__ import annotations

from pathlib import Path


def _run_git(project_root: Path, *args: str) -> tuple[int, str, str]:
    """Run ``git -C <project_root> <args>``; never raises. Returns (rc, out, err)."""
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), *args],
            capture_output=True, text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, ValueError):
        return 1, "", ""


def _git_available(project_root: Path) -> bool:
    rc, _, _ = _run_git(project_root, "rev-parse", "--is-inside-work-tree")
    return rc == 0


def _commit_changed_paths(project_root: Path, commit: str) -> list[str] | None:
    """Return the repo-relative paths a commit touched, or None on git failure."""
    rc, out, _ = _run_git(
        project_root, "show", "--name-only", "--pretty=format:", commit
    )
    if rc != 0:
        return None
    return [ln.strip() for ln in out.splitlines() if ln.strip()]
