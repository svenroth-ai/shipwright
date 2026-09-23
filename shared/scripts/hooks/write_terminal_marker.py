#!/usr/bin/env python3
"""Stop hook: write terminal marker for autonomous loop synchronization.

When SHIPWRIGHT_LOOP_ID and SHIPWRIGHT_LOOP_UNIT_ID are set, writes a
DONE file at .shipwright/runs/<loop_id>/<unit_id>/DONE. The parent loop
polls for this file after Task-return to ensure all Stop-hooks have
completed before transitioning unit state.

Must be registered as the LAST Stop hook in hooks.json.
No-op when loop env vars are not set (normal sessions), and no-op under
the campaign-dag-scheduler R5a wave sentinel (`SHIPWRIGHT_LOOP_UNIT_ID ==
"__campaign_wave__"`): every unit in a wave shares that one value, so a
literal write would put N concurrent sub-iterate-runners' Stop hooks on the
SAME shared path, and nothing polls for it any more (`campaign-mode.md`
step 3d retired the terminal-marker wait for `kind == "sub_iterate"` in
favor of the Task call itself blocking until every runner returns).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.campaign_wave import is_wave_sentinel  # noqa: E402


def main() -> int:
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    loop_id = os.environ.get("SHIPWRIGHT_LOOP_ID")
    unit_id = os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID")

    if not loop_id or not unit_id or is_wave_sentinel(unit_id):
        return 0

    marker_dir = Path(".shipwright") / "runs" / loop_id / unit_id
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / "DONE").write_text("", encoding="utf-8")

    # The DONE file on disk is the actual signal the loop polls for.
    # Stop hookSpecificOutput cannot carry additionalContext (ADR-042);
    # log diagnostic to stderr.
    sys.stderr.write(
        f"[shipwright:loop] terminal marker written: "
        f".shipwright/runs/{loop_id}/{unit_id}/DONE\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
