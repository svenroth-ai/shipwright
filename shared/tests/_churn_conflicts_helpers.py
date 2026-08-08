"""Shared real-git plumbing for the ``test_resolve_churn_conflicts*`` modules.

Not a test file (leading underscore -> pytest does not collect it), mirroring
the ``_sweep_helpers.py`` / ``_reconcile_helpers.py`` convention. Split out of
``test_resolve_churn_conflicts.py`` when that file crossed the 300-LOC
guideline (iterate-2026-08-08-triage-amend-event added an orphan-amend test).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

TRIAGE_HEADER = '{"v":1,"schema":"triage","created":"2026-06-05T00:00:00Z"}'


def env() -> dict[str, str]:
    e = os.environ.copy()
    e.update(
        GIT_AUTHOR_NAME="Churn Test",
        GIT_AUTHOR_EMAIL="churn@test.invalid",
        GIT_COMMITTER_NAME="Churn Test",
        GIT_COMMITTER_EMAIL="churn@test.invalid",
    )
    return e


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env(), capture_output=True, text=True, check=check
    )


def make_conflict_repo(root: Path, files: dict[str, tuple[str, str, str]]) -> subprocess.CompletedProcess[str]:
    """``files``: relpath -> (base, ours, theirs). Returns the (conflicting) merge."""
    git(root, "init", "-b", "main")
    for rel, (base, _o, _t) in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(base, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-m", "base")
    git(root, "checkout", "-b", "theirs")
    for rel, (_b, _o, theirs) in files.items():
        (root / rel).write_text(theirs, encoding="utf-8")
    git(root, "commit", "-am", "theirs")
    git(root, "checkout", "main")
    git(root, "checkout", "-b", "ours")
    for rel, (_b, ours, _t) in files.items():
        (root / rel).write_text(ours, encoding="utf-8")
    git(root, "commit", "-am", "ours")
    return git(root, "merge", "theirs", "-m", "merge theirs", check=False)
