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


def emit_grade_snapshot(data: ComplianceData) -> dict:
    """Append one ``grade_snapshot`` event for the just-regenerated grade.

    The grade is RECOMPUTED here via ``compute_grade(build_grade_inputs(data))``
    rather than reusing the dashboard's ``GradeReport``. That is deliberate: it
    is the SAME deterministic function on the SAME frozen ``data`` the dashboard
    render consumed, so the two cannot diverge — this independent recompute IS
    the parity guarantee (pinned by a real-flow test). Do NOT refactor to cache
    or thread the report through the render path.

    Returns a small result dict (``appended`` count + grade/score, or a skip
    ``reason``) for the ``update_compliance`` output payload. Raises on a real
    append failure (the caller's best-effort wrapper catches it).
    """
    report = compute_grade(build_grade_inputs(data))
    if not report.gradeable or report.score is None:
        # No letter/score to trend (no measurable control dimension) —
        # nothing to snapshot.
        return {"appended": 0, "reason": "not_gradeable"}

    # Lazy import (ADR-045 / mirrors ``_control_block._ratchet_delta`` +
    # ``hooks/check_rtm_coverage``): ``record_event`` lives in shared/scripts,
    # OUTSIDE this plugin's ``scripts.lib`` namespace, so it is wired at call
    # time to avoid binding ``sys.modules['lib']`` at module import.
    shared = Path(__file__).resolve().parents[4] / "shared" / "scripts"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
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
        "grade": report.grade,
        "score": report.score,
    }
    session = os.environ.get("SHIPWRIGHT_SESSION_ID", "")
    if session:
        event["session"] = session
    # ``commit`` is deliberately omitted: the finalize-time regen runs BEFORE the
    # F6 commit, so HEAD would still be the PREVIOUS commit — recording it would
    # mislabel the snapshot. The WebUI correlates snapshots by ``ts``.

    event_id = append_event(data.project_root, event)
    return {
        "appended": 1,
        "id": event_id,
        "grade": report.grade,
        "score": report.score,
    }
