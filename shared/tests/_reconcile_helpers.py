"""Shared helpers for the ``reconcile_main_triage`` test modules.

Not a test file (leading underscore → pytest does not collect it). Holds the
git/triage fixtures-on-disk plumbing so the three ``test_reconcile_triage*``
modules each stay under the 300-LOC guideline without duplicating it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

TRIAGE = ".shipwright/triage.jsonl"
HEADER = '{"v":1,"schema":"triage","created":"2026-06-01T00:00:00Z"}'


def env() -> dict[str, str]:
    e = os.environ.copy()
    e.update(
        GIT_AUTHOR_NAME="Reconcile Test",
        GIT_AUTHOR_EMAIL="reconcile@test.invalid",
        GIT_COMMITTER_NAME="Reconcile Test",
        GIT_COMMITTER_EMAIL="reconcile@test.invalid",
    )
    return e


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # encoding="utf-8" so `git show` of a UTF-8 triage line round-trips on a
    # Windows runner instead of mojibake-decoding via the cp1252 locale default.
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env(),
        capture_output=True, text=True, encoding="utf-8", check=check,
    )


def set_identity(work: Path) -> None:
    git(work, "config", "user.email", "reconcile@test.invalid")
    git(work, "config", "user.name", "Reconcile Test")


def append(root: Path, *lines: str) -> None:
    p = root / TRIAGE
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")


def item(iid: str, title: str = "x") -> str:
    return f'{{"event":"append","id":"{iid}","title":"{title}","status":"triage"}}'


def seed_tracked_triage(work: Path, *items: str, push: bool = True) -> None:
    """Commit a triage.jsonl (header + items) + the union .gitattributes."""
    (work / ".shipwright").mkdir(exist_ok=True)
    body = "\n".join([HEADER, *items]) + "\n"
    (work / TRIAGE).write_text(body, encoding="utf-8")
    (work / ".gitattributes").write_text(f"{TRIAGE} merge=union\n", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-m", "seed triage")
    if push:
        git(work, "push", "origin", "main")


def head_count(work: Path) -> int:
    return int(git(work, "rev-list", "--count", "HEAD").stdout.strip())
