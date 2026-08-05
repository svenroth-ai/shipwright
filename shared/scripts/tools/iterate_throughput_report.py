#!/usr/bin/env python3
"""Generate the derived iterate-throughput report from ``shipwright_events.jsonl``.

Reproducible entirely from the durable event log — no second metrics store.
Reads every iterate ``work_completed`` event's (optional) ``iterate_timings``
block, computes per-run + rolling stats (``lib.iterate_throughput_stats``),
renders markdown (``lib.iterate_throughput_render``), and atomically writes
``.shipwright/compliance/performance/iterate-throughput.md``.

Called from ``finalize_iterate.py`` at F5b (best-effort, in-process) and
runnable standalone for ad-hoc regeneration:

    uv run shared/scripts/tools/iterate_throughput_report.py --project-root .

This file must NEVER be added to any agent-context-loading path — it is an
operator/WebUI artifact, not a startup input (see the card's storage contract).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.config import read_events  # noqa: E402
from lib.iterate_throughput_render import render_report  # noqa: E402
from lib.iterate_throughput_stats import (  # noqa: E402
    iterate_work_completed_events,
    run_stat,
)

REPORT_RELATIVE_PATH = Path(".shipwright/compliance/performance/iterate-throughput.md")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def compute_report(project_root: Path) -> str:
    """Pure-ish: reads events, returns the rendered markdown. No writes."""
    events = read_events(project_root)
    runs = iterate_work_completed_events(events)
    stats = [run_stat(e) for e in runs]
    return render_report(stats)


def write_report(project_root: Path) -> Path:
    """Compute + atomically write the report. Returns the written path."""
    project_root = Path(project_root)
    text = compute_report(project_root)
    path = project_root / REPORT_RELATIVE_PATH
    _atomic_write(path, text)
    return path


def write_report_best_effort(project_root: Path) -> str | None:
    """``write_report``, swallowing any failure — for callers (finalize_iterate's
    F5b step) that must never be blocked by a report going wrong."""
    try:
        return str(write_report(project_root))
    except Exception as exc:  # noqa: BLE001 — a report must never break finalize
        print(f"[iterate_throughput_report] skipped: {exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the iterate-throughput report")
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)
    path = write_report(Path(args.project_root).resolve())
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
