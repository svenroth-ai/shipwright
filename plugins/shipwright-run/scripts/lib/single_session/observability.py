"""Structured observability events for the single-session orchestrator loop (SS5).

Append-only JSONL telemetry at ``.shipwright/run_loop_events.jsonl`` — the loop's
own transition log, DISTINCT from the tracked pipeline ``shipwright_events.jsonl``
and from ``run_loop_state.json``. It is emitted ONLY from single-session code paths
(``single_session_loop`` dispatch/apply + ``single_session_recovery``
resume/gate/recover); a ``multi_session`` run never calls them, so its events file
never appears — the dual-mode back-compat guarantee (SS5, asserted by the back-compat
suite).

Same pure-data discipline as ``loop_state``: this module NEVER mutates
``shipwright_run_config.json`` and NEVER imports ``orchestrator_pkg`` (that would form
an import cycle). It only appends to its own file.

**Single writer.** The one ``/shipwright-run`` master drives every emit serially — the
loop subcommands and the resume/gate/recover subcommands are never called concurrently
for a run. So a plain append (``open("a")`` + ``flush`` + ``fsync``) is the correct,
O(1) form: each line is written whole and durably; only a crash mid-write can leave a
torn TRAILING line, which ``load_events`` skips. (The earlier read+rewrite design was
O(N²) and bought nothing over append for a single writer — dropped after external review.)

**Best-effort.** Telemetry must never crash the pipeline (the authoritative phase state
lives in run_config regardless), so ``emit_event`` swallows IO errors — but writes a
one-line diagnostic to stderr first, so a persistent disk/permission failure is visible
rather than a silent black hole.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

EVENTS_SCHEMA_VERSION = 1
EVENTS_REL_PATH = Path(".shipwright") / "run_loop_events.jsonl"

# The loop's own transitions (reconciled-target observability #7). Closed set —
# ``build_event`` rejects anything else so a typo never lands an unqueryable event.
LOOP_EVENT_TYPES = (
    "dispatch",           # a phase task was (re)dispatched to a phase-runner subagent
    "phase_result",       # a phase-runner result was applied (ok true|false)
    "strict_stop",        # an ok=false result halted the run (no successor planned)
    "human_gate_pause",   # the loop paused at an orchestrator-approve / hard-stop gate
    "human_gate_resume",  # the human released the gate; the loop continues
    "resume",             # the master re-entered a dead run and confirmed resume
    "recovery",           # recover-phase-task cleared a wedged task in-loop
)


def events_path(project_root: Path) -> Path:
    """Canonical run-loop events path for a project."""
    return Path(project_root) / EVENTS_REL_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event(event_type: str, run_id: str, **fields: Any) -> dict[str, Any]:
    """Build one structured event.

    Validates ``event_type`` against ``LOOP_EVENT_TYPES`` (raises ``ValueError`` like
    ``loop_state.set_status`` — a bad type is a programming error and fails at the call
    site, never a silent unqueryable event). ``fields`` are small structured extras
    (identifiers/status only — callers whitelist; never a full context/summary blob).
    """
    if event_type not in LOOP_EVENT_TYPES:
        raise ValueError(
            f"invalid loop event type {event_type!r}; expected one of "
            f"{', '.join(LOOP_EVENT_TYPES)}"
        )
    event: dict[str, Any] = {
        "schemaVersion": EVENTS_SCHEMA_VERSION,
        "event": event_type,
        "runId": run_id,
        "at": _now_iso(),
    }
    event.update(fields)
    return event


def load_events(project_root: Path) -> list[dict[str, Any]]:
    """Read every event (malformed lines skipped). Empty list when the file is absent.

    Corrupt-line tolerance is deliberate: with append emission only a crash mid-write can
    truncate the LAST line, so skipping malformed lines loses at most the final in-flight
    event and never blocks reading the rest. Telemetry, not authority.
    """
    path = events_path(project_root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            events.append(json.loads(stripped))
        except ValueError:
            continue
    return events


def emit_event(project_root: Path, event: dict[str, Any]) -> None:
    """Append ``event`` as one JSONL line — durably (append + flush + fsync), best-effort.

    A whole line is written in one call so a concurrent reader never sees a partial line;
    ``fsync`` puts it on stable storage before returning (resumability wants the last event
    to survive a crash). Any IO error is swallowed so a telemetry failure never crashes the
    loop — but a diagnostic is written to stderr first so a persistent failure stays visible.
    """
    try:
        path = events_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except (OSError, TypeError, ValueError) as exc:  # noqa: BLE001 — best-effort, not silent
        # OSError = disk/permission; TypeError/ValueError = a non-serializable field slipped
        # past the whitelist. Either way, drop the event rather than crash the loop.
        sys.stderr.write(
            f"[single-session] observability emit failed ({event.get('event')!r}): {exc}\n"
        )


def emit(project_root: Path, *, event_type: str, run_id: str, **fields: Any) -> None:
    """``build_event`` + ``emit_event`` convenience for compact loop call sites.

    A bad ``event_type`` still raises (programming error surfaces in tests); an IO error
    is swallowed by ``emit_event`` (never propagates to the loop).
    """
    emit_event(project_root, build_event(event_type, run_id, **fields))


# --- typed emitters for the orchestrator loop's two emit points ---------------
# The loop keeps these one-line so ``single_session_loop`` stays lean; the event
# field-mapping (and the phase_result/strict_stop pairing) lives here with the schema.


def emit_dispatch(
    project_root: Path, *, run_id: str, dispatch: dict[str, Any],
    attempt: int, idempotent: bool,
) -> None:
    """Emit a ``dispatch`` event from a dispatch descriptor (identifiers only)."""
    emit(
        project_root, event_type="dispatch", run_id=run_id,
        phaseTaskId=dispatch.get("phaseTaskId"), phase=dispatch.get("phase"),
        splitId=dispatch.get("splitId"), attempt=attempt, idempotent=idempotent,
    )


def emit_phase_result(
    project_root: Path, *, run_id: str, phase_task_id: str, phase: Optional[str],
    run_status: Optional[str], failed: bool, reason: Optional[str] = None,
) -> None:
    """Emit a ``phase_result`` event; a FAILED result also emits ``strict_stop`` — the
    ok=false-halts-the-run pairing, encapsulated in one place."""
    emit(
        project_root, event_type="phase_result", run_id=run_id,
        phaseTaskId=phase_task_id, phase=phase, ok=not failed, runStatus=run_status,
    )
    if failed:
        emit(
            project_root, event_type="strict_stop", run_id=run_id,
            phaseTaskId=phase_task_id, phase=phase, reason=reason,
        )
