#!/usr/bin/env python3
"""Best-effort emit of a durable phase event via ``record_event.py``.

Thin shared wrapper around the ``record_event.py`` CLI so phase-entry code can
append a ``phase_started`` event to the per-tree ``shipwright_events.jsonl``
without duplicating the subprocess boilerplate. B1/M-Pre-1: the
``phase_started`` event *type* already existed but nothing emitted it, so the
WebUI PhaseRail (concept §5a) had only END timestamps (from
``phase_session_stop``'s ``phase_completed``). This is that event's phase-ENTRY
counterpart.

Never raises — a telemetry write must never crash a phase-entry path.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# lib/ -> shared/scripts ; record_event.py lives in shared/scripts/tools.
_RECORD_EVENT = Path(__file__).resolve().parent.parent / "tools" / "record_event.py"


def emit_phase_event(
    project_root: Path | str,
    event_type: str,
    phase: str,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Append an event via ``record_event.py``. Swallows all failures.

    ``detail`` is JSON-encoded into the event's ``--detail`` string, mirroring
    ``phase_session_stop``'s ``phase_completed`` payload (``phaseTaskId`` /
    ``splitId`` / ``runId``). Additive — no existing event is changed.
    """
    if not _RECORD_EVENT.exists():
        return
    args = [
        sys.executable, str(_RECORD_EVENT),
        "--project-root", str(project_root),
        "--type", event_type,
        "--phase", phase,
    ]
    if detail:
        args.extend(["--detail", json.dumps(detail)])
    try:
        # errors="replace" guards the Windows cp1252 child-output decode
        # landmine: an undecodable byte would otherwise raise UnicodeDecodeError,
        # which the except below does NOT catch — breaking "never raises" and
        # potentially crashing the unwrapped SessionStart-hook caller.
        proc = subprocess.run(
            args, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        # Never raise — but make the miss observable (a swallowed failure would
        # silently drop the event; mirrors single_session.observability).
        sys.stderr.write(f"[phase_event_emit] {event_type} emit failed: {exc}\n")
        return
    if proc.returncode != 0:
        sys.stderr.write(
            f"[phase_event_emit] {event_type} emit exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout or '').strip()[:200]}\n"
        )
