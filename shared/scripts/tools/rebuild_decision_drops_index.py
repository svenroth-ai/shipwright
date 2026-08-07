#!/usr/bin/env python3
"""Regenerate ``.shipwright/agent_docs/decision-drops/INDEX.md``. Nothing else.

Mirrors ``rebuild_adr_index.py``. The index is gitignored (the drops directory
is), so this exists purely as the documented manual refresh — never a CI drift
guard target. A repo with no pending drops (or no drops dir at all) is a no-op.

CLI:
    uv run shared/scripts/tools/rebuild_decision_drops_index.py --project-root .
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.decision_drops_index import drop_dir, rebuild_decision_drops_index  # noqa: E402
from lib.file_lock import LockTimeout  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the decision-drops directory's INDEX.md.",
    )
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)

    try:
        path = rebuild_decision_drops_index(Path(args.project_root))
    except (OSError, LockTimeout) as exc:
        print(f"ERROR: could not write INDEX.md: {exc}", file=sys.stderr)
        return 1

    if path is None:
        dd = drop_dir(Path(args.project_root))
        print(f"no decision-drops directory at {dd} - nothing to do")
        return 0
    print(f"regenerated {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
