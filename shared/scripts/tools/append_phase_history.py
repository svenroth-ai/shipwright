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
        "project": [{"run_id": "...", "date": "...", "outcome": "...", "splits": N}],
        "design":  [{"run_id": "...", "date": "...", "screens": N, "flows": M}],
        ...
      }
    }

Retention: last 50 entries per phase, oldest dropped. Older entries are
preserved only by ``shipwright_events.jsonl`` (authoritative event log).

Usage:

    uv run shared/scripts/tools/append_phase_history.py \\
        --project-root . \\
        --phase build \\
        --run-id build-2026-04-14-foo \\
        --entry-json '{"split": "02-dashboard", "sections": 4}'

The ``--entry-json`` field is merged with the canonical keys
``run_id`` and ``date`` so callers don't have to repeat them.

Exit codes:

- 0 — entry appended
- 1 — lock timeout, malformed JSON, or I/O error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Bootstrap: make lib.file_lock importable when this file is run
# directly via `uv run`.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

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
        data = json.loads(path.read_text(encoding="utf-8"))
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
    content = json.dumps(data, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
        help="Additional JSON object merged into the entry (no run_id/date collision allowed)",
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
    if "run_id" in extra or "date" in extra:
        print("ERROR: --entry-json must not set run_id or date (they are canonical)", file=sys.stderr)
        return 1

    entry: dict[str, Any] = {
        "run_id": args.run_id,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        **extra,
    }

    project_root = Path(args.project_root).resolve()
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
