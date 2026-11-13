#!/usr/bin/env python3
"""Move the event folders from the repo root into ``.shipwright/events/`` (one-off, per repo).

    migrate_events_folder.py --project-root . [--dry-run]

    shipwright_events.d/          ->  .shipwright/events/drops/
    shipwright_events.archive/    ->  .shipwright/events/archive/
    shipwright_events.quarantine/ ->  .shipwright/events/quarantine/

Tracked files move with ``git mv`` (so git sees a rename and the history follows); untracked ones are
renamed in place. Re-runnable: a repo that is already migrated reports ``nothing_to_migrate``. The tool never
overwrites: a name that exists in both places with DIFFERENT content stops it (exit 1) before anything is moved
(byte-identical duplicates count as already moved). OS junk (Thumbs.db, .DS_Store, desktop.ini) is deleted, not
moved. It changes the working tree and the index only -- the caller commits.

Prints one JSON object. Exit 0 = migrated or nothing to do, 1 = refused (a name exists in both places),
2 = bad arguments / git or filesystem trouble (``git_mv_failed``, ``move_failed``, ``migrated_incomplete``).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_sentinel import MOVED_FOLDERS, OS_JUNK_NAMES, old_event_folders  # noqa: E402
from tools.verifiers.stdio import ensure_utf8_stdout  # noqa: E402


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120)


def _tracked(root: Path, rel: str) -> bool:
    proc = _git(root, "ls-files", "--error-unmatch", "--", rel)
    return proc.returncode == 0


def _same_bytes(a: Path, b: Path) -> bool:
    try:
        return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _plan(root: Path) -> tuple[list[tuple[str, str]], list[str], list[str], list[str]]:
    """(moves as (old file, new file), collisions, leftovers to drop, new copies to track).

    A move is per FILE so a half-migrated repo converges. OS junk is dropped, not moved (it would trip the
    integrity check in the new folder); a name present at both places with identical bytes counts as already
    moved (the old copy is dropped), any other duplicate is a collision.
    """
    moves: list[tuple[str, str]] = []
    collisions: list[str] = []
    drop: list[str] = []
    adopt: list[str] = []   # the identical new copy that must be tracked before its old twin is removed
    for old in old_event_folders(root):
        new = MOVED_FOLDERS[old]
        for src in sorted(p for p in (root / old).iterdir()):
            old_rel, new_rel = f"{old}/{src.name}", f"{new}/{src.name}"
            if src.name in OS_JUNK_NAMES:
                drop.append(old_rel)
            elif not (root / new_rel).exists():
                moves.append((old_rel, new_rel))
            elif _same_bytes(src, root / new_rel):
                drop.append(old_rel)
                adopt.append(new_rel)
            else:
                collisions.append(new_rel)
    return moves, collisions, drop, adopt


def migrate(root: Path, dry_run: bool = False) -> dict:
    odd = [f"{old}/{p.name}" for old in old_event_folders(root) for p in (root / old).iterdir() if p.is_dir()]
    if odd:   # a sub-directory has no legal name in the new folder: never moved blindly
        return {"status": "refused_unexpected_entry", "entries": odd}
    moves, collisions, drop, adopt = _plan(root)
    if collisions:
        return {"status": "refused_name_exists_in_both_places", "files": collisions}
    if not moves and not drop and not old_event_folders(root):
        return {"status": "nothing_to_migrate"}
    if dry_run:
        return {"status": "dry_run", "moves": [{"from": a, "to": b} for a, b in moves], "dropped": drop}
    done: list[dict] = []
    unstaged: list[str] = []
    try:
        for old_rel, new_rel in moves:
            if (root / new_rel).exists():  # appeared since the plan: never overwrite
                return {"status": "refused_name_exists_in_both_places", "files": [new_rel], "moved": done}
            (root / new_rel).parent.mkdir(parents=True, exist_ok=True)
            if _tracked(root, old_rel):
                proc = _git(root, "mv", "--", old_rel, new_rel)
                if proc.returncode != 0:
                    return {"status": "git_mv_failed", "file": old_rel, "error": proc.stderr.strip()[:300], "moved": done}
            else:
                shutil.move(str(root / old_rel), str(root / new_rel))
                if _git(root, "add", "--", new_rel).returncode != 0:   # e.g. an ignored folder: reported, the F11 check fails loudly
                    unstaged.append(new_rel)
            done.append({"from": old_rel, "to": new_rel})
        for new_rel in adopt:   # tracked old twin + untracked identical new copy: track the copy, or the commit would lose the file
            if not _tracked(root, new_rel) and _git(root, "add", "--", new_rel).returncode != 0:
                return {"status": "git_mv_failed", "file": new_rel, "error": "git add failed", "moved": done}
        for old_rel in drop:
            if _tracked(root, old_rel):
                proc = _git(root, "rm", "-q", "-f", "--", old_rel)
                if proc.returncode != 0:
                    return {"status": "git_mv_failed", "file": old_rel, "error": proc.stderr.strip()[:300], "moved": done}
            else:
                (root / old_rel).unlink(missing_ok=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "move_failed", "error": str(exc)[:300], "moved": done}
    for old in list(MOVED_FOLDERS):  # an emptied old folder is removed so the hard-abort check no longer sees it
        folder = root / old
        if folder.is_dir() and not folder.is_symlink():
            for junk in [p for p in folder.iterdir() if p.name in OS_JUNK_NAMES and p.is_file()]:
                junk.unlink()   # a folder that only ever held OS junk goes too
            if not any(folder.iterdir()):
                folder.rmdir()
    left = old_event_folders(root)
    out = {"status": "migrated" if not left else "migrated_incomplete", "moved": done, "still_at_old_location": left}
    if unstaged:
        out["not_staged"] = unstaged
    return out


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.project_root).resolve()
    if not root.is_dir():
        print(json.dumps({"status": "bad_arguments", "error": f"{root} is not a directory"}))
        return 2
    result = migrate(root, args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    status = result["status"]
    if status.startswith("refused"):
        return 1
    return 2 if status in ("git_mv_failed", "move_failed", "migrated_incomplete") else 0


if __name__ == "__main__":
    sys.exit(main())
