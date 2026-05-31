#!/usr/bin/env python3
"""Commit ``shipwright_events.jsonl`` as a follow-up commit when it is tracked.

The iterate skill's F7 step (``record_event.py``) appends to the event log
after F6 has already committed. SKILL.md historically documented F7 as
"writes only to a gitignored event log" — that assumption only holds when
``shipwright_events.jsonl`` is git-ignored. In repos that track it (notably
the shipwright dev repo itself — ``.gitignore`` line 70:
``!/shipwright_events.jsonl``), the F7 append leaves a tracked-dirty file
that the next ``git reset --hard`` / ``git stash`` / rebase wipes silently.

This tool runs immediately after ``record_event.py`` and, when the event log
is tracked AND dirty, produces a small follow-up commit. Idempotent:

- events.jsonl gitignored             → noop (status: ``ignored``)
- events.jsonl tracked but not dirty  → noop (status: ``clean``)
- events.jsonl untracked              → noop (status: ``untracked``)
- events.jsonl tracked + dirty        → commit + return status ``committed``

CLI:
    uv run shared/scripts/tools/commit_event_followup.py \\
        --project-root . \\
        --run-id iterate-2026-05-23-foo \\
        [--event-id evt-12345678]      # optional, embedded in commit body
        [--co-author "Claude <noreply@anthropic.com>"]
        [--dry-run]

Exit codes:
    0 — any outcome (noop or committed); details on stdout as JSON
    1 — unexpected git failure / bad arguments
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

EVENT_FILE = "shipwright_events.jsonl"


def _run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run ``git`` with the given args under ``cwd``. Returns the completed
    process. When ``check`` is True, raises on non-zero exit."""
    return subprocess.run(  # noqa: S603 — args is a hardcoded list, cwd is validated
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=check,
        encoding="utf-8",
    )


def resolve_main_repo_root(project_root: Path) -> Path:
    """Return the main-repo root for ``project_root``.

    Mirrors record_event.py's ``resolve_events_path`` semantics: when
    ``project_root`` is inside a linked git worktree, the canonical event log
    lives next to the **main** repo (where ``record_event.py`` writes it).
    The F7b commit must target the same repo or it will check a different
    events.jsonl and report ``clean`` even when the real log is dirty.

    Resolves via ``git rev-parse --git-common-dir`` and returns its parent.
    Falls back to ``project_root`` when git is unavailable or the resolution
    fails (matches the events_log.py fallback contract).
    """
    try:
        result = _run_git(["rev-parse", "--git-common-dir"], project_root, check=False)
    except (FileNotFoundError, OSError):
        return project_root
    if result.returncode != 0:
        return project_root
    git_common = result.stdout.strip()
    if not git_common:
        return project_root
    git_common_path = Path(git_common)
    if not git_common_path.is_absolute():
        git_common_path = (project_root / git_common_path).resolve()
    # git-common-dir points at the .git directory of the main repo; its
    # parent is the main repo's working tree root.
    return git_common_path.parent


def is_tracked(project_root: Path) -> bool:
    """True when ``shipwright_events.jsonl`` is tracked by git in this repo."""
    result = _run_git(["ls-files", "--error-unmatch", EVENT_FILE], project_root, check=False)
    return result.returncode == 0


def is_dirty(project_root: Path) -> bool:
    """True when ``shipwright_events.jsonl`` has uncommitted modifications."""
    result = _run_git(["diff", "--quiet", "--", EVENT_FILE], project_root, check=False)
    return result.returncode != 0


def is_untracked(project_root: Path) -> bool:
    """True when ``shipwright_events.jsonl`` exists but is not tracked AND not
    gitignored (rare — most projects gitignore it OR track it)."""
    if is_tracked(project_root):
        return False
    if not (project_root / EVENT_FILE).exists():
        return False
    result = _run_git(["check-ignore", "-q", EVENT_FILE], project_root, check=False)
    return result.returncode != 0  # check-ignore exit 0 = ignored, 1 = not ignored


def commit_followup(
    project_root: Path,
    run_id: str,
    event_id: str | None = None,
    co_author: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Execute the F7-followup commit logic. Returns a result dict.

    Mirrors record_event.py's worktree-aware semantics: if ``project_root``
    is inside a linked worktree, the operation targets the MAIN repo (where
    ``record_event.py`` actually wrote the event). The returned dict carries
    ``main_repo_root`` so callers can see which tree was acted on.
    """
    main_repo_root = resolve_main_repo_root(project_root)
    if not is_tracked(main_repo_root):
        return {
            "status": "ignored",
            "reason": "shipwright_events.jsonl is gitignored",
            "main_repo_root": str(main_repo_root),
        }
    if not is_dirty(main_repo_root):
        return {
            "status": "clean",
            "reason": "no uncommitted changes to shipwright_events.jsonl",
            "main_repo_root": str(main_repo_root),
        }
    # Switch project_root to the main repo for the rest of this function.
    project_root = main_repo_root

    body_lines = [
        "Follow-up commit for the F7 work_completed event appended by",
        f"record_event.py during iterate run {run_id}. shipwright_events.jsonl",
        "is tracked in this repo (.gitignore line 70 negates the general",
        "ignore for the repo root); without a follow-up commit, the next",
        "`git reset --hard` / `git stash` / rebase silently wipes the",
        "append.",
    ]
    if event_id:
        body_lines.append("")
        body_lines.append(f"Event: {event_id}")
    body_lines.append("")
    body_lines.append(f"Run-ID: {run_id}")
    if co_author:
        body_lines.append(f"Co-Authored-By: {co_author}")

    title = f"chore(events): record work_completed for {run_id}"
    if event_id:
        title = f"chore(events): record {event_id} for {run_id}"
    commit_msg = title + "\n\n" + "\n".join(body_lines)

    if dry_run:
        return {
            "status": "dry_run",
            "title": title,
            "body": "\n".join(body_lines),
            "main_repo_root": str(main_repo_root),
        }

    _run_git(["add", EVENT_FILE], project_root, check=True)
    _run_git(["commit", "-m", commit_msg], project_root, check=True)
    sha = _run_git(["rev-parse", "HEAD"], project_root, check=True).stdout.strip()
    return {
        "status": "committed",
        "commit": sha,
        "title": title,
        "main_repo_root": str(main_repo_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F7 follow-up commit for tracked shipwright_events.jsonl",
    )
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--event-id", default=None)
    parser.add_argument("--co-author", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = commit_followup(
            project_root=args.project_root.resolve(),
            run_id=args.run_id,
            event_id=args.event_id,
            co_author=args.co_author,
            dry_run=args.dry_run,
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"git failed: {exc.stderr or exc.stdout}\n")
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"git not found: {exc}\n")
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
