"""Grade-neutral diff-coverage rendering for the Control Verdict block.

Diff-coverage roadmap **Phase 1** (``iterate-2026-07-03-diff-coverage-measure-
one-tier``). The number is surfaced as an INFORMATIONAL INFO line under
Test-Health only — it is deliberately kept out of :class:`GradeInputs` /
:class:`GradeReport`, so it can never enter the Control Grade score (feeding the
grade is Phase 3). Split out of ``_control_block.py`` to keep that module ≤300
lines and to isolate the display-only concern.

The value comes from the **gitignored transient**
``.shipwright/coverage/diff_coverage.json`` written by
``shared/scripts/tools/measure_diff_coverage.py`` — never from the tracked
``shipwright_test_results.json`` (``coverage.diff`` is PR-local, so committing it
would show stale data on ``main``).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

__all__ = [
    "load_diff_coverage",
    "diff_coverage_info_line",
    "gradeable_diff_percent",
]

_DIFF_COVERAGE_REL = Path(".shipwright") / "coverage" / "diff_coverage.json"

_INFO_PREFIX = "> ℹ️ **Test-Health · diff-coverage (informational, not yet graded):** "


def load_diff_coverage(project_root: Path | None) -> dict | None:
    """Read the gitignored transient diff-coverage report, or ``None`` when
    absent/unreadable. Passed to the renderer as an EXPLICIT display-only value
    (never through the grade)."""
    if project_root is None:
        return None
    path = Path(project_root) / _DIFF_COVERAGE_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def gradeable_diff_percent(cov: dict | None) -> float | None:
    """Strict extraction of the diff-coverage % that may feed the grade, or None.

    Diff-coverage roadmap **Phase 3**: only a finite, in-range ``[0, 100]``
    ``diff`` with ``status == "ok"`` is gradeable. The transient is untrusted
    local input, so every other shape — n/a status, missing/None ``diff``, a
    bool/string, ``NaN``/``inf``, or an out-of-range percent — degrades to
    ``None`` (no Test-Health effect), never a crash or a nonsensical penalty. On
    ``main`` (no transient → ``cov is None``) this is always ``None``, so the
    monorepo grade is unchanged."""
    if not cov or cov.get("status") != "ok":
        return None
    diff = cov.get("diff")
    # bool is an int subclass — reject it explicitly (True/False are not a %).
    if isinstance(diff, bool) or not isinstance(diff, (int, float)):
        return None
    # Range check FIRST: int↔float comparison is exact and overflow-safe, so a
    # huge arbitrary-precision JSON int (e.g. 10**400) is rejected here without
    # ever reaching math.isfinite (which would raise OverflowError on it). The
    # range also rejects NaN/±inf (out-of-range); isfinite is a belt-and-braces
    # guard reached only for an already-bounded value.
    if not (0.0 <= diff <= 100.0) or not math.isfinite(diff):
        return None
    return float(diff)


def diff_coverage_info_line(cov: dict | None) -> str:
    """One grade-neutral INFO line tying diff-coverage to Test-Health.

    Purely informational — the number does NOT affect the Control Grade."""
    if not cov:
        return (_INFO_PREFIX + "not measured this session — per-PR signal; see "
                'the CI "Diff coverage" artifact.')
    if cov.get("status") == "ok" and isinstance(cov.get("diff"), (int, float)):
        tier = cov.get("measured_tier", "repo")
        base = cov.get("compare_branch", "origin/main")
        return (_INFO_PREFIX + f"{float(cov['diff']):.1f}% of changed lines "
                f"covered ({tier} tier, vs {base}).")
    # n/a can mean several things (no changed lines, missing coverage.xml,
    # diff-cover unavailable, unreadable report) — surface the producer's own
    # `note` rather than assuming a single reason.
    note = (cov.get("note") or "").strip()
    reason = note or "no diff-coverage available for this ref"
    return _INFO_PREFIX + f"n/a — {reason}."
