"""Pipeline phase status for the generated session handoff.

FR-01.01 (E): *"…the document a person reads on returning states which phases are
finished and which one was interrupted — the run already knows this; the point is
that the person is told without having to ask."*

Nothing here builds resume state. The run is already resumable; both inputs
already exist and are already authoritative:

  * ``run_config["phase_tasks"]`` — the per-phase status, mutated ONLY through
    ``phase_task_lifecycle``.
  * ``.shipwright/run_loop_state.json`` — which phase task the orchestrator has
    dispatched, the attempt count, and the loop status.

``single_session_recovery.resume_run`` already reads both to decide a resume.
This renders the same two facts for the person, whom the handoff previously told
only what had *completed* (counted from the event log) and nothing about what was
interrupted.

Sibling: ``handoff_iterate.py`` fills the equivalent gap for an ITERATE run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Owner: plugins/shipwright-run/scripts/lib/single_session/loop_state.py
# (LOOP_STATE_REL_PATH). Duplicated rather than imported — `shared/` must not
# import from a plugin. The duplication is not on trust:
# integration-tests/test_handoff_reads_real_loop_state.py imports the owner's
# constant and asserts the two agree, so a rename over there fails a test here
# instead of silently blanking these lines.
LOOP_STATE_REL_PATH = ".shipwright/run_loop_state.json"

from lib.handoff_phase_status import (
    FAILED_STATUSES,
    FINISHED_STATUSES,
    INTERRUPTED_STATUSES,
    TERMINAL_STATUSES,
    finished_verdict as _finished_verdict,
    status_of as _status_of,
)

def _cell(value: Any) -> str:
    """Render one markdown table cell: single-line and delimiter-safe.

    Phase and split ids come from JSON written by another component; an embedded
    newline or ``|`` would silently break the table and hide a row rather than
    show a bad one.
    """
    if value is None or value == "":
        return "—"
    return " ".join(str(value).split()).replace("|", "\\|")


def _read_loop_state(project_root: Path) -> dict[str, Any]:
    """The orchestrator's dispatch pointer, or ``{}`` if it cannot be read.

    Degrades on every failure mode rather than taking the handoff down with it:
    the file is absent before the first dispatch, and the loop rewrites it while
    this may be reading, so a partial read (``JSONDecodeError``, a ``ValueError``
    subclass) is expected rather than exceptional.
    """
    try:
        data = json.loads(
            (Path(project_root) / LOOP_STATE_REL_PATH).read_text(encoding="utf-8"),
        )
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _phase_label(task: dict[str, Any]) -> str:
    phase = f"`{_cell(task.get('phase'))}`"
    split = task.get("splitId")
    return f"{phase} (split `{_cell(split)}`)" if split else phase


def _plain_label(task: dict[str, Any]) -> str:
    """Phase + split, unquoted — for the comma-joined finished list.

    The split is NOT optional here. Rendering bare phase names made a multi-split
    run read as ``Finished: … build`` while the Interrupted line simultaneously
    named ``build (split 02)`` — the same phase listed as both finished and
    unfinished, with no way to tell which split was which.
    """
    phase = _cell(task.get("phase"))
    split = task.get("splitId")
    return f"{phase} (split {_cell(split)})" if split else phase


def _expected_total(run_config: dict[str, Any], tasks: list[dict[str, Any]]) -> int:
    """How many phase tasks this run will end up with.

    NOT ``len(phase_tasks)`` — those are materialised one at a time, so counting
    against them made a run one phase into seven read as "1 of 2".

    NOT ``len(pipeline)`` either: ``phase_state_machine.next_phase_task`` expands
    ``plan`` and ``build`` once per frozen split, so a 3-split run has 4 extra
    tasks. Denominating against the bare pipeline made a 3-split run that had
    finished plan+build for every split render "8 of 8" — a categorical
    100%-complete claim with test, changelog and deploy still unplanned.

    ``splits_frozen`` is a REQUIRED v2 field and is already in the dict we were
    handed. ``max`` with the planned count keeps the answer honest for any shape
    this arithmetic does not anticipate — but only AFTER the extra task exists, so
    the known off-pipeline case is counted explicitly rather than left to it.
    """
    pipeline = run_config.get("pipeline")
    if not isinstance(pipeline, list):
        return len(tasks)
    splits = run_config.get("splits_frozen")
    extra_per_split = 2 * max(0, len(splits) - 1) if isinstance(splits, list) else 0
    # A phase that exists as a task but not in `pipeline` — `legacy_migration`
    # drops `security` from the pipeline while leaving its phase task in place,
    # and the state machine keeps the legacy security -> changelog edge. Without
    # this the run reads "6 of 7" with two phases still unplanned.
    off_pipeline = {t.get("phase") for t in tasks} - set(pipeline)
    return max(len(pipeline) + extra_per_split + len(off_pipeline), len(tasks))


def _dispatch_lines(loop: dict[str, Any], tasks: list[dict[str, Any]]) -> list[str]:
    """The loop-pointer lines, resolved against ``phase_tasks``.

    An unresolvable pointer is labelled stale rather than asserted as the current
    phase: loop state and run config are separate files, and a pointer naming a
    task that is not in ``phase_tasks`` means one of them is behind.
    """
    pointer_id = loop.get("currentPhaseTaskId")
    lines: list[str] = []
    if pointer_id:
        pointed = next((t for t in tasks if t.get("phaseTaskId") == pointer_id), None)
        if pointed is None:
            lines.append(
                f"- **Dispatch pointer**: `{_cell(pointer_id)}` — stale pointer, "
                "no such entry in `phase_tasks[]`"
            )
        else:
            status = _status_of(pointed)
            shown = _cell(status) if status else "unknown"
            attempt = loop.get("attempt")
            counted = (
                isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 1
            )
            # THE TASK'S OWN STATUS DECIDES — never the attempt counter.
            #
            # The pointer alone proves nothing: `advance_pointer` moves it to the
            # SUCCESSOR and resets attempt to 0 after every completed phase, so
            # "pointer set" is the normal between-phases state.
            #
            # And the counter proves nothing either. It records that a dispatch
            # HAPPENED, not that one is live: `recover-phase-task --force-status
            # awaiting_launch` (the default, and exempt from the drivability
            # guard) releases the claim without touching run_loop_state.json, so a
            # recovered task keeps attempt >= 1. Treating a counted attempt as
            # evidence printed "Currently dispatched: `build` (status
            # `awaiting_launch`, attempt 2)" — a line that contradicts itself, one
            # recovery after the claim was released.
            #
            # So: `in_progress` is dispatched (the lifecycle sets it under CAS at
            # claim time), terminal is finished-or-dead, everything else is
            # pending. The counter only decorates a dispatch we already believe in.
            if status in TERMINAL_STATUSES:
                lines.append(
                    f"- **Dispatch pointer**: {_phase_label(pointed)} "
                    f"(status `{shown}`) — terminal; the loop has not moved on yet"
                )
            elif status in INTERRUPTED_STATUSES:
                suffix = f", attempt {attempt}" if counted else ""
                lines.append(
                    f"- **Currently dispatched**: {_phase_label(pointed)} "
                    f"(status `{shown}`{suffix})"
                )
            else:
                lines.append(
                    f"- **Next up**: {_phase_label(pointed)} (status `{shown}`) "
                    "— pointed at, not yet dispatched"
                )
    if loop.get("status"):
        lines.append(f"- **Loop status**: {_cell(loop.get('status'))}")
    return lines


def render_pipeline_phases(
    project_root: Path | str, run_config: dict[str, Any] | None,
) -> list[str]:
    """Render the authoritative per-phase pipeline status, or ``[]``.

    Returns an empty list — no heading, no placeholder rows — when the config has
    no ``phase_tasks[]``, which is every legacy / standalone / adopted run. The
    handoff for those projects is byte-identical to before.
    """
    raw = (run_config or {}).get("phase_tasks")
    if not isinstance(raw, list):
        return []
    tasks = [t for t in raw if isinstance(t, dict)]
    if not tasks:
        return []

    finished = [t for t in tasks if _status_of(t) in FINISHED_STATUSES]
    interrupted = [t for t in tasks if _status_of(t) in INTERRUPTED_STATUSES]
    failed = [t for t in tasks if _status_of(t) in FAILED_STATUSES]

    total = _expected_total(run_config or {}, tasks)

    lines = [
        "## Pipeline Phases",
        "",
        "Authoritative per-phase status from `shipwright_run_config.json` → "
        f"`phase_tasks[]`; the dispatch pointer from `{LOOP_STATE_REL_PATH}`. "
        "**A phase that merely STARTED is not finished** — only `done` / "
        "`skipped` count, so an `in_progress` row below is work to pick back up, "
        "not work banked. Phase tasks are **planned incrementally** (each one is "
        "created as its predecessor completes), so the table lists what has been "
        "planned so far, not the whole run.",
        "",
    ]

    tally = f"- **Finished**: {len(finished)} of {total}"
    if finished:
        tally += f" ({', '.join(_plain_label(t) for t in finished)})"
    lines.append(tally)

    if interrupted:
        lines.extend(
            f"- **Interrupted**: {_phase_label(t)} — started, not finished"
            for t in interrupted
        )
    else:
        lines.append("- **Interrupted**: none — no phase is mid-flight")

    # A failed task is terminal but NOT finished, so it appeared in no bullet at
    # all: a run that died at build rendered "Interrupted: none" — "nothing to
    # pick up" for a dead run.
    lines.extend(
        f"- **Failed**: {_phase_label(t)} — terminal, not finished" for t in failed
    )

    lines.extend(_dispatch_lines(_read_loop_state(Path(project_root)), tasks))
    if (run_config or {}).get("status"):
        lines.append(f"- **Run status**: {_cell(run_config.get('status'))}")

    lines += [
        "",
        "| Phase | Split | Status | Finished? |",
        "|-------|-------|--------|-----------|",
    ]
    for t in tasks:
        status = _status_of(t)
        lines.append(
            f"| {_cell(t.get('phase'))} | {_cell(t.get('splitId'))} | "
            f"{_cell(status) if status else 'unknown'} | {_finished_verdict(status)} |"
        )
    lines.append("")
    return lines
