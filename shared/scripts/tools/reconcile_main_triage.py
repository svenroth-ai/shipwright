#!/usr/bin/env python3
"""CLI for :func:`lib.reconcile_triage.reconcile_main_triage` — the post-merge
**sync-path** entrypoint.

Run this in the main repo BEFORE a ``git pull`` (e.g. as part of the post-merge
plugin-cache-sync) so uncommitted background ``.shipwright/triage.jsonl`` drift
is folded into one ``chore(triage)`` commit first — otherwise the pull is blocked
by the dirty tracked log (the 2026-06-07 failure). NB: once the drift is
committed, local ``main`` has diverged from ``origin/main``, so a literal
``--ff-only`` is no longer topologically possible — use a normal ``git pull``
(union merge). Safe to run any time: a no-op when there is no drift or when any
safety guard trips.

    uv run shared/scripts/tools/reconcile_main_triage.py [--project-root .] \\
        [--allow-ci] [--json]

Exit codes: 0 = committed | no_drift | skipped (safe to proceed) ·
3 = invalid (corrupt log — fix before pulling) · 4 = error (git/IO failure).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.reconcile_triage import reconcile_main_triage  # noqa: E402

_EXIT = {"committed": 0, "no_drift": 0, "skipped": 0, "invalid": 3, "error": 4}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fold main-tree triage.jsonl drift into one chore(triage) commit")
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--allow-ci",
        action="store_true",
        help="Permit the auto-commit even when $CI is set (default: skip in CI).",
    )
    parser.add_argument("--json", action="store_true", help="Emit the result dict as JSON.")
    args = parser.parse_args(argv)

    result = reconcile_main_triage(Path(args.project_root), allow_ci=args.allow_ci)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    elif result.status == "committed":
        print(f"reconcile-main-triage: committed — folded {result.folded} background append(s)")
    elif result.status == "no_drift":
        print("reconcile-main-triage: no drift — nothing to commit")
    elif result.status == "skipped":
        print(f"reconcile-main-triage: skipped — {result.reason}")
    elif result.status == "invalid":
        print(f"reconcile-main-triage: INVALID triage log — not committed: {result.errors}", file=sys.stderr)
    else:
        print(f"reconcile-main-triage: error — {result.reason}", file=sys.stderr)

    return _EXIT.get(result.status, 4)


if __name__ == "__main__":
    raise SystemExit(main())
