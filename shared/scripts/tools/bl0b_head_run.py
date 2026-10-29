#!/usr/bin/env python3
"""BL0b item 2: run every pytest root once at one commit (serially, CI-faithful) and keep each root's coverage database.

    bl0b_head_run.py --tree <detached worktree at the commit> --out <dir outside the tree> [--roots R ...] [--timeout SECONDS]

Writes ``<out>/runs.json`` (one entry per root: time, exit code, summary, database size), ``<out>/junit-*.xml``,
``<out>/log-*.txt`` and ``<out>/cov-*`` (coverage databases with per-test contexts). Measurement only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from verifiers._baseline_head_run import run_all  # noqa: E402
from verifiers._baseline_measure import discover_roots  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--roots", nargs="*")
    ap.add_argument("--timeout", type=int, default=3000, help="seconds per root (default 3000)")
    ap.add_argument("--venv")
    args = ap.parse_args(argv)
    tree = Path(args.tree).resolve()
    run_all(tree, args.roots or discover_roots(tree), Path(args.out), args.timeout, args.venv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
