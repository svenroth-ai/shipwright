"""Change-history-facing collectors: git log + event log.

* ``git log`` parses conventional commits into ``CommitEntry`` rows.
* ``shipwright_events.jsonl`` is the unified event log; resolution is
  git-worktree-aware so a worktree checkout still reads the main
  repo's canonical log (see ``_resolve_events_path``).

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

import re
import subprocess
import warnings
from pathlib import Path

from ._lib_loader import load_shared_lib
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

    RECORD BOUNDARIES (iterate-2026-07-19-…-readers). Several records may share
    one physical line: ``shipwright_events.jsonl`` carries ``merge=union``, union
    merge is line-based, and so an ordinary merge of two worktrees joins an
    unterminated blob's last line to the next side's first line. The previous
    line-at-a-time parse discarded EVERY record on such a line, which on an
    append-only audit trail makes a step that happened read as one that never
    did. Recovery delegates to the shared SSoT ``lib/jsonl_records`` — reached
    via ``load_shared_lib`` because a bare ``from lib import jsonl_records``
    resolves to THIS plugin's own ``lib`` package and raises ImportError
    (ADR-045).

    The warning is kept (this site warns today) but reports only WHERE and HOW
    MUCH — never the fragment text, which would echo raw event data into CI logs.
    The old ``path.open(...)`` also leaked its file handle on every read; the
    shared reader uses a context manager.
    """
    path = _resolve_events_path(project_root)
    if not path.exists():
        return []
    result = load_shared_lib("jsonl_records").read_jsonl_records(path)
    for frag in result.corrupt:
        # ASCII-only: surfaces on Windows cp1252 consoles.
        warnings.warn(
            f"Corrupt event at {EVENT_FILE}:{frag.line_no} "
            f"({len(frag.text)} bytes unrecoverable), skipping that fragment"
        )
    return list(result.records)


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


#: Rendered in the ``Generated:`` banner when no event has a usable timestamp.
#: A deterministic, human-readable token rather than an empty string.
NO_EVENTS = "(no events)"

#: ``adr_id`` is dual-purpose: ``finalize_iterate`` stores the iterate run id there,
#: but ``record_event.py`` documents ``--adr-id`` as an ADR reference ("ADR-055") and
#: build-phase events use it that way. Without this guard a build-phase newest event
#: renders ``Source-State: run=ADR-055`` — naming a decision record as a run.
_ADR_REF_RE = re.compile(r"^ADR-\d+$", re.IGNORECASE)


def run_id_of(event: WorkEvent | None) -> str | None:
    """Run id recorded on ``event``, or ``None`` when it carries an ADR ref instead.

    ``None`` is the honest answer here: the renderers turn it into ``run=(unknown)``,
    which is true, rather than printing an ADR id under a field labelled ``run``.

    **What the resulting stamp does and does not mean.** It names the newest *recorded
    completed change* at render time — which for the iterate producer IS the current
    run, because ``finalize_iterate`` records ``work_completed`` before regenerating.
    For the two producers that regenerate these documents outside an iterate (a
    ``chore(release)`` commit, and the security phase's Step 7.5 finalizer) the newest
    recorded change is the *previous* iterate's, so the banner names that run, not the
    regeneration. Reading it as "the tree this file was rendered from" would therefore
    be wrong. Adding HEAD to the compliance banner is not the fix: a per-commit field
    would change on every commit and re-open the permanently-dirty tracked-markdown
    defect that deterministic render timestamps were introduced to close.
    """
    if event is None:
        return None
    value = (event.adr_id or "").strip()
    if not value or _ADR_REF_RE.match(value):
        return None
    return value


def latest_work_event(work_events: list[WorkEvent]) -> WorkEvent | None:
    """Return the chronologically-latest work event, or ``None``.

    The single resolver behind BOTH provenance header lines a compliance document
    carries: ``Generated:`` (this event's timestamp) and ``Source-State:`` (this
    event's ``adr_id``, which is where the run id travels — see
    ``finalize_iterate.py``, "storing run_id as adr_id").

    One event object, read once, on purpose. Resolving the timestamp and the run id
    through two independent "latest" queries would let a document's two header
    lines describe two different events, which is precisely the confusion the
    stamp exists to remove (card ``trg-4d5b6a56``; external review, edge-case/high).

    Returns ``None`` when no event has a usable timestamp, mirroring
    :func:`latest_event_timestamp`'s ``"(no events)"`` fallback rather than picking
    an arbitrary event — the two must not diverge.
    """
    latest: WorkEvent | None = None
    latest_ts = ""
    for we in work_events or []:
        ts = we.timestamp
        if isinstance(ts, str) and ts > latest_ts:
            latest_ts, latest = ts, we
    return latest


def latest_event_timestamp(work_events: list[WorkEvent]) -> str:
    """Return the latest event timestamp formatted for ``ComplianceData.timestamp``.

    Mirrors ``shared/scripts/lib/events_log.latest_event_dt`` but stays
    local to the compliance plugin: the plugin is a distinct
    distributable and cannot import ``shared/scripts/lib`` without a
    cross-plugin path bootstrap (see events_log.py docstring). The
    parity test (TestLatestEventTimestamp in test_data_collector.py)
    pins these two to the same answer for any given input.

    Empty input → :data:`NO_EVENTS` so the rendered banner is
    still a deterministic, human-readable token rather than empty
    string.

    Delegates to :func:`latest_work_event` so the timestamp and the run id in
    ``Source-State:`` are guaranteed to come off the same event.
    """
    latest = latest_work_event(work_events)
    return latest.timestamp if latest is not None else NO_EVENTS
