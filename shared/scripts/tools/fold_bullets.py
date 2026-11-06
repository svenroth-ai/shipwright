#!/usr/bin/env python3
"""Fold pending architecture / convention bullet drops into their curated docs, or show them.

    fold_bullets.py --project-root .            # fold + delete the drop files (release housekeeping)
    fold_bullets.py --project-root . --dry-run  # report only
    fold_bullets.py --project-root . --summary  # context load: 20 newest + "N more pending" (+ warning)

``aggregate_decisions`` (the release step) already folds bullets first; this CLI lets the fold run
as its own small PR. The caller stages the touched docs and the deleted drop files. See
``lib/doc_bullets.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.doc_bullets import fold, render_pending_summary  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--project-root", default=".")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--summary", action="store_true", help="print the context-load view and exit")
    a = p.parse_args(argv)
    if a.summary:
        text = render_pending_summary(a.project_root)
        if text:
            print("Pending bullets (not yet folded into architecture.md / conventions.md):")
            print(text)
        return 0
    res = fold(a.project_root, dry_run=a.dry_run)
    print(f"{'[dry-run] ' if a.dry_run else ''}folded {res['folded']} bullet(s)"
          if res["folded"] else "no pending bullets to fold")
    for name in res["skipped"]:
        print(f"WARNING: ignored non-bullet file in bullets/: {name}", file=sys.stderr)
    for name in res["conflicts"]:
        print(f"WARNING: kept {name}: its anchor is already in the doc with different text", file=sys.stderr)
    for err in res["errors"]:
        print(f"ERROR: {err}", file=sys.stderr)
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
