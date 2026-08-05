#!/usr/bin/env python3
"""CLI for agent-emitted iterate-timing spans (measurement only).

Thin CLI over ``lib.iterate_timings`` for the boundaries no single process
owns (entering Build, entering Self-Review, a reviewer dispatch/receipt,
post-CI remediation, …) — see
``plugins/shipwright-iterate/skills/iterate/references/iterate-timings.md``
for the full catalog and which spans are producer-owned instead (those need
no agent action at all).

Usage:
    uv run iterate_timing.py start <name> --parent <p|none> \\
        --project-root <p> --run-id <id> [--attempt N]
    uv run iterate_timing.py end <name> --parent <p|none> \\
        --project-root <p> --run-id <id> [--attempt N] \\
        [--outcome completed|incomplete|cancelled] [--extra-json '{}']

Best-effort — every SKILL call site suffixes ``|| true`` so a transient
failure here never blocks the iterate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.iterate_entry import RUN_ID_STRICT  # noqa: E402
from lib.iterate_timings import (  # noqa: E402
    IterateTimingError,
    SPAN_NAMES,
    record_end,
    record_start,
)


def _parent_arg(value: str) -> str | None:
    return None if value.lower() == "none" else value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent-emitted iterate-timing marks")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="Mark entering a span (no process owns this boundary).")
    s.add_argument("name", choices=sorted(SPAN_NAMES))
    s.add_argument("--parent", required=True, help="parent span name, or 'none' for top-level")
    s.add_argument("--project-root", required=True)
    s.add_argument("--run-id", required=True)
    s.add_argument("--attempt", type=int, default=1)

    e = sub.add_parser("end", help="Mark leaving a span.")
    e.add_argument("name", choices=sorted(SPAN_NAMES))
    e.add_argument("--parent", required=True, help="parent span name, or 'none' for top-level")
    e.add_argument("--project-root", required=True)
    e.add_argument("--run-id", required=True)
    e.add_argument("--attempt", type=int, default=1)
    e.add_argument("--outcome", default="completed",
                    choices=["completed", "incomplete", "cancelled"])
    e.add_argument("--extra-json", default=None,
                    help="bounded metadata, e.g. '{\"reviewer\": \"code-reviewer\"}'")

    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()

    if not RUN_ID_STRICT.match(str(args.run_id)):
        print(f"[iterate_timing] not a canonical iterate run_id: {args.run_id!r}", file=sys.stderr)
        return 2

    parent = _parent_arg(args.parent)

    if args.cmd == "start":
        try:
            path = record_start(project_root, args.run_id, name=args.name, parent=parent,
                                attempt=args.attempt)
        except (OSError, IterateTimingError) as exc:
            print(f"[iterate_timing] start skipped: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"started": args.name, "parent": parent, "sidecar": str(path)},
                         ensure_ascii=False))
        return 0

    # end
    extra = None
    if args.extra_json:
        try:
            extra = json.loads(args.extra_json)
        except json.JSONDecodeError as exc:
            print(f"[iterate_timing] --extra-json is not valid JSON: {exc}", file=sys.stderr)
            return 2
    try:
        path = record_end(project_root, args.run_id, name=args.name, parent=parent,
                          attempt=args.attempt, outcome=args.outcome, extra=extra)
    except (OSError, IterateTimingError) as exc:
        print(f"[iterate_timing] end skipped: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ended": args.name, "parent": parent, "sidecar": str(path)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
