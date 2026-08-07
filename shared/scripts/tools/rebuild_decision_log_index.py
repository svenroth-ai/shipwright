#!/usr/bin/env python3
"""Regenerate ``.shipwright/agent_docs/decision_log_index.md``. Nothing else.

Mirrors ``rebuild_adr_index.py``: the command named by the drift guard, the
generated header, and every best-effort refresh failure. A repo with no
``decision_log.md`` is a no-op, not an error.

CLI:
    uv run shared/scripts/tools/rebuild_decision_log_index.py --project-root .
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.decision_log_index import DECISION_LOG_PATH, rebuild_decision_log_index  # noqa: E402
from lib.file_lock import LockTimeout  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate .shipwright/agent_docs/decision_log_index.md.",
    )
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)

    try:
        path = rebuild_decision_log_index(Path(args.project_root))
    except (OSError, LockTimeout) as exc:
        print(f"ERROR: could not write decision_log_index.md: {exc}", file=sys.stderr)
        return 1

    if path is None:
        print(f"no {DECISION_LOG_PATH} in this checkout - nothing to do")
        return 0
    print(f"regenerated {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
