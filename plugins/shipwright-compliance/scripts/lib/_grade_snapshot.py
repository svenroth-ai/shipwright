"""Grade-snapshot emitter — one Control-Grade event per grade CHANGE (M-Pre-3).

The WebUI Ship's-Log Grade-Trend sparkline needs grade HISTORY, but the grade is
a repo aggregate that the dashboard overwrites on every regen — no history
survives. This module appends a ``grade_snapshot`` event to the DURABLE, tracked
``shipwright_events.jsonl`` when the compliance dashboard regenerates the grade
**and the grade has moved**, so the WebUI can project a trend + per-run delta
without the log filling with restatements of a number that did not change.

Idempotency contract (iterate-2026-08-01-grade-snapshot-dedup): a snapshot is
appended only when it CHANGES something. A regen whose grade and score match the
most recent snapshot from the same tree appends nothing and returns
``{"appended": 0, "reason": "unchanged_grade"}``.

This reverses the original contract, which appended UNCONDITIONALLY on the
premise that "a regen is an explicit act (a run finished)" and left dedup to the
WebUI. The premise was measurable, and measuring it falsified it: 234 of 695
events in this repo's log were grade snapshots (34%), and 2026-07-27 alone
produced 47 identical ``('F', 49.0)`` records from 20 different sessions. A
regen is not an explicit act — it fires on every compliance regen, in every
worktree, in every session. Delegating dedup to the WebUI remains right for
RENDERING, but it never stopped the durable, git-tracked, reviewed-in-diffs log
from being a third heartbeat.

What may be compared with what is the whole subtlety, and it lives in
``record_event`` (``append_event_idempotent(..., deduplicate_grade_snapshot=True)``)
so the scan shares the append's lock:

* the comparator is the most recent snapshot **of the same lineage class**, not
  the absolute last one — otherwise an alternating ``main``/``branch`` sequence
  dedups nothing;
* sameness of tree is ESTABLISHED, never assumed: a lineage outside
  ``{main, branch}`` is non-comparable, and two equally-unattributable records
  are not thereby the same tree;
* the comparison never raises, because a raise inside the lock would reach the
  best-effort wrapper below and LOSE the snapshot — worse than the duplicate.

Dedup is opt-in, and the manual/replay ``record_event.py --type grade_snapshot``
CLI does not opt in: the falsified premise is false for an automatic regen and
true for a hand-run replay.

Two known limits, stated rather than implied. ``resolve_events_path`` is a
literal per-tree join, so the lock covers one checkout: a stale or concurrent
worktree can still append a value already recorded elsewhere, and union merge
keeps both. And the 234 historical lines are NOT compacted — "never destroy an
appended line" (``compliance_input_state``) outranks a tidier chart.

Attribution (iterate-2026-07-28-grade-snapshot-lineage): a Control Grade is a
property of a TREE, and this regen usually runs inside an iterate worktree whose
event then union-merges onto ``main``. Every snapshot therefore carries
``lineage``/``branch``/``base``, built by the shared ``grade_snapshot_shape``
SSOT so this emitter and the ``record_event`` CLI cannot drift apart. Consumers
filter on ``lineage``; an ABSENT ``lineage`` means the event predates
attribution, which is why an unresolvable tree emits ``"unknown"`` explicitly
rather than omitting the field.

Additive: consumers that don't know ``grade_snapshot`` skip it
(``change_history.collect_events`` filters by known type) and the dashboard
output is unchanged. Fail-soft is SPLIT across two layers: this emitter only
*skips* (returns ``{"appended": 0, "reason": ...}`` — ``not_gradeable`` when
there is no gradeable score, ``unchanged_grade`` when the grade has not moved);
a real append failure RAISES and is caught by
``update_compliance``'s best-effort wrapper (which records
``{"appended": 0, "error": ...}``), so the compliance regen is never aborted —
the same contract as the SBOM / test-evidence triage emitters.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.lib._control_block import build_grade_inputs
from scripts.lib.control_grade import compute_grade

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


def emit_grade_snapshot(data: ComplianceData) -> dict:
    """Append a ``grade_snapshot`` event when the just-regenerated grade moved.

    The grade is RECOMPUTED here via ``compute_grade(build_grade_inputs(data))``
    rather than reusing the dashboard's ``GradeReport``. That is deliberate: it
    is the SAME deterministic function on the SAME frozen ``data`` the dashboard
    render consumed, so the two cannot diverge — this independent recompute IS
    the parity guarantee (pinned by a real-flow test). Do NOT refactor to cache
    or thread the report through the render path.

    Returns a small result dict (``appended`` count + grade/score + the resolved
    ``lineage``, or a skip ``reason``) for the ``update_compliance`` output
    payload. Raises on a real append failure (the caller's best-effort wrapper
    catches it) — but never because attribution failed, which degrades to
    ``lineage="unknown"``.
    """
    report = compute_grade(build_grade_inputs(data))
    if not report.gradeable or report.score is None:
        # No letter/score to trend (no measurable control dimension) —
        # nothing to snapshot.
        return {"appended": 0, "reason": "not_gradeable"}

    # Lazy import (ADR-045 / mirrors ``_control_block._ratchet_delta`` +
    # ``hooks/check_rtm_coverage``): these live in shared/scripts, OUTSIDE this
    # plugin's ``scripts.lib`` namespace, so they are wired at call time to avoid
    # binding ``sys.modules['lib']`` at module import. ``grade_snapshot_shape``
    # sits top-level there (not under ``lib/``) for exactly that reason.
    shared = Path(__file__).resolve().parents[4] / "shared" / "scripts"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    from grade_snapshot_shape import apply_grade_snapshot  # noqa: PLC0415
    from tools.record_event import (  # noqa: PLC0415
        SCHEMA_VERSION,
        append_event_idempotent,
        generate_event_id,
    )

    event: dict = {
        "v": SCHEMA_VERSION,
        "id": generate_event_id(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "grade_snapshot",
    }
    session = os.environ.get("SHIPWRIGHT_SESSION_ID", "")
    if session:
        event["session"] = session
    # grade/score + the tree attribution come from the shape SSOT shared with
    # the ``record_event`` CLI, so the two producers of this durable event cannot
    # drift apart. ``commit`` stays omitted: this regen runs BEFORE the F6
    # commit, so HEAD would still be the PREVIOUS commit and would mislabel the
    # snapshot. ``base`` — the merge-base the attribution resolves — answers
    # "which tree" without that defect (iterate-2026-07-28-grade-snapshot-lineage).
    apply_grade_snapshot(event, grade=report.grade, score=report.score,
                         project_root=data.project_root)

    event_id, skipped = append_event_idempotent(
        data.project_root, event, deduplicate_grade_snapshot=True,
    )
    if skipped is not None:
        # ``appended`` is this emitter's result vocabulary, not the helper's —
        # added here exactly as it is for the ``not_gradeable`` skip above, so
        # ``update_compliance``'s payload handling needs no change at all.
        return {"appended": 0, **skipped}
    return {
        "appended": 1,
        "id": event_id,
        "grade": report.grade,
        "score": report.score,
        "lineage": event["lineage"],
    }
