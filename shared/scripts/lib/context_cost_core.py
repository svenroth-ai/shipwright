"""Shared context-cost computation: dedup + phase attribution + pricing.

One function, three callers (context-cost-meter design, revised after two
external-review rounds rejected a standing incremental append-only cache as
disproportionate for a transcript this small and this cheap to re-read in
full): the ``Stop`` hook (``track_context_cost.py``), the summary/statusline
readers, and the F5b ``finalize_iterate`` fold. All three call
:func:`compute_summary` — never three reimplementations of dedup, phase
resolution, or pricing.

Phase attribution reuses the EXISTING ``iterate_phase_groups`` boundary-mark
sidecar (the same sidecar M-Pre-1 phase timing already writes) rather than a
second marking mechanism. A call is attributed to a phase only when its
timestamp falls on or after that run's *first* mark — a transcript that spans
into a prior run, or starts before phase tracking began, must never
misattribute a call to a run it did not happen in (plan-review finding,
iterate-2026-08-07-context-cost-meter).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib import model_pricing  # noqa: E402
from lib.context_cost_session import (  # noqa: E402,F401
    resolve_active_project_root,
    resolve_session_id,
)
from lib.iterate_phase_groups import ITERATE_PHASE_GROUPS, read_marks  # noqa: E402

__all__ = [
    "compute_summary",
    "fold_into_event",
    "resolve_session_id",
    "resolve_active_project_root",
]

_UNPHASED = "unphased"


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _sorted_marks(project_root, run_id: str | None) -> list[tuple[datetime, str]]:
    if not run_id:
        return []
    out: list[tuple[datetime, str]] = []
    for m in read_marks(project_root, run_id):
        dt = _parse_dt(m.get("ts"))
        if dt is not None and m.get("phase") in ITERATE_PHASE_GROUPS:
            out.append((dt, m["phase"]))
    out.sort(key=lambda t: t[0])
    return out


def _resolve_phase(sorted_marks: list[tuple[datetime, str]], call_dt: datetime | None) -> str:
    if not sorted_marks or call_dt is None:
        return _UNPHASED
    if call_dt < sorted_marks[0][0]:
        return _UNPHASED
    phase = _UNPHASED
    for mark_dt, mark_phase in sorted_marks:
        if mark_dt <= call_dt:
            phase = mark_phase
        else:
            break
    return phase


def _iter_transcript_records(transcript_path):
    path = Path(transcript_path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            yield obj


def _empty_phase_bucket() -> dict:
    return {"calls": 0, "context_tokens": 0, "cost_usd": 0.0, "unpriced_calls": 0}


def _num(value) -> int | float:
    """Coerce a transcript token-count field to a non-negative number, or 0.

    A malformed value (wrong type, negative) degrades to 0 for that ONE
    token type rather than raising out of the whole record's accounting --
    the same "unexpected shape degrades, never crashes" precedent this file
    already applies to a malformed cache_creation shape. Without this, a
    string ``input_tokens`` (e.g. ``"100"``) raised a ``TypeError`` out of
    the entire ``compute_summary`` loop, silently losing every OTHER call in
    the same transcript, not just the malformed one (external-review
    finding, iterate-2026-08-07-context-cost-meter).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return value if value >= 0 else 0


