"""Bloat-findings summary — bridge from ``shipwright_bloat_baseline.json``
to the project-wide Compliance Dashboard.

Consumed by the compliance plugin's ``compliance_report.py`` to render
the three bloat-findings cells on the Compliance Dashboard MD. Kept in
:mod:`phase_quality` (not in the compliance plugin) because the
shipwright-compliance plugin already imports from
``shared.scripts.lib`` and the baseline schema producer
(``lib.bloat_baseline``) lives in shared — keeping the consumer
adjacent to the producer reduces cross-plugin coupling.

Iterate Campaign B (B3): introduced as part of the
``phase_quality.py`` 1108-LOC split. Separated from
``_dashboard_render.py`` so each submodule stays under the 300-LOC
source budget.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import bloat_baseline as _bb  # noqa: E402
from lib.anti_ratchet import measure_worktree  # noqa: E402


def collect_bloat_summary(project_root: Path) -> dict[str, int]:
    """Return the three bloat-findings counters for the Compliance Dashboard.

    Reads ``shipwright_bloat_baseline.json`` and re-measures every entry
    against the current worktree. Returns a dict with three keys:

    * ``over_limit`` — entries where ``measured > limit`` AND
      ``state != "exception"``. Counts files that have ratcheted past
      their grandfathered ceiling AND aren't ADR-justified exceptions.
    * ``in_allowlist`` — count of ``state == "grandfathered"`` +
      ``state == "exception"`` entries (everything the baseline
      tracks, by definition).
    * ``ratchet_delta`` — sum of ``(measured − current)`` across all
      ``state == "grandfathered"`` entries. Negative values mean the
      campaign is shrinking the grandfathered surface; positive
      values mean ratcheting up (Iron Law violation).

    Fail-open: a missing / malformed baseline returns all zeros. A
    missing-from-disk path contributes 0 to ``over_limit`` and to
    ``ratchet_delta`` (the file is gone; the entry is stale, not
    ratcheting).
    """
    doc = _bb.load(project_root)
    if not isinstance(doc, dict):
        return {"over_limit": 0, "in_allowlist": 0, "ratchet_delta": 0}
    entries = doc.get("entries")
    if not isinstance(entries, list):
        return {"over_limit": 0, "in_allowlist": 0, "ratchet_delta": 0}

    over_limit = 0
    in_allowlist = 0
    ratchet_delta = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        limit = entry.get("limit")
        current = entry.get("current")
        state = entry.get("state")
        if not isinstance(path, str):
            continue

        if state in ("grandfathered", "exception"):
            in_allowlist += 1

        measured: int | None = None
        if isinstance(limit, int) or isinstance(current, int):
            try:
                measured = measure_worktree(project_root, path)
            except Exception:  # noqa: BLE001
                measured = None

        # over_limit: measured > limit AND not an ADR-justified exception.
        if (
            measured is not None
            and isinstance(limit, int)
            and measured > limit
            and state != "exception"
        ):
            over_limit += 1

        # ratchet_delta: only grandfathered entries contribute. Missing
        # worktree files contribute 0 (stale, not a ratchet).
        if state == "grandfathered" and measured is not None and isinstance(current, int):
            ratchet_delta += measured - current

    return {
        "over_limit": over_limit,
        "in_allowlist": in_allowlist,
        "ratchet_delta": ratchet_delta,
    }


__all__ = ["collect_bloat_summary"]
