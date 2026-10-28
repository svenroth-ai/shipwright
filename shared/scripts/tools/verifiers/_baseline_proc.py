"""Process helpers shared by the baseline measurement tooling (BP unit BL0): a scrubbed environment and
the scratch-directory guard. Kept apart so the replay and the measurement modules need not import each other."""

from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = ["clean_env", "guard_workdir"]

_SECRET = re.compile(r"TOKEN|SECRET|KEY|PASSWORD|^CI$|^GITHUB_", re.I)


def clean_env(venv: str | Path | None = None) -> dict[str, str]:
    """The process environment without anything credential-shaped (a context run executes the repo's own tests)."""
    env = {k: v for k, v in os.environ.items() if not _SECRET.search(k)}
    if venv:
        env["UV_PROJECT_ENVIRONMENT"] = str(venv)
    return env


def guard_workdir(repo: str | Path, workdir: str | Path) -> None:
    """Scratch worktrees and databases must live OUTSIDE the repository they are made from."""
    repo_p, work_p = Path(repo).resolve(), Path(workdir).resolve()
    if repo_p == work_p or repo_p in work_p.parents:
        raise ValueError("workdir must be outside the repository")
