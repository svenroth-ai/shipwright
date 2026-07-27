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

# Owner: shared/schemas/run_config.v2.schema.json → $defs.PhaseTaskStatus
# ("backlog", "awaiting_launch", "in_progress", "done", "failed", "skipped").
# Only these two mean the work is banked. `failed` is terminal but NOT finished,
# and is called out separately below.
FINISHED_STATUSES = frozenset({"done", "skipped"})
INTERRUPTED_STATUS = "in_progress"


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


def _finished_verdict(status: Any) -> str:
    if status in FINISHED_STATUSES:
        return "yes"
    if status == INTERRUPTED_STATUS:
        return "**no — interrupted**"
    if status == "failed":
        return "**no — failed**"
    return "no"


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
                f"- **Currently dispatched**: `{_cell(pointer_id)}` — stale pointer, "
                "no such entry in `phase_tasks[]`"
            )
        else:
            attempt = loop.get("attempt")
            suffix = f", attempt {attempt}" if isinstance(attempt, int) else ""
            lines.append(
                f"- **Currently dispatched**: {_phase_label(pointed)} "
                f"(status `{_cell(pointed.get('status'))}`{suffix})"
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

    finished = [t for t in tasks if t.get("status") in FINISHED_STATUSES]
    interrupted = [t for t in tasks if t.get("status") == INTERRUPTED_STATUS]

    lines = [
        "## Pipeline Phases",
        "",
        "Authoritative per-phase status from `shipwright_run_config.json` → "
        f"`phase_tasks[]`; the dispatch pointer from `{LOOP_STATE_REL_PATH}`. "
        "**A phase that merely STARTED is not finished** — only `done` / "
        "`skipped` count, so an `in_progress` row below is work to pick back up, "
        "not work banked.",
        "",
    ]

    tally = f"- **Finished**: {len(finished)} of {len(tasks)}"
    if finished:
        tally += f" ({', '.join(_cell(t.get('phase')) for t in finished)})"
    lines.append(tally)

    if interrupted:
        lines.extend(
            f"- **Interrupted**: {_phase_label(t)} — started, not finished"
            for t in interrupted
        )
    else:
        lines.append("- **Interrupted**: none — no phase is mid-flight")

    lines.extend(_dispatch_lines(_read_loop_state(Path(project_root)), tasks))
    if (run_config or {}).get("status"):
        lines.append(f"- **Run status**: {_cell(run_config.get('status'))}")

    lines += [
        "",
        "| Phase | Split | Status | Finished? |",
        "|-------|-------|--------|-----------|",
    ]
    lines.extend(
        f"| {_cell(t.get('phase'))} | {_cell(t.get('splitId'))} | "
        f"{_cell(t.get('status'))} | {_finished_verdict(t.get('status'))} |"
        for t in tasks
    )
    lines.append("")
    return lines