def compute_summary(transcript_path, project_root, run_id: str | None = None) -> dict:
    """Compute the deduped, phase-tagged, priced summary for one transcript.

    Full re-read every call — no incremental state, nothing to keep in sync,
    nothing to corrupt across a crash. Sessions are small (median ~276 calls
    per the measurement this feature is built from), so this is cheap.

    Returns a dict shaped:
    ``{calls, context_tokens, cost_usd, unpriced_calls, unpriced_models,
    cost_complete, skipped_malformed, by_phase: {phase: {calls,
    context_tokens, cost_usd, unpriced_calls}}}``. ``cost_usd`` at every
    level is the sum of what is actually priced — never ``null`` for a
    total that includes some priced calls — paired with ``unpriced_calls``
    and ``cost_complete`` so a partial total is never mistaken for a whole
    one. ``unpriced_models`` is the sorted, deduplicated list of model ids
    that produced an unpriced call — this summary deliberately keeps no
    other per-call detail (design rejected as disproportionate in two
    external-review rounds; the transcript itself remains the source of
    truth for anything finer-grained than this), but a bare count alone
    left no way to tell WHICH model needs a pricing-table entry, so this
    one bounded, non-growing field closes that gap (external-review
    finding, iterate-2026-08-07-context-cost-meter).
    """
    sorted_marks = _sorted_marks(project_root, run_id)

    seen_request_ids: set[str] = set()
    calls = 0
    context_tokens = 0
    cost_usd = 0.0
    unpriced_calls = 0
    unpriced_models: set[str] = set()
    skipped_malformed = 0
    by_phase: dict[str, dict] = {}

    for record in _iter_transcript_records(transcript_path):
        if record.get("type") != "assistant":
            continue
        request_id = record.get("requestId")
        message = record.get("message")
        if not isinstance(message, dict):
            skipped_malformed += 1
            continue
        model = message.get("model")
        usage = message.get("usage")
        # request_id and model must be strings, not merely truthy -- an
        # unhashable value (e.g. a list) would raise out of the
        # seen_request_ids/unpriced_models set or the MODEL_PRICING dict
        # lookup below, aborting every OTHER call's accounting too
        # (external-review finding, iterate-2026-08-07-context-cost-meter).
        if (
            not isinstance(request_id, str)
            or not request_id
            or not isinstance(model, str)
            or not model
            or not isinstance(usage, dict)
        ):
            skipped_malformed += 1
            continue
        if request_id in seen_request_ids:
            continue
        seen_request_ids.add(request_id)

        call_dt = _parse_dt(record.get("timestamp"))
        phase = _resolve_phase(sorted_marks, call_dt)

        cache_creation = usage.get("cache_creation")
        if not isinstance(cache_creation, dict):
            # A transcript's own cache_creation shape is not this feature's
            # contract to enforce -- an unexpected shape here degrades to
            # "no cache-creation tokens for this call", never a crash that
            # would abort every OTHER call's accounting too.
            cache_creation = {}
        input_tokens = _num(usage.get("input_tokens"))
        cache_read_tokens = _num(usage.get("cache_read_input_tokens"))
        # Presence of the split KEY wins, not the split value's truthiness --
        # mirrors model_pricing.compute_cost_usd's identical fix (external-
        # review finding, iterate-2026-08-07-context-cost-meter): a record
        # can legitimately carry an explicit-zero split that must still beat
        # a stale aggregate field rather than falling through to it.
        split_present = (
            "ephemeral_5m_input_tokens" in cache_creation
            or "ephemeral_1h_input_tokens" in cache_creation
        )
        write_5m = _num(cache_creation.get("ephemeral_5m_input_tokens"))
        write_1h = _num(cache_creation.get("ephemeral_1h_input_tokens"))
        if not split_present:
            write_5m = _num(usage.get("cache_creation_input_tokens"))
        call_context_tokens = input_tokens + cache_read_tokens + write_5m + write_1h

        call_cost, unpriced = model_pricing.compute_cost_usd(model, usage)

        calls += 1
        context_tokens += call_context_tokens
        if unpriced:
            unpriced_calls += 1
            unpriced_models.add(model)
        else:
            cost_usd += call_cost

        bucket = by_phase.setdefault(phase, _empty_phase_bucket())
        bucket["calls"] += 1
        bucket["context_tokens"] += call_context_tokens
        if unpriced:
            bucket["unpriced_calls"] += 1
        else:
            # Full precision through accumulation -- rounded once below, not
            # after every addition. Rounding on each add (as this line used
            # to) compounds the same sub-microdollar loss model_pricing.
            # compute_cost_usd's own per-call round used to cause, just at
            # the phase-bucket level instead of the session total (external-
            # review finding, iterate-2026-08-07-context-cost-meter).
            bucket["cost_usd"] += call_cost

    for bucket in by_phase.values():
        bucket["cost_usd"] = round(bucket["cost_usd"], 6)

    return {
        "calls": calls,
        "context_tokens": context_tokens,
        "cost_usd": round(cost_usd, 6),
        "unpriced_calls": unpriced_calls,
        "unpriced_models": sorted(unpriced_models),
        "cost_complete": unpriced_calls == 0,
        "skipped_malformed": skipped_malformed,
        "by_phase": by_phase,
    }


def fold_into_event(event: dict, summary: dict | None, measured_through: str = "F5b") -> dict:
    """Fold a run's cost summary into ``event['context_cost']``.

    Additive, first-write-wins — mirrors
    ``iterate_phase_groups.fold_into_event`` exactly. Best-effort: a missing
    or empty summary leaves ``event`` unchanged, and this never raises —
    cost measurement must never break finalization. Returns ``event`` for
    chaining.

    ``summary`` is the finalizing session's *last-Stop-written* per-session
    file, not a fresh :func:`compute_summary` call — ``finalize_iterate.py``
    is a plain script, not a hook, so it never receives a ``transcript_path``
    (that only arrives on a hook's own stdin payload); deriving one from
    ``SHIPWRIGHT_SESSION_ID`` alone would mean guessing Claude Code's
    internal transcript-storage layout, the exact kind of unfounded
    inference this feature's own pricing code refuses to do for an
    unrecognized model. The file is current through the end of the
    *previous* assistant turn — ``Stop`` fires at every turn end, not once
    at session end (verified via ``generate_handoff_on_stop.py``'s own
    turn-end-skip guard), so this is a bounded staleness of at most one
    in-flight turn, not an indefinitely stale accumulation.

    That bound still means a run's ``work_completed.context_cost`` never
    includes F6-F12 (commit, PR delivery, CI rework) or anything folded
    mid-turn after the last ``Stop`` — the tracked, cross-run-comparable
    number is systematically a *floor*, not the whole session. ``calls``
    and ``measured_at`` (this fold's own wall-clock time) are stamped
    alongside ``measured_through`` so a truncated figure can never be
    compared against a whole-session figure unnoticed.
    """
    if "context_cost" in event:
        return event
    if not summary:
        return event
    try:
        event["context_cost"] = {
            "calls": summary["calls"],
            "context_tokens": summary["context_tokens"],
            "cost_usd": summary["cost_usd"],
            "unpriced_calls": summary["unpriced_calls"],
            "unpriced_models": summary.get("unpriced_models", []),
            "cost_complete": summary["cost_complete"],
            "by_phase": summary["by_phase"],
            "measured_through": measured_through,
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }
    except (KeyError, TypeError) as exc:
        print(f"[context_cost_core] fold skipped: {exc}", file=sys.stderr)
    return event
