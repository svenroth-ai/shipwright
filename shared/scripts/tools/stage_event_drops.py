#!/usr/bin/env python3
"""F6 staging of THIS run's event drop files (issue 978, campaign unit S4).

    uv run stage_event_drops.py --project-root <path> --run-id <run id> [--dry-run]

Stages (``git add --``, explicit paths) exactly the untracked drops whose KEY is the run's key and whose
``wt8`` is this worktree's -- never the folder (DESIGN 4.1): the shared campaign worktree has one ``wt8``
for the orchestrator and every sub-iterate, so a folder-level add would carry a sibling run's files.
Prints one JSON object ``{"staged": [...], "key": ..., "problems": [...]}``.

A no-op (``staged: []``, exit 0) under the legacy layout and for a run that wrote no drop. Exit 1 when a
selected drop is torn/empty (it must not become permanent history) or ``git add`` fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # shared/scripts
from lib.events_layout import drop_key, events_layout  # noqa: E402
from lib.events_stage import _git, own_drops, validate_drops, writer_lock  # noqa: E402


def stage(project_root: Path, run_id: str, dry_run: bool = False) -> tuple[dict, int]:
    out: dict = {"key": drop_key(project_root, None, run_id), "staged": [], "problems": []}
    if events_layout(project_root) != "drops" or not own_drops(project_root, run_id):
        return out, 0  # legacy, or nothing to stage: a write landing later is the absorb's, not this run's
    with writer_lock(project_root):  # list -> validate -> add is atomic w.r.t. an appending writer
        return _stage_locked(project_root, run_id, dry_run)


def _stage_locked(project_root: Path, run_id: str, dry_run: bool) -> tuple[dict, int]:
    rels = own_drops(project_root, run_id)
    out: dict = {"key": drop_key(project_root, None, run_id), "staged": [], "problems": []}
    if not rels:
        return out, 0
    out["problems"] = validate_drops(project_root, rels)
    if out["problems"]:
        return out, 1
    if dry_run:
        out["staged"] = rels
        return out, 0
    add = _git(project_root, "add", "--", *rels)
    if add.returncode != 0:
        out["problems"] = [f"git add failed: {add.stderr.strip()[:300]}"]
        return out, 1
    out["staged"] = rels
    return out, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage this run's event drop files (F6)")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result, rc = stage(args.project_root.resolve(), args.run_id, args.dry_run)
    print(json.dumps(result, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
