"""Change-history-facing collectors: git log + event log.

* ``git log`` parses conventional commits into ``CommitEntry`` rows.
* ``shipwright_events.jsonl`` is the unified event log; resolution is
  git-worktree-aware so a worktree checkout still reads the main
  repo's canonical log (see ``_resolve_events_path``).

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

import json
import re
import subprocess
import warnings
from pathlib import Path

from ._types import CommitEntry, TestRunEvent, WorkEvent


# ---------------------------------------------------------------------------
# Git History
# ---------------------------------------------------------------------------

_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|refactor|docs|test|chore|style|perf|ci|build)"
    r"(?:\(([^)]+)\))?"
    r":\s*(.+)$"
)


def collect_git_history(project_root: Path) -> list[CommitEntry]:
    """Parse git log for conventional commits."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H|%s|%an|%aI", "--no-merges"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            encoding="utf-8",
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0:
        return []

    commits: list[CommitEntry] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue

        hash_, subject, author, date = parts
        match = _CONVENTIONAL_RE.match(subject)
        if match:
            commits.append(CommitEntry(
                hash=hash_[:12],
                type=match.group(1),
                scope=match.group(2),
                description=match.group(3),
                date=date,
                author=author,
            ))
        else:
            # Non-conventional commits get type "other"
            commits.append(CommitEntry(
                hash=hash_[:12],
                type="other",
                scope=None,
                description=subject,
                date=date,
                author=author,
            ))

    return commits


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

EVENT_FILE = "shipwright_events.jsonl"


def _resolve_events_path(project_root: Path) -> Path:
    """Resolve the path to ``shipwright_events.jsonl`` — ``project_root / EVENT_FILE``.

    The event log is a **per-tree, version-controlled artifact**: the
    ``/shipwright-iterate`` run commits it via F6, so a worktree checkout
    carries its own copy that ships through the PR. Resolution is therefore a
    literal join — from inside a worktree ``project_root`` is the worktree
    root, and that is the copy compliance must read so the F5b regen reflects
    the iterate's just-recorded event (and the F6 commit snapshot is
    self-consistent).

    Standalone-distributable twin of
    ``shared/scripts/lib/events_log.py::resolve_events_path``;
    ``integration-tests/test_events_log_parity.py`` pins them to the same
    answer. Both flipped from a main-repo ``--git-common-dir`` redirect to this
    literal join in iterate-2026-05-29-events-jsonl-worktree-commit (the
    redirect orphaned the work_completed event outside the iterate PR).
    """
    return project_root / EVENT_FILE


def _read_event_log(project_root: Path) -> list[dict]:
    """Read and parse shipwright_events.jsonl. Tolerant of corrupt lines.

    Resolves the per-tree log via ``_resolve_events_path`` (a literal
    ``project_root / EVENT_FILE`` join) so collection from inside a worktree
    reads the worktree's own committed copy — the same file the F5b producer
    wrote and F6 committed.
    """
    path = _resolve_events_path(project_root)
    if not path.exists():
        return []
    events: list[dict] = []
    for i, line in enumerate(path.open("r", encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            warnings.warn(f"Corrupt event at line {i + 1} in {EVENT_FILE}, skipping")
    return events


def _apply_amendments(events: list[dict]) -> list[dict]:
    """Apply event_amended entries to their target events."""
    amendments: dict[str, dict] = {}
    for e in events:
        if e.get("type") == "event_amended":
            amendments[e["amends"]] = e.get("fields", {})

    result: list[dict] = []
    for e in events:
        if e.get("type") == "event_amended":
            continue
        if e.get("id") in amendments:
            e = {**e, **amendments[e["id"]]}
        result.append(e)
    return result


def collect_events(project_root: Path) -> tuple[list[WorkEvent], list[TestRunEvent], list[dict]]:
    """Collect events from the unified event log.

    Returns (work_events, test_runs, phase_events).
    """
    raw = _read_event_log(project_root)
    if not raw:
        return [], [], []

    raw = _apply_amendments(raw)

    work_events = [WorkEvent.from_dict(e) for e in raw if e.get("type") == "work_completed"]
    test_runs = [TestRunEvent.from_dict(e) for e in raw if e.get("type") == "test_run"]
    phase_events = [e for e in raw if e.get("type") in ("phase_started", "phase_completed", "split_completed")]

    return work_events, test_runs, phase_events


def latest_event_timestamp(work_events: list[WorkEvent]) -> str:
    """Return the latest event timestamp formatted for ``ComplianceData.timestamp``.

    Mirrors ``shared/scripts/lib/events_log.latest_event_dt`` but stays
    local to the compliance plugin: the plugin is a distinct
    distributable and cannot import ``shared/scripts/lib`` without a
    cross-plugin path bootstrap (see events_log.py docstring). The
    parity test (TestLatestEventTimestamp in test_data_collector.py)
    pins these two to the same answer for any given input.

    Empty input → ``"(no events)"`` literal so the rendered banner is
    still a deterministic, human-readable token rather than empty
    string.
    """
    if not work_events:
        return "(no events)"
    latest = ""
    for we in work_events:
        ts = we.timestamp
        if isinstance(ts, str) and ts > latest:
            latest = ts
    return latest or "(no events)"
