"""Which run id the phase gate's canon ``phase_history`` check must find (A5 review).

The canon check ``phase_history[<phase>] has run_id`` matches one run id exactly. In a
driven run the gate used to hand it the RUN's id (``config.runId``, e.g. ``run-1a2b3c4d``),
but the phase skills record their own: project, design and plan mint a fresh
``SHIPWRIGHT_RUN_ID`` at finalization (``design-20261025-101500``), and build, test,
changelog and deploy mint one when it is unset. With enforcement on, every real driven
phase would have been rejected at its first apply, and an unattended run (no override)
could never finish.

The rule, deterministic and narrow:

1. the run's own id when ``phase_history[<phase>]`` has an entry for it (unchanged);
2. else the id of the NEWEST entry recorded since THIS task was claimed (``startedAt``)
   — for a split task, one whose ``split`` is absent or names this split;
3. else the run's id, so the check fails and names it.

Rule 2 accepts "the phase wrote its audit entry during this task", which is what the check
exists to prove; an entry from before the claim (an earlier task, another run) never counts.
A task with no parseable ``startedAt`` gets rule 1/3 only. A ``runId`` that is absent
(``None``) or blank is returned unchanged: the canon bridge owns those answers.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_RUN_CONFIG = "shipwright_run_config.json"


def _when(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None   # naive = not comparable


def canon_run_id(project_root: Path, task: dict[str, Any], config: dict[str, Any]) -> Optional[str]:
    """The run id to verify ``task``'s phase against (rules in the module docstring)."""
    run_id = config.get("runId")
    if not isinstance(run_id, str) or not run_id.strip():
        return run_id
    try:
        on_disk = json.loads((project_root / _RUN_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return run_id
    history = on_disk.get("phase_history") if isinstance(on_disk, dict) else None
    bucket = history.get(task.get("phase")) if isinstance(history, dict) else None
    if not isinstance(bucket, list):
        return run_id
    entries = [e for e in bucket if isinstance(e, dict) and isinstance(e.get("run_id"), str)
               and e["run_id"].strip()]
    if any(e["run_id"] == run_id for e in entries):
        return run_id
    started = _when(task.get("startedAt"))
    if started is None:
        return run_id
    split = task.get("splitId")
    since = [e for e in entries
             if (at := _when(e.get("at"))) is not None and at >= started
             and (not split or e.get("split") in (None, split))]
    return since[-1]["run_id"] if since else run_id
