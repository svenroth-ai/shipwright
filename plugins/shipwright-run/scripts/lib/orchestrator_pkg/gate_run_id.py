"""Which run id the phase gate's canon ``phase_history`` check must find (A5 review).

The canon check ``phase_history[<phase>] has run_id`` matches one run id exactly. In a
driven run the gate used to hand it the RUN's id (``config.runId``, e.g. ``run-1a2b3c4d``),
but the phase skills record their own: project, design and plan mint a fresh
``SHIPWRIGHT_RUN_ID`` at finalization (``design-20261025-101500``), and build, test,
changelog and deploy mint one when it is unset. With enforcement on, every real driven
phase would have been rejected at its first apply, and an unattended run (no override)
could never finish.

The rule, deterministic and narrow. Only entries recorded during THIS task count: written
at or after its claim (``startedAt``), not dated in the future (beyond a small clock-skew
tolerance), and for a split task with no ``split`` or this split. Among those:

1. the run's own id when one of them carries it (a phase-runner exports ``runId``);
2. else the id of the newest of them (a skill that minted its own id);
3. with none, an id no entry can carry (``<runId>:no-phase_history-entry-since-claim``), so
   the check FAILS and says why — returning the bare ``runId`` would let the canon check,
   which matches any entry ever written, pass on an earlier split's or claim's entry.

So an earlier split's entry, the first claim's entry of a recovered task, or another run's
entry never satisfies the check, even under the same id. A task with no parseable
``startedAt`` (not claimed by the driven loop) gets the run's id unchanged: the canon check
then behaves as it does outside a driven run. A ``runId`` that is absent (``None``) or
blank is returned unchanged: the canon bridge owns those answers.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_RUN_CONFIG = "shipwright_run_config.json"
NO_ENTRY_SUFFIX = ":no-phase_history-entry-since-claim"
_SKEW = timedelta(minutes=5)   # clock-skew tolerance for an entry's ``at``


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
    started = _when(task.get("startedAt"))
    if started is None:
        return run_id
    latest = datetime.now(timezone.utc) + _SKEW
    split = task.get("splitId")
    mine = [e for e in bucket
            if isinstance(e, dict) and isinstance(e.get("run_id"), str) and e["run_id"].strip()
            and (at := _when(e.get("at"))) is not None and started <= at <= latest
            and (not split or e.get("split") in (None, split))]
    if any(e["run_id"] == run_id for e in mine):
        return run_id
    return mine[-1]["run_id"] if mine else run_id + NO_ENTRY_SUFFIX
