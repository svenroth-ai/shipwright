#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Record the one legitimate reason an --autonomous iterate may stop early.

The Stop-guard (``lib/iterate_stop_guard.py``) blocks every Stop while an
autonomous run's PR is not MERGED. A recorded hard blocker lifts the guard for
that run; ``--clear`` re-arms it once the blocker is resolved. Use it only for a
blocker the agent cannot resolve itself -- the F12 summary must name it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.iterate_stop_guard import (  # noqa: E402
    HARD_BLOCKER_CODES,
    clear_hard_blocker,
    record_hard_blocker,
)
from lib.repo_root import resolve_main_repo_root  # noqa: E402


def _run_has_live_pointer(main_root: Path, run_id: str) -> bool:
    for path in (main_root / ".shipwright" / "iterate_active").glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # unreadable or retired mid-glob: not a match
        if isinstance(data, dict) and data.get("run_id") == run_id:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-root", default=".")
    p.add_argument("--run-id", required=True)
    p.add_argument("--clear", action="store_true", help="remove a resolved blocker and re-arm the guard")
    p.add_argument("--reason-code", choices=HARD_BLOCKER_CODES)
    p.add_argument("--detail", help="one sentence: what blocks, what the operator must do")
    args = p.parse_args(argv)
    if not args.clear and not (args.reason_code and args.detail):
        p.error("--reason-code and --detail are required unless --clear is given")
    root = Path(args.project_root).resolve()
    main_root = resolve_main_repo_root(root) or root
    if not _run_has_live_pointer(main_root, args.run_id):
        print(f"no live run pointer names run_id {args.run_id!r}; nothing changed", file=sys.stderr)
        return 2
    if args.clear:
        print(json.dumps({"success": True, "run_id": args.run_id,
                          "cleared": clear_hard_blocker(main_root, args.run_id)}))
        return 0
    state = record_hard_blocker(main_root, args.run_id, args.reason_code, args.detail)
    print(json.dumps({"success": True, "run_id": args.run_id, "blocker": state["blocker"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
