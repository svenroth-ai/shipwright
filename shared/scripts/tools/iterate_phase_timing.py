#!/usr/bin/env python3
"""CLI for iterate per-phase timing marks (M-Pre-1 iterate half).

Thin CLI over ``lib.iterate_phase_groups``. The iterate SKILL calls ``mark`` as
it crosses each of the 5 WebUI Iterate-Rail group boundaries
(``scope build review test finalize``); ``finalize_iterate`` (F5b) reads the
sidecar and folds the durations into ``work_completed.phase_timings``. See
``lib/iterate_phase_groups.py`` for the design + boundary contract.

Usage:
    uv run iterate_phase_timing.py mark <group> --project-root <p> --run-id <id>
    uv run iterate_phase_timing.py summarize --project-root <p> --run-id <id>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.iterate_entry import RUN_ID_STRICT  # noqa: E402
from lib.iterate_phase_groups import (  # noqa: E402
    ITERATE_PHASE_GROUPS,
    append_mark,
    compute_phase_timings,
    read_marks,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Iterate per-phase timing marks")
    sub = parser.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mark", help="Record a group-boundary timing mark (first-wins).")
    m.add_argument("group", choices=list(ITERATE_PHASE_GROUPS))
    m.add_argument("--project-root", required=True)
    m.add_argument("--run-id", required=True)

    s = sub.add_parser("summarize", help="Print computed phase_timings JSON for a run.")
    s.add_argument("--project-root", required=True)
    s.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()

    if not RUN_ID_STRICT.match(str(args.run_id)):
        print(
            f"[iterate_phase_timing] not a canonical iterate run_id: {args.run_id!r}",
            file=sys.stderr,
        )
        return 2

    if args.cmd == "mark":
        try:
            path = append_mark(project_root, args.run_id, args.group)
        except (OSError, ValueError) as exc:  # best-effort: never abort the iterate
            print(f"[iterate_phase_timing] mark skipped: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"marked": args.group, "sidecar": str(path)}, ensure_ascii=False))
        return 0

    # summarize
    marks = read_marks(project_root, args.run_id)
    timings = compute_phase_timings(marks, datetime.now(timezone.utc))
    print(json.dumps(timings, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
