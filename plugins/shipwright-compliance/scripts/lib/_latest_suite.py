"""Resolve the latest *full* test-suite run from work events (AR-02).

The event log carries no explicit "full suite" flag, test totals fluctuate
run-to-run, and subset (``--related``) runs interleave with full ones — so
naively taking the last event's ``tests`` yields ``0/0`` (a doc commit) or a
tiny subset, not the real suite. We define the latest full suite as the most
recent work event whose ``tests_total`` is at least ``FULL_SUITE_FRACTION``
of the maximum ``tests_total`` ever observed, which deterministically
isolates whole-suite runs (thousands of tests) from subset runs.

Shared by the dashboard headline and the test-evidence summary so both read
the same number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

# A full suite is any run reaching >= this fraction of the largest run seen.
FULL_SUITE_FRACTION = 0.5


def _ts_key(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp to a comparable aware datetime.

    Comparing parsed datetimes (not raw strings) keeps ordering correct even
    if a producer ever emits a ``Z`` suffix or a non-``+00:00`` offset (raw
    string compare would mis-sort those). A malformed stamp sorts to the far
    past so it can never spuriously win "latest"."""
    try:
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class LatestSuite:
    passed: int
    total: int
    date: str          # YYYY-MM-DD of the suite event
    changes_since: int  # work events recorded after it (no full re-run)


def resolve_latest_full_suite(work_events) -> LatestSuite | None:
    """Return the most recent full-suite run, or None when none qualifies.

    Events are not strictly time-ordered in the log (``event_amended`` +
    multi-machine use), so "most recent" is by timestamp, not list order.

    Limitation (generic grader): with no explicit full-suite flag, a relative
    "fraction of max" heuristic can over-credit a repo whose largest run is
    tiny, or mistake a recent large *partial* run for the full suite. The
    definitive fix is an upstream full-suite marker (roadmap BP-3); for
    Shipwright's data the heuristic resolves the real suite correctly.
    """
    tested = [we for we in work_events if we.tests_total > 0]
    if not tested:
        return None

    max_total = max(we.tests_total for we in tested)
    threshold = max_total * FULL_SUITE_FRACTION
    full = [we for we in tested if we.tests_total >= threshold]
    if not full:  # pragma: no cover - max element always clears its own bar
        return None

    # Ties on timestamp resolve to first-in-list order (deterministic).
    latest = max(full, key=lambda we: _ts_key(we.timestamp))
    latest_key = _ts_key(latest.timestamp)
    changes_since = sum(
        1 for we in work_events if _ts_key(we.timestamp) > latest_key)
    return LatestSuite(
        passed=latest.tests_passed,
        total=latest.tests_total,
        date=latest.timestamp[:10],
        changes_since=changes_since,
    )
