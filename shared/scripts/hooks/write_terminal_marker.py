#!/usr/bin/env python3
"""Stop hook: write terminal marker for autonomous loop synchronization.

When SHIPWRIGHT_LOOP_ID and SHIPWRIGHT_LOOP_UNIT_ID are set, writes a
DONE file at .shipwright/runs/<loop_id>/<unit_id>/DONE. The parent loop
polls for this file after Task-return to ensure all Stop-hooks have
completed before transitioning unit state.

Must be registered as the LAST Stop hook in hooks.json.
No-op when loop env vars are not set (normal sessions).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    loop_id = os.environ.get("SHIPWRIGHT_LOOP_ID")
    unit_id = os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID")

    if not loop_id or not unit_id:
        return 0

    marker_dir = Path(".shipwright") / "runs" / loop_id / unit_id
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / "DONE").write_text("", encoding="utf-8")

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": f"Terminal marker written: .shipwright/runs/{loop_id}/{unit_id}/DONE",
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
