"""Shared real-git plumbing for the ``test_sweep_outbox*`` modules (D2).

Not a test file (leading underscore → pytest does not collect it). Holds the
git/worktree/outbox fixtures-on-disk plumbing so the two ``test_sweep_outbox*``
modules each stay under the 300-LOC guideline without duplicating it. Mirrors
the ``_reconcile_helpers.py`` pattern. EVERYTHING here uses REAL git — the sweep
is the most data-loss-sensitive unit in the campaign, so nothing is mocked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

TRIAGE = ".shipwright/triage.jsonl"
OUTBOX = ".shipwright/triage.outbox.jsonl"
HEADER = '{"v":1,"schema":"triage","created":"2026-06-08T00:00:00Z"}'


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, encoding="utf-8", check=check,
    )


def set_identity(work: Path) -> None:
    git(work, "config", "user.email", "sweep@test.invalid")
    git(work, "config", "user.name", "Sweep Test")


def item(iid: str, title: str = "x") -> str:
    return (
        f'{{"event":"append","id":"{iid}","ts":"2026-06-08T00:00:00Z",'
        f'"title":"{title}","status":"triage"}}'
    )


def seed_tracked(work: Path, *items: str) -> None:
    """Commit a tracked triage.jsonl (header + items) + the union .gitattributes
    + a .gitignore for the outbox on ``main``, push to origin, set origin/HEAD."""
    (work / ".shipwright").mkdir(parents=True, exist_ok=True)
    body = "\n".join([HEADER, *items]) + "\n"
    (work / TRIAGE).write_text(body, encoding="utf-8", newline="\n")
    (work / ".gitattributes").write_text(f"{TRIAGE} merge=union\n", encoding="utf-8", newline="\n")
    (work / ".gitignore").write_text(f"{OUTBOX}\n", encoding="utf-8", newline="\n")
    git(work, "add", "--", TRIAGE, ".gitattributes", ".gitignore")
    git(work, "commit", "-m", "seed triage")
    git(work, "push", "origin", "main")
    git(work, "remote", "set-head", "origin", "main")


def write_outbox(work: Path, *lines: str) -> None:
    p = work / OUTBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")


def make_worktree(work: Path, slug: str) -> Path:
    wt = work / ".worktrees" / slug
    git(work, "worktree", "add", str(wt), "-b", f"iterate/{slug}", "main")
    return wt


def branch_triage_lines(wt: Path) -> set[str]:
    """Committed triage lines on the worktree branch HEAD (stripped, non-blank)."""
    proc = git(wt, "show", f"HEAD:{TRIAGE}", check=False)
    if proc.returncode != 0:
        return set()
    return {ln.strip() for ln in proc.stdout.split("\n") if ln.strip()}


def outbox_lines(work: Path) -> set[str]:
    p = work / OUTBOX
    if not p.exists():
        return set()
    return {ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()}
