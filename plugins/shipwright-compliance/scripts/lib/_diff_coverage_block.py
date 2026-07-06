"""Diff-coverage rendering for the Control Verdict block (Test-Health signal).

Diff-coverage — the % of the CHANGED lines (vs the merge-base) that tests
execute — is a first-class Test-Health quality signal, NOT merely informational.
Since diff-coverage roadmap **Phase 3** it feeds the Control-Grade Test-Health
dimension (a WARN penalty below 80%); on any repo that adopts the CI gate,
**Phase 4** enforces it — a PR whose changed lines are < 80% covered blocks
merge. Split out of ``_control_block.py`` to keep that module ≤300 lines.

The value comes from the **gitignored transient**
``.shipwright/coverage/diff_coverage.json`` written by
``shared/scripts/tools/measure_diff_coverage.py`` — never from the tracked
``shipwright_test_results.json`` (``coverage.diff`` is PR-local, so committing it
would show stale data on ``main``). This renderer is repo-agnostic: it lights up
on ANY managed repo whose CI writes that transient, not just the monorepo.
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

_INFO_PREFIX = "> 📊 **Test-Health · diff-coverage (Control-Grade input · target ≥80%):** "


def load_diff_coverage(project_root: Path | None) -> dict | None:
    """Read the gitignored transient diff-coverage report, or ``None`` when
    absent/unreadable. Feeds both the display line and (via
    ``gradeable_diff_percent``) the Test-Health grade input."""
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
    """One Test-Health line for diff-coverage. Since Phase 3 the value feeds the
    Control-Grade Test-Health dimension (WARN below 80%), so it is a graded
    quality signal — not merely informational."""
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
