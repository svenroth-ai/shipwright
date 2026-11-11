#!/usr/bin/env python3
"""Fold, emergency-fold, fully fold or quarantine the per-run event drop files (issue 978, S6).

    fold_events.py fold       --project-root . [--base-ref origin/main] [--max-age-days 14] [--dry-run]
    fold_events.py emergency  --project-root .     # every ok drop -> archive, events_layout back to legacy
    fold_events.py full       --project-root .     # archive + drops -> the one legacy log (pre-change readers)
    fold_events.py quarantine --project-root . [--base-ref origin/main]   # zero-record, non-ok-at-base drops

Prints one JSON object. The tool changes the working tree only; the caller stages
(``--stage`` stages exactly the paths it touched) and commits. Exit 0 = done or
nothing to do, 1 = refused (a conflicting duplicate id, a changed file), 2 = bad arguments / git trouble.
See ``lib/events_fold.py`` and ``lib/events_fold_full.py`` for the rules.
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

from lib.events_fold import FOLD_AGE_DAYS, apply_fold, apply_quarantine, plan_fold, plan_quarantine  # noqa: E402
from lib.events_fold_full import apply_full_fold  # noqa: E402
from lib.events_fold_io import KEEP_NAME, GitError, git  # noqa: E402
from lib.events_log import DROPS_DIR, QUARANTINE_DIR  # noqa: E402
from tools.verifiers.stdio import ensure_utf8_stdout  # noqa: E402

DEFAULT_BASE = "origin/main"
REFUSED = ("conflict", "changed_since_plan", "archive_incomplete", "copy_mismatch",
           "folded_incomplete", "folded_into_legacy_incomplete", "quarantined_incomplete")   # the last three: a file could not be deleted


def _stage_paths(result: dict) -> list[str]:
    """Exactly what the tool changed (never a folder-level add: other runs may have untracked drops there)."""
    status, paths = result.get("status", ""), []
    if status.startswith("folded"):   # also *_incomplete: staged as far as it got, the finishing re-run (same command) stages the rest
        paths.append(f"{DROPS_DIR}/{KEEP_NAME}")
        paths += [f"{DROPS_DIR}/{n}" for n in result.get("folded_files", [])]
        paths += [result["archive"]] if result.get("archive") else []
        paths += result.get("removed_files", [])
        if result.get("mode") == "emergency" or status == "folded_into_legacy":
            paths.append("shipwright_sync_config.json")
        paths += [result["legacy_log"]] if result.get("legacy_log") else []
    if status.startswith("quarantined"):
        paths += [f"{folder}/{n}" for folder in (QUARANTINE_DIR, DROPS_DIR) for n in result.get("files", [])]
    if status == "nothing_to_fold" and result.get("mode") == "emergency":
        paths.append("shipwright_sync_config.json")   # an emergency fold with nothing left still resets the layout
    return paths


def _stage(root: str, paths: list[str]) -> list[str]:
    """``git add -A`` of exactly ``paths`` (those that exist or are tracked) in ONE call, paths on stdin (S8: ~1000 drops
    overflowed a Windows command line; one call also keeps the index all-or-nothing)."""
    tracked = set(git(root, "ls-files", "-z").stdout.decode("utf-8", "replace").split(chr(0)))
    known = [p for p in paths if (Path(root) / p).exists() or p in tracked]
    if not known:
        return []
    proc = subprocess.run(["git", "-C", str(root), "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul"],
                          input=chr(0).join(known).encode("utf-8"), capture_output=True, timeout=120)
    if proc.returncode:
        raise GitError("git add failed: " + proc.stderr.decode("utf-8", "replace").strip()[-400:])
    return known


def _run(a: argparse.Namespace) -> dict:
    if a.command == "full":
        return {"status": "dry_run"} if a.dry_run else apply_full_fold(a.project_root, allow_conflicts=a.allow_conflicts)
    if a.command == "quarantine":
        items = plan_quarantine(a.project_root, base_ref=a.base_ref)
        if a.dry_run:
            return {"status": "dry_run", "files": [i.path.name for i in items]}
        return apply_quarantine(a.project_root, items)
    plan = plan_fold(a.project_root, mode=a.command, base_ref=a.base_ref, max_age_days=a.max_age_days,
                     include_corrupt=a.include_corrupt)
    if a.dry_run:
        return {"status": "dry_run", "archive": plan.archive_name, "files": [s.path.name for s in plan.selected],
                "skipped": plan.skipped, "conflicting_ids": plan.conflicts}
    return apply_fold(a.project_root, plan, allow_conflicts=a.allow_conflicts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("command", choices=("fold", "emergency", "full", "quarantine"))
    p.add_argument("--project-root", default=".")
    p.add_argument("--base-ref", default=None, help=f"the ref whose tree defines merged (default {DEFAULT_BASE}; fold and quarantine only)")
    p.add_argument("--max-age-days", type=int, default=FOLD_AGE_DAYS)
    p.add_argument("--include-corrupt", action="store_true")
    p.add_argument("--allow-conflicts", action="store_true", help="keep BOTH when an id carries different content")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--stage", action="store_true")
    a = p.parse_args(argv)
    ensure_utf8_stdout()
    if a.command in ("fold", "quarantine") and a.base_ref is None:
        a.base_ref = DEFAULT_BASE
        if git(a.project_root, "rev-parse", "--verify", "-q", DEFAULT_BASE + "^{commit}", check=False).returncode:
            print(json.dumps({"status": "error", "error": f"{DEFAULT_BASE} does not resolve; pass --base-ref"}))
            return 2
    try:
        result = _run(a)
        if a.stage and not a.dry_run:
            _stage(a.project_root, _stage_paths(result))
    except (GitError, ValueError, TypeError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result.get("status") in REFUSED else 0


if __name__ == "__main__":
    sys.exit(main())
