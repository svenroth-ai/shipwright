#!/usr/bin/env python3
"""Build or query bounded LLM context derived from Shipwright's raw event log."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))

from lib.event_context_index import build_index, index_path  # noqa: E402
from lib.event_context_query import (  # noqa: E402
    DEFAULT_MAX_EVENTS,
    DEFAULT_MAX_TOKENS,
    MODES,
    query_events,
)


def _atomic_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    rebuild = sub.add_parser("rebuild", help="discard and rebuild the derived index")
    rebuild.add_argument("--project-root", default=".")
    query = sub.add_parser("query", help="emit bounded, relevance-selected untrusted event data")
    query.add_argument("--project-root", default=".")
    query.add_argument("--run-id", required=True)
    query.add_argument("--mode", choices=sorted(MODES))
    query.add_argument("--changed-file", action="append", default=[])
    query.add_argument("--area", action="append", default=[])
    query.add_argument("--affected-fr", action="append", default=[])
    query.add_argument("--event-type", action="append", default=[])
    query.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    query.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    query.add_argument("--output")
    query.add_argument("--no-metrics", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        if args.command == "rebuild":
            payload = build_index(root)
            result = {"entries": len(payload["entries"]), "event_log_fingerprint": payload["event_log_fingerprint"],
                      "index_path": str(index_path(root)), "invalid_lines": payload["invalid_lines"]}
        else:
            result = query_events(root, run_id=args.run_id, mode=args.mode,
                                  changed_files=args.changed_file, area_ids=args.area,
                                  affected_frs=args.affected_fr, event_types=args.event_type,
                                  max_events=args.max_events, max_tokens=args.max_tokens,
                                  write_metrics=not args.no_metrics)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"command": args.command, "error": str(exc), "success": False}, sort_keys=True), file=sys.stderr)
        return 2
    if getattr(args, "output", None):
        _atomic_output(Path(args.output), result)
        print(json.dumps({"coverage": result["coverage"], "events": len(result["events"]),
                          "fallbacks_used": result["fallbacks_used"], "mode": result["mode"],
                          "output": str(Path(args.output))}, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
