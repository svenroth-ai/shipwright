#!/usr/bin/env python3
"""Fold the old per-run event files at release time, in a commit of their own, and never block the release.

    fold_events_for_release.py --project-root . [--base-ref REF] [--max-age-days 14] [--dry-run]

Called from ``/shipwright-changelog`` Step 5.3, before anything else of the release is staged. It is the
routine housekeeping of ``tools/fold_events.py fold`` made automatic: drops that are on the base ref unchanged
and older than the age limit move into ONE archive file, and exactly the paths the fold touched go into one
``chore(events)`` commit (``git commit --pathspec-from-file``: whatever else is staged stays out, and a
thousand file names do not overflow a Windows command line). Hooks are never bypassed.

Prints one JSON object and always exits 0 (2 only for bad arguments): housekeeping must never stop a release.
``status`` says what happened:

* ``folded`` -- committed (``commit``, ``events``, ``files``).
* ``nothing_to_fold`` / ``not_applicable`` -- nothing changed (``not_applicable``: the project is on the legacy layout).
* ``skipped`` -- nothing of the fold was written; ``reason`` says why (a conflicting id, a file with local changes, no base ref ...).
* ``dry_run`` -- with ``--dry-run``: the files a fold would take, nothing changed.
* ``incomplete`` -- a file could not be deleted (a reader holds it open) or an error hit the fold half way; nothing was committed.
* ``commit_failed`` -- git refused the commit (a hook); nothing was committed.

Every failure after the fold started puts the tree back as it was (``rolled_back: true``): the archive the fold
wrote is removed, the deleted drops are restored from HEAD, the index is as before. A fold is lossless to repeat,
so the next release tries again. Every status except ``not_applicable`` also carries ``open_files``, the number of
event files still open, so a fold that keeps failing shows in the release output.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_fold import FOLD_AGE_DAYS, apply_fold, plan_fold  # noqa: E402
from lib.events_fold_io import KEEP_NAME, GitError, git  # noqa: E402
from lib.events_layout import events_layout  # noqa: E402
from lib.events_log import ARCHIVE_DIR, DROPS_DIR  # noqa: E402
from tools.fold_events import DEFAULT_BASE, REFUSED, _stage, _stage_paths  # noqa: E402
from tools.verifiers.stdio import ensure_utf8_stdout  # noqa: E402


def _default_base(root: str) -> str:
    """The trunk the repo itself names (origin/HEAD), else origin/main, else origin/master."""
    proc = git(root, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False)
    named = proc.stdout.decode("utf-8", "replace").strip() if proc.returncode == 0 else ""
    for ref in (named, DEFAULT_BASE, "origin/master"):
        if ref and git(root, "rev-parse", "--verify", "-q", ref + "^{commit}", check=False).returncode == 0:
            return ref
    return named or DEFAULT_BASE


def _pathspec_git(root: str, args: list[str], paths: list[str]) -> subprocess.CompletedProcess:
    """``git <args> --pathspec-from-file=-`` with the NUL-separated ``paths`` on stdin (no command-line limit)."""
    return subprocess.run(["git", "-C", str(root), "--literal-pathspecs", *args, "--pathspec-from-file=-", "--pathspec-file-nul"],
                          input=chr(0).join(paths).encode("utf-8"), capture_output=True, timeout=300)


def _open_files(root: str) -> int:
    folder = Path(root) / DROPS_DIR
    return sum(1 for _ in folder.glob("*.jsonl")) if folder.is_dir() else 0


def _dirty(root: str, paths: list[str]) -> bool:
    """True when any of ``paths`` has a change in the index or the work tree (a person's work the fold must not sweep up).

    An untracked archive file or ``.keep`` is not a change of a person's work: the fold writes that very name itself (same
    bytes, or it refuses on its own)."""
    proc = git(root, "status", "--porcelain", "-z", "--", DROPS_DIR, ARCHIVE_DIR, check=False)
    if proc.returncode:
        return True   # cannot tell: fail closed
    mine, records, i = set(paths), proc.stdout.decode("utf-8", "replace").split(chr(0)), 0
    while i < len(records):
        entry = records[i]
        i += 1
        if len(entry) < 4:
            continue
        names = [entry[3:]]
        if entry[0] in "RC":   # a rename or copy carries the old path as the next record
            names.append(records[i] if i < len(records) else "")
            i += 1
        if entry[:2] == "??" and all(n.startswith(ARCHIVE_DIR + "/") or n == f"{DROPS_DIR}/{KEEP_NAME}" for n in names):
            continue
        if any(n in mine for n in names):
            return True
    return False


def _rollback(root: str, paths: list[str], existed: frozenset[str] = frozenset()) -> bool:
    """Undo a fold that did not end in a commit: unstage ``paths``, restore the ones HEAD has, remove the rest.

    A path that existed before the run (``existed``) and is not in HEAD is somebody else's file and stays. The archive
    this run wrote is removed only after every drop is confirmed back. Never raises: ``False`` says the tree could not be
    put back completely (then repair by hand, see the changelog skill, Step 5.3)."""
    try:
        proc = git(root, "ls-tree", "-r", "--name-only", "-z", "HEAD", check=False)
        if proc.returncode:
            return False
        in_head = set(proc.stdout.decode("utf-8", "replace").split(chr(0)))
        ok = _pathspec_git(root, ["reset", "-q"], paths).returncode == 0
        tracked = [p for p in paths if p in in_head]
        if tracked:
            ok = _pathspec_git(root, ["checkout", "HEAD"], tracked).returncode == 0 and ok
        if not ok:
            return False   # the drops may still be missing: the archive is then the only copy of their events, keep it
        for p in paths:
            if p not in in_head and p not in existed:
                (Path(root) / p).unlink(missing_ok=True)
        return ok
    except (GitError, OSError, subprocess.SubprocessError):
        return False


def _planned_paths(plan) -> list[str]:
    """Every path a fold of ``plan`` may write or delete (known before it starts, so a failure anywhere can be undone)."""
    name = plan.archive_name
    return ([f"{ARCHIVE_DIR}/{name}"] if name else []) + [f"{DROPS_DIR}/{s.path.name}" for s in plan.selected] + [f"{DROPS_DIR}/{KEEP_NAME}"]


def _failed(root: str, result: dict, planned: list[str], existed: frozenset[str]) -> dict:
    """The report for a fold that did not finish; undoes what it left behind when it had written anything."""
    status = result.get("status", "")
    why = "an id carries different content in two places" if status == "conflict" else status
    wrote = status == "folded_incomplete" or (status == "archive_incomplete" and result.get("missing"))   # else: nothing of ours was written
    out = {"status": "incomplete" if wrote else "skipped", "reason": result.get("error") or why + (" (refused)" if status in REFUSED else "")}
    if status == "folded_incomplete":
        out["not_deleted"] = result.get("not_deleted", [])
    if wrote:
        out["rolled_back"] = _rollback(root, planned, existed)
    return out


def fold_for_release(root: str, base_ref: str | None = None, max_age_days: int = FOLD_AGE_DAYS, dry_run: bool = False) -> dict:
    """The one JSON-able result; every status except ``not_applicable`` carries ``open_files``."""
    out = _fold(root, base_ref, max_age_days, dry_run)
    if out["status"] != "not_applicable":
        out.setdefault("open_files", _open_files(root))
    return out


def _fold(root: str, base_ref: str | None, max_age_days: int, dry_run: bool) -> dict:
    if events_layout(root) != "drops":
        return {"status": "not_applicable", "reason": "the project is on the legacy event log"}
    planned: list[str] = []
    existed: frozenset[str] = frozenset()
    started = False   # True once the fold may have changed files: from then on a failure must undo it
    try:
        if git(root, "rev-parse", "--show-prefix", check=False).stdout.strip():
            return {"status": "skipped", "reason": "the project root is a folder inside the repository, not its top level"}
        base_ref = base_ref or _default_base(root)
        if git(root, "rev-parse", "--verify", "-q", base_ref + "^{commit}", check=False).returncode:
            return {"status": "skipped", "reason": f"{base_ref} does not resolve, so nothing can be called merged"}
        merged_at = git(root, "merge-base", base_ref, "HEAD", check=False)   # what the F11 events integrity check calls the base
        if merged_at.returncode:
            return {"status": "skipped", "reason": f"{base_ref} and HEAD share no history"}
        plan = plan_fold(root, base_ref=merged_at.stdout.decode("utf-8", "replace").strip(), max_age_days=max_age_days)
        if dry_run:
            return {"status": "dry_run", "files": [s.path.name for s in plan.selected], "conflicting_ids": plan.conflicts}
        planned = _planned_paths(plan)
        existed = frozenset(p for p in planned if (Path(root) / p).exists())
        if plan.selected and _dirty(root, planned):
            return {"status": "skipped", "reason": "an event file to fold has local changes, or git could not say"}
        started = True
        result = apply_fold(root, plan)
        if result.get("status") == "nothing_to_fold":
            return {"status": "nothing_to_fold"}
        if result.get("status") != "folded":
            return _failed(root, result, planned, existed)
        return _commit_fold(root, result, max_age_days, existed)
    except (GitError, ValueError, TypeError, OSError, subprocess.SubprocessError) as exc:
        reason = f"{exc.__class__.__name__}: {exc}"
        if started:
            return {"status": "incomplete", "reason": reason, "rolled_back": _rollback(root, planned, existed)}
        return {"status": "skipped", "reason": reason}


def _head(root: str) -> str:
    return git(root, "rev-parse", "HEAD", check=False).stdout.decode("utf-8", "replace").strip()


def _commit_fold(root: str, result: dict, max_age_days: int, existed: frozenset[str]) -> dict:
    """Stage and commit what the fold touched; any failure on the way puts the tree back (the fold already moved files).

    Whether the commit happened is decided by HEAD, not by the exit code of a hook that may have run after it."""
    touched = _stage_paths(result)
    before, reason, count = _head(root), "", len(result.get("folded_files", []))
    try:
        known = _stage(root, touched)
        if not known:
            reason = "nothing was staged"
        else:
            proc = _pathspec_git(root, ["commit", "-q", "-m", f"chore(events): fold {count} event files older than {max_age_days} days into the archive"], known)
            if proc.returncode:
                reason = proc.stderr.decode("utf-8", "replace").strip()[-400:] or f"git commit exited with {proc.returncode}"
    except subprocess.TimeoutExpired:
        lock = Path(git(root, "rev-parse", "--git-path", "index.lock", check=False).stdout.decode("utf-8", "replace").strip())
        reason = "git commit did not finish in time (a hook that waits?)" + (f"; {lock} is left behind, remove it once no git runs" if lock.exists() else "")
    except (GitError, OSError, subprocess.SubprocessError) as exc:
        reason = f"{exc.__class__.__name__}: {exc}"
    if _head(root) != before:
        return {"status": "folded", "commit": _head(root), "files": count, "events": result.get("events", 0), "archive": result.get("archive")}
    return {"status": "commit_failed", "reason": reason or "git made no commit", "rolled_back": _rollback(root, touched, existed)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--project-root", default=".")
    p.add_argument("--base-ref", default=None, help="what counts as merged (default: the repo's origin/HEAD, else origin/main, else origin/master)")
    p.add_argument("--max-age-days", type=int, default=FOLD_AGE_DAYS)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    ensure_utf8_stdout()
    try:
        out = fold_for_release(a.project_root, a.base_ref, a.max_age_days, a.dry_run)
    except Exception as exc:  # noqa: BLE001 -- housekeeping must never stop a release, whatever it hit
        out = {"status": "skipped", "reason": f"{exc.__class__.__name__}: {exc}"}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
