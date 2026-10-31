"""Replay the ``affected_acs`` rule over the last N recorded iterate events (read-only).

For each ``work_completed`` iterate event in the window it asks the same
question the F11 check asks - does the diff touch a runtime path
(``changed_files``) and is the declaration present - and prints the counts.
An event with no ``changed_files`` list cannot be placed either way; it is counted as
``unknown_paths`` and the measurement is then reported ``conclusive: false``.
Events recorded before the field existed show up as ``missing``: that is the
measure of how many past iterates the rule would have asked.

    uv run shared/scripts/tools/affected_acs_replay.py --project-root . --window 100
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.affected_acs_gate import declaration_present, is_scoped_intent, requires_declaration  # noqa: E402
from lib.events_log import resolve_events_path  # noqa: E402
from lib.jsonl_records import read_jsonl_records  # noqa: E402


def git_paths_for_run(project_root: Path, run_id: str) -> list[str] | None:
    """Paths changed by the commits stamped ``Run-ID: <run_id>``; ``None`` when none can be found."""
    if not run_id:
        return None
    try:
        shas = subprocess.run(
            ["git", "-C", str(project_root), "log", "--all", "--fixed-strings", f"--grep=Run-ID: {run_id}", "--format=%H"],
            capture_output=True, text=True, timeout=60, check=False,
        ).stdout.split()
        paths: set[str] = set()
        for sha in shas:
            out = subprocess.run(
                ["git", "-C", str(project_root), "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", sha],
                capture_output=True, text=True, timeout=60, check=False,
            ).stdout
            paths.update(line.strip() for line in out.splitlines() if line.strip())
    except (OSError, subprocess.SubprocessError):
        return None
    return sorted(paths) if shas else None


def replay(events: list[dict], window: int, paths_for=None) -> dict:
    """Counts over the last ``window`` iterate ``work_completed`` events.

    ``paths_for(run_id)`` (optional) supplies the changed paths of an event that lists none."""
    iterates = [e for e in events if e.get("type") == "work_completed" and e.get("source") == "iterate"]
    picked = iterates[-window:] if window > 0 else iterates
    required = declared = unknown = 0
    missing: list[str] = []
    for evt in picked:
        files = evt.get("changed_files")
        if not isinstance(files, list) and paths_for is not None:
            files = paths_for(str(evt.get("adr_id") or ""))
        if not isinstance(files, list):
            # No path list on the event: runtime-touching or not cannot be told. Counted apart, never as clean.
            if is_scoped_intent(evt):
                unknown += 1
            continue
        if not requires_declaration(evt, files):
            continue
        required += 1
        if declaration_present(evt):
            declared += 1
        else:
            missing.append(str(evt.get("adr_id") or evt.get("id") or "?"))
    return {"window": len(picked), "required": required, "declared": declared,
            "missing": len(missing), "unknown_paths": unknown, "conclusive": unknown == 0,
            "missing_run_ids": missing}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--window", type=int, default=100)
    parser.add_argument("--git", action="store_true",
                        help="reconstruct changed paths from Run-ID commits for events that list none")
    args = parser.parse_args()
    path = resolve_events_path(Path(args.project_root))
    events = read_jsonl_records(path).records if path.exists() else []
    print(json.dumps(replay(events, args.window, (lambda rid: git_paths_for_run(Path(args.project_root), rid)) if args.git else None), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
