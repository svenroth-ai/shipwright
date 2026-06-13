"""Generic git-invocation helpers shared across iterate verifier modules.

Extracted from ``iterate_checks.py``
(iterate-2026-06-13-risk-detector-extract) so the integration-coverage gate
(``integration_coverage.py``) and the iterate finalization checks
(``iterate_checks.py``) share ONE copy instead of duplicating the wrappers or
forcing a circular import. All functions are read-only and never raise.
"""

from __future__ import annotations

from pathlib import Path


def _run_git(
    project_root: Path, *args: str, timeout: float | None = None,
) -> tuple[int, str, str]:
    """Run ``git -C <project_root> <args>``; never raises. Returns (rc, out, err).

    ``timeout`` (seconds) is passed through to ``subprocess.run`` only when
    set; the default ``None`` preserves the original no-timeout behaviour for
    existing callers. On any failure (git missing, bad args, or — when a
    timeout is set — the command exceeding it) returns ``(1, "", "")`` so
    callers can branch on ``rc != 0`` / ``rc == 0`` uniformly.
    """
    import subprocess
    # Pass ``timeout`` to subprocess.run only when the caller set it, so an
    # un-timed call keeps the exact kwarg shape it had before this param existed.
    kwargs: dict = {"capture_output": True, "text": True,
                    "encoding": "utf-8", "errors": "ignore"}
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        proc = subprocess.run(["git", "-C", str(project_root), *args], **kwargs)
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 1, "", ""


def _git_available(project_root: Path, timeout: float | None = 10.0) -> bool:
    # ``rev-parse --is-inside-work-tree`` is a trivial metadata read; bound it
    # (default 10s) so a wedged ``index.lock`` / stalled filesystem cannot hang a
    # verifier indefinitely. spec_checks bounded this probe at 10s before its
    # wrappers were folded onto this module (iterate-2026-06-13-shc-git-helpers);
    # the bound now also covers the integration_coverage / iterate_checks callers.
    rc, _, _ = _run_git(
        project_root, "rev-parse", "--is-inside-work-tree", timeout=timeout
    )
    return rc == 0


def _commit_changed_paths(project_root: Path, commit: str) -> list[str] | None:
    """Return the repo-relative paths a commit touched, or None on git failure."""
    rc, out, _ = _run_git(
        project_root, "show", "--name-only", "--pretty=format:", commit
    )
    if rc != 0:
        return None
    return [ln.strip() for ln in out.splitlines() if ln.strip()]
