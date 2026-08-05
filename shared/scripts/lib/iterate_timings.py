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
only, kept under the file-size guideline.

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

# ---------------------------------------------------------------------------
# Catalog (SSoT) — 7 top-level groups + 14 nested spans named in the card.
# ---------------------------------------------------------------------------

TOP_LEVEL_SPANS: tuple[str, ...] = (
    "discovery_diagnosis", "planning", "implementation", "verification",
    "review", "finalization", "delivery",
)

# F5b (finalize_iterate.py) folds the durable event BEFORE F6 commits and
# BEFORE F11 pushes/delivers — the SKILL places "end finalization" at F11
# entry and "delivery" only self-records from the real F11 CLI invocation, so
# neither can EVER be closed (or, for delivery, exist at all) when the fold
# runs, in every run, structurally — not an occasional gap (doubt review).
# Coverage/degraded is measured against this achievable subset so a genuinely
# complete pre-fold run reads as complete, not permanently "degraded";
# finalization/delivery are still shown per-run, just not penalized for an
# incompleteness the architecture guarantees. See iterate-timings.md.
FOLD_TIME_CAPTURABLE_SPANS: tuple[str, ...] = (
    "discovery_diagnosis", "planning", "implementation", "verification", "review",
)

# name -> frozenset of valid parent names. Top-level spans parent to ``None``.
SPAN_PARENTS: dict[str, frozenset] = {
    "discovery_diagnosis": frozenset({None}),
    "planning": frozenset({None}),
    "implementation": frozenset({None}),
    "verification": frozenset({None}),
    "review": frozenset({None}),
    "finalization": frozenset({None}),
    "delivery": frozenset({None}),
    "focused_tests": frozenset({"implementation"}),
    "pre_f0_validation": frozenset({"verification"}),
    "f0_queue": frozenset({"verification"}),
    "canonical_f0_active": frozenset({"verification"}),
    "self_review": frozenset({"review"}),
    "spec_review": frozenset({"review"}),
    "code_review": frozenset({"review"}),
    "doubt_review": frozenset({"review"}),
    "external_review": frozenset({"planning", "review"}),
    "reviewer_wait": frozenset({"planning", "review"}),
    "remediation": frozenset({"review"}),
    "delivery_wait": frozenset({"delivery"}),
    "ci_wait": frozenset({"delivery", "delivery_wait"}),
    "post_ci_remediation": frozenset({"delivery"}),
}
SPAN_NAMES: frozenset = frozenset(SPAN_PARENTS)

SOURCES: frozenset = frozenset({"producer", "agent", "derived"})
OUTCOMES: frozenset = frozenset({"completed", "incomplete", "cancelled", "unavailable"})


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


def _append_line(project_root, run_id: str, obj: dict) -> Path:
    """Append one line under the run's lock — the same serialization
    ``record_event.py``/``triage.py`` use for their own JSONL append-logs.
    Multiple producers CAN legitimately write within one run (F0, external
    review, delivery), so an unlocked append risks interleaved writes,
    especially on Windows where append-mode alone isn't atomic."""
    path = sidecar_path(project_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(path.with_name(path.name + ".lock")):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def validate_name_parent(name: str, parent: str | None) -> None:
    if name not in SPAN_NAMES:
        raise IterateTimingError(f"unknown span name {name!r}")
    if parent not in SPAN_PARENTS[name]:
        allowed = ", ".join(str(p) for p in sorted(SPAN_PARENTS[name], key=lambda p: p or ""))
        raise IterateTimingError(f"span {name!r} does not accept parent {parent!r} (allowed: {allowed})")


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
    return _append_line(project_root, run_id, {
        "event": "span", "name": name, "parent": parent, "attempt": int(attempt),
        "source": source, "outcome": outcome, "start_utc": start_utc,
        "end_utc": end_utc, "duration_ms": duration_ms, "extra": clean_extra,
    })


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
