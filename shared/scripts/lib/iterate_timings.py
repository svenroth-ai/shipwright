#!/usr/bin/env python3
"""Hierarchical iterate-timing spans — catalog + sidecar writers (measurement only).

Separate, richer sibling of ``iterate_phase_groups.py`` (the 5-group
``phase_timings`` system, which this file does NOT replace or alter).  Where
``phase_timings`` records five flat boundary marks, this module records a
tree of named spans across the WHOLE iterate lifecycle — discovery through
delivery — distinguishing producer-timed spans (a real OS process brackets
its own start/end) from agent-emitted marks (no process owns the boundary,
so the calling session marks it as the boundary is crossed).

Read-side (normalization + the ``work_completed.iterate_timings`` fold) lives
in the sibling ``iterate_timings_normalize.py`` — this file is the write path
only, kept under the file-size guideline. That includes the counted-
resolution variant (:func:`record_producer_span_counted`): its tolerant
sidecar read exists only to resolve ``attempt`` atomically alongside the
write it performs in the same locked critical section, never to normalize
or fold data for a reader.

Boundary (touches_io_boundary):
    Producer: either a Shipwright script self-instrumenting via
              :func:`span` / :func:`record_producer_span`, or the agent via
              ``iterate_timing.py start|end`` (SKILL boundary calls).
    File:     ``<run_id>.iterate_timings.jsonl`` — GITIGNORED transient run
              state, sibling of ``<run_id>.phase_timings.jsonl``.
    Consumer: ``finalize_iterate`` -> ``work_completed.iterate_timings`` ->
              ``iterate_throughput_report.py`` -> derived markdown.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# This module is imported under both `lib.iterate_timings` (files that put
# shared/scripts on sys.path) and `scripts.lib.iterate_timings`
# (run_test_suite.py's own convention, which only adds shared/) — a package-
# relative `from lib.file_lock import ...` only resolves under the former.
# Self-inserting this file's own directory makes the plain sibling import
# work under either caller convention.
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from file_lock import FileLock  # noqa: E402
# Re-exported for existing callers (iterate_timings_pairing.py,
# iterate_timing.py, tests) — the validation BODY lives in the split-out leaf
# module below; this stays the public entry point for the write path.
from iterate_timings_extra import (  # noqa: E402, F401
    EXTRA_FIELD_TYPES,
    IterateTimingError,
    validate_extra,
)
# Catalog (span-name SSoT) + name/parent validation split out at the same
# ~300-line guideline (test-phase-attribution) — re-exported below for
# existing callers exactly like the iterate_timings_extra import above.
from iterate_timings_catalog import (  # noqa: E402, F401
    FOLD_TIME_CAPTURABLE_SPANS,
    OUTCOMES,
    SOURCES,
    SPAN_NAMES,
    SPAN_PARENTS,
    TOP_LEVEL_SPANS,
    validate_name_parent,
)


def sidecar_path(project_root, run_id: str) -> Path:
    """On-disk location of the iterate-timings sidecar for ``run_id``.

    ``Path(run_id).name`` strips any directory components so a crafted
    run_id cannot escape the iterates directory — mirrors
    ``iterate_phase_groups.sidecar_path``.
    """
    safe = Path(str(run_id)).name
    return (
        Path(project_root) / ".shipwright" / "agent_docs" / "iterates"
        / f"{safe}.iterate_timings.jsonl"
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_line_unlocked(path: Path, obj: dict) -> None:
    """The raw append, with no locking of its own — callers hold the lock
    for the region this sits inside (either just this write, via
    :func:`_append_line`, or a read-then-write region, via
    :func:`record_producer_span_counted`)."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def _append_line(project_root, run_id: str, obj: dict) -> Path:
    """Append one line under the run's lock — the same serialization
    ``record_event.py``/``triage.py`` use for their own JSONL append-logs.
    Multiple producers CAN legitimately write within one run (F0, external
    review, delivery), so an unlocked append risks interleaved writes,
    especially on Windows where append-mode alone isn't atomic."""
    path = sidecar_path(project_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(path.with_name(path.name + ".lock")):
        _write_line_unlocked(path, obj)
    return path


def _span_obj(*, name: str, parent: str | None, attempt: int, source: str, outcome: str,
              start_utc: str, end_utc: str | None, duration_ms: int | None,
              extra: dict) -> dict:
    """The one span-shaped dict both span writers below produce — kept in one
    place so the two write paths (locked-then-append vs. locked-read-then-
    append) cannot drift on the object they write (external code review)."""
    return {
        "event": "span", "name": name, "parent": parent, "attempt": int(attempt),
        "source": source, "outcome": outcome, "start_utc": start_utc,
        "end_utc": end_utc, "duration_ms": duration_ms, "extra": extra,
    }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def record_start(project_root, run_id: str, *, name: str, parent: str | None,
                  attempt: int = 1, ts: str | None = None) -> Path:
    """Agent-emitted: mark entering ``name`` right now (no process owns the boundary)."""
    validate_name_parent(name, parent)
    return _append_line(project_root, run_id, {
        "event": "start", "name": name, "parent": parent, "attempt": int(attempt),
        "ts": ts or _now_iso(),
    })


def record_end(project_root, run_id: str, *, name: str, parent: str | None,
                attempt: int = 1, outcome: str = "completed",
                extra: dict | None = None, ts: str | None = None) -> Path:
    """Agent-emitted: mark leaving ``name`` right now."""
    validate_name_parent(name, parent)
    if outcome not in OUTCOMES:
        raise IterateTimingError(f"unknown outcome {outcome!r}")
    clean_extra = validate_extra(extra)
    return _append_line(project_root, run_id, {
        "event": "end", "name": name, "parent": parent, "attempt": int(attempt),
        "outcome": outcome, "extra": clean_extra, "ts": ts or _now_iso(),
    })


def record_producer_span(project_root, run_id: str, *, name: str, parent: str | None,
                          start_utc: str, end_utc: str | None, duration_ms: int | None,
                          attempt: int = 1, outcome: str = "completed",
                          source: str = "producer", extra: dict | None = None) -> Path:
    """A real process brackets its own start/end and records ONE atomic line."""
    validate_name_parent(name, parent)
    if outcome not in OUTCOMES:
        raise IterateTimingError(f"unknown outcome {outcome!r}")
    if source not in SOURCES:
        raise IterateTimingError(f"unknown source {source!r}")
    clean_extra = validate_extra(extra)
    obj = _span_obj(name=name, parent=parent, attempt=attempt, source=source, outcome=outcome,
                    start_utc=start_utc, end_utc=end_utc, duration_ms=duration_ms,
                    extra=clean_extra)
    return _append_line(project_root, run_id, obj)


def _tolerant_read_lines(path: Path) -> list[dict]:
    """Minimal JSONL parse for this run's own sidecar. Missing file -> ``[]``,
    a malformed line is skipped, never raised — the counted resolver below
    must never fail a first-ever invocation (no sidecar yet) or a run with
    one bad line ahead of it. A deliberate, small duplication of
    ``iterate_timings_normalize.read_raw_events``'s tolerant-read shape
    rather than an import of it: that module imports THIS one, so importing
    back would cycle."""
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (RecursionError, ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def record_producer_span_counted(project_root, run_id: str, *, name: str, parent: str | None,
                                  start_utc: str, end_utc: str | None, duration_ms: int | None,
                                  outcome: str = "completed", source: str = "producer",
                                  extra: dict | None = None,
                                  count_prior: Callable[[list[dict]], int]) -> tuple[Path, int]:
    """Resolve ``attempt`` from ``count_prior`` and append this span, atomically.

    A caller-side "count, then call :func:`record_producer_span`" is NOT
    atomic across two OS processes: that function acquires and releases its
    own lock internally, so the count and the write are two separate
    critical sections with a gap between them a concurrent process can land
    in. This function closes that gap by doing both under ONE lock
    acquisition: a tolerant read of this run's existing sidecar entries,
    ``attempt = count_prior(entries) + 1``, then the validated append —
    mirroring :func:`record_producer_span`'s own validation exactly, just
    with the attempt resolved from inside the lock instead of passed in.
    ``count_prior`` is the caller's own policy (e.g. "the max of several
    per-stage counts") — this function stays span-shape-agnostic, matching
    the rest of this module. Returns ``(path, attempt)`` only once the
    append has durably succeeded; on any failure (bad extra, count_prior
    raising, disk error) nothing is written and the exception propagates —
    callers that must never break their own process wrap this the same way
    every other call in this module is already wrapped at its call sites.
    """
    validate_name_parent(name, parent)
    if outcome not in OUTCOMES:
        raise IterateTimingError(f"unknown outcome {outcome!r}")
    if source not in SOURCES:
        raise IterateTimingError(f"unknown source {source!r}")
    clean_extra = validate_extra(extra)
    path = sidecar_path(project_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(path.with_name(path.name + ".lock")):
        prior_entries = _tolerant_read_lines(path)
        attempt = int(count_prior(prior_entries)) + 1
        obj = _span_obj(name=name, parent=parent, attempt=attempt, source=source,
                        outcome=outcome, start_utc=start_utc, end_utc=end_utc,
                        duration_ms=duration_ms, extra=clean_extra)
        _write_line_unlocked(path, obj)
    return path, attempt


@contextmanager
def span(project_root, run_id: str, *, name: str, parent: str | None,
         attempt: int = 1, source: str = "producer"):
    """Bracket a real producer boundary. Yields a mutable ``extra`` dict.

    Best-effort: a failure while RECORDING the span (bad project_root, disk
    full, an invalid ``extra`` key the caller set) is swallowed and printed to
    stderr — it must never fail the wrapped work. An exception raised INSIDE
    the ``with`` block is re-raised unchanged after marking the span
    ``incomplete``; this context manager never masks a real failure.
    """
    extra: dict = {}
    start_dt = datetime.now(timezone.utc)
    t0 = time.monotonic()
    outcome = "completed"
    try:
        yield extra
    except BaseException:
        outcome = "incomplete"
        raise
    finally:
        end_dt = datetime.now(timezone.utc)
        duration_ms = max(0, int((time.monotonic() - t0) * 1000))
        try:
            record_producer_span(
                project_root, run_id, name=name, parent=parent, attempt=attempt,
                source=source, outcome=outcome, start_utc=start_dt.isoformat(),
                end_utc=end_dt.isoformat(), duration_ms=duration_ms, extra=extra,
            )
        except Exception as exc:  # noqa: BLE001 — timing must never break the producer
            print(f"[iterate_timings] span recording skipped: {exc}", file=sys.stderr)
