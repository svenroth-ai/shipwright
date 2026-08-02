"""Grade-snapshot emitter — one Control-Grade event per compliance regen (M-Pre-3).

The WebUI Ship's-Log Grade-Trend sparkline needs grade HISTORY, but the grade is
a repo aggregate that the dashboard overwrites on every regen — no history
survives. This module appends one ``grade_snapshot`` event to the DURABLE,
tracked ``shipwright_events.jsonl`` each time the compliance dashboard
regenerates the grade, so the WebUI can project a trend + per-run delta.

Idempotency contract (AC1): exactly one snapshot per regen, appended
UNCONDITIONALLY — no producer-side dedup. A regen is an explicit act (a run
finished); recording it every time keeps the producer trivial and preserves the
full regen cadence for the trend, while the WebUI dedupes consecutive identical
(grade, score) points when it draws the sparkline. The alternative — skip an
unchanged-grade no-op regen — would need a read-back-last-snapshot scan here for
no functional gain, so the simpler contract wins.

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
*skips* (returns ``{"appended": 0, "reason": "not_gradeable"}``) when there is
no gradeable score; a real append failure RAISES and is caught by
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


def emit_grade_snapshot(data: ComplianceData, *, dirty: bool | None = None) -> dict:
    """Append one ``grade_snapshot`` event for the just-regenerated grade.

    The grade is RECOMPUTED here via ``compute_grade(build_grade_inputs(data))``
    rather than reusing the dashboard's ``GradeReport``. That is deliberate: it
    is the SAME deterministic function on the SAME frozen ``data`` the dashboard
    render consumed, so the two cannot diverge — this independent recompute IS
    the parity guarantee (pinned by a real-flow test). Do NOT refactor to cache
    or thread the report through the render path.

    ``dirty`` is passed IN, never measured here: this runs after six generators
    have rewritten tracked documents, so asking git now reads ``true`` on a pristine
    tree (``trg-f5ae5371``). ``update_compliance`` captures it at its own entry,
    before the first generator runs.

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
        append_event,
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
                         project_root=data.project_root, dirty=dirty)

    event_id = append_event(data.project_root, event)
    return {
        "appended": 1,
        "id": event_id,
        "grade": report.grade,
        "score": report.score,
        "lineage": event["lineage"],
        "dirty": event.get("dirty"),
    }
