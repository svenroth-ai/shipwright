"""Append a phase-history entry to ``shipwright_run_config.json``.

Iterate 12.0 (ADR-027) introduces ``phase_history`` as a parallel to
``iterate_history``: a per-phase audit trail of completion events that
phase-specific verifiers (12.1+) can consult without re-parsing
``shipwright_events.jsonl``. iterate continues to write to
``iterate_history`` — the two fields do NOT mirror each other because
iterate has a richer schema (branch, spec path, tests_passed) that
generic phases don't.

Schema:

    {
      "phase_history": {
        "project": [{"run_id": "...", "at": "...", "date": "...", "outcome": "...", "splits": N}],
        "design":  [{"run_id": "...", "at": "...", "date": "...", "screens": N, "flows": M}],
        ...
      }
    }

``at`` is the completion INSTANT (ISO-8601 UTC); ``date`` is the same moment
truncated to a day, kept because readers written before
iterate-2026-07-27-c3-phase-history-join look for it. Until that iterate this
tool stamped ``date`` ALONE, and Canon C3 — which orders a phase's completion
against the handover note's own intra-day timestamp — could not resolve anything
inside a calendar day. It answered "the note came later" for every same-day
comparison, so a phase that skipped its C3 step was reported as legitimately
superseded. A day is not a time; writing one where an instant is meant is what
made the comparison dead on arrival.

Retention: last 50 entries per phase, oldest dropped. Older entries are
preserved only by ``shipwright_events.jsonl`` (authoritative event log).

Usage:

    uv run shared/scripts/tools/append_phase_history.py \\
        --project-root . \\
        --phase build \\
        --run-id build-2026-04-14-foo \\
        --entry-json '{"split": "02-dashboard", "sections": 4}'

The ``--entry-json`` field is merged with the canonical keys
``run_id``, ``at`` and ``date`` so callers don't have to repeat them.

Exit codes:

- 0 — entry appended
- 1 — lock timeout, malformed JSON, or I/O error
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Bootstrap: make lib.file_lock importable when this file is run
# directly via `uv run`.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write, durable_read_text  # noqa: E402
from lib.events_log import latest_event_dt  # noqa: E402
from lib.file_lock import LockTimeout, file_lock  # noqa: E402


RETENTION_PER_PHASE = 50
RUN_CONFIG_NAME = "shipwright_run_config.json"


def append_history(
    project_root: Path,
    phase: str,
    entry: dict[str, Any],
    *,
    retention: int = RETENTION_PER_PHASE,
) -> dict[str, Any]:
    """Read-modify-write on ``shipwright_run_config.json``.

    Caller must hold the lock. Unknown top-level fields are preserved
    verbatim so parallel iterate runs, migrations, or out-of-band edits
    don't get clobbered (GPT R2 writer audit).
    """
    path = project_root / RUN_CONFIG_NAME
    if not path.exists():
        raise FileNotFoundError(
            f"{RUN_CONFIG_NAME} not found at {path} — run config must exist before phase history"
        )

    try:
        # durable_read_text: a concurrent writer's os.replace can leave the
        # entry delete-pending, so a plain open() fails on Windows.
        data = json.loads(durable_read_text(path))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed {RUN_CONFIG_NAME}: {exc}") from exc

    phase_history = data.get("phase_history")
    if not isinstance(phase_history, dict):
        phase_history = {}
        data["phase_history"] = phase_history

    bucket = phase_history.get(phase)
    if not isinstance(bucket, list):
        bucket = []
        phase_history[phase] = bucket

    bucket.append(entry)

    # Retention: keep only the most recent N entries.
    if retention > 0 and len(bucket) > retention:
        dropped = len(bucket) - retention
        del bucket[:dropped]
    else:
        dropped = 0

    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(path, data)

    return {
        "status": "appended",
        "phase": phase,
        "bucket_size": len(bucket),
        "dropped": dropped,
    }


def _atomic_write_json(target: Path, data: dict[str, Any]) -> None:
    """Durable atomic JSON write (tmp + fsync + os.replace via the shared
    :func:`durable_atomic_write`)."""
    durable_atomic_write(target, json.dumps(data, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--phase",
        required=True,
        help="Pipeline phase name (project|design|plan|build|test|changelog|deploy|iterate)",
    )
    parser.add_argument("--run-id", required=True, help="Run id for this phase completion")
    parser.add_argument(
        "--entry-json",
        default="{}",
        help="Additional JSON object merged into the entry (no run_id/at/date collision allowed)",
    )
    parser.add_argument(
        "--retention",
        type=int,
        default=RETENTION_PER_PHASE,
        help=f"Keep last N entries per phase (default {RETENTION_PER_PHASE})",
    )
    parser.add_argument("--lock-timeout", type=float, default=5.0)
    args = parser.parse_args()

    try:
        extra = json.loads(args.entry_json)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid --entry-json: {exc}", file=sys.stderr)
        return 1
    if not isinstance(extra, dict):
        print("ERROR: --entry-json must be a JSON object", file=sys.stderr)
        return 1
    canonical = {"run_id", "at", "event_at", "date"}
    if canonical & set(extra):
        print(
            "ERROR: --entry-json must not set run_id, at, event_at or date "
            "(they are canonical)",
            file=sys.stderr,
        )
        return 1

    project_root = Path(args.project_root).resolve()

    # One `now()`, so `at` and `date` can never name different days.
    completed_at = datetime.now(timezone.utc)
    # `event_at` is the anchor Canon C3 actually compares against, stamped with
    # the SAME function that stamps the handoff's canon marker. `at` is wall
    # clock, and the canon block runs record_event -> marker -> this tool, so
    # `at` is unconditionally LATER than the marker that closed it; comparing
    # those two accused a phase of skipping its C3 step on every re-run where
    # record_event's first-wins dedup meant no fresh event landed. Omitted
    # rather than nulled when the project has no events yet — an absent key is a
    # stated unknown: without it C3 does not consult the clock at all for this
    # phase, which is the right answer for entries written before this key.
    event_dt = latest_event_dt(project_root)
    entry: dict[str, Any] = {
        "run_id": args.run_id,
        "at": completed_at.isoformat(),
        **({"event_at": event_dt.isoformat()} if event_dt is not None else {}),
        "date": completed_at.strftime("%Y-%m-%d"),
        **extra,
    }

    lock_path = (project_root / RUN_CONFIG_NAME).with_suffix(".json.lock")

    try:
        with file_lock(lock_path, timeout_seconds=args.lock_timeout):
            result = append_history(project_root, args.phase, entry, retention=args.retention)
    except LockTimeout as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"entry": entry, **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
