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
from pathlib import Path

__all__ = ["load_diff_coverage", "diff_coverage_info_line"]

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
