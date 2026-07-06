#!/usr/bin/env python3
"""Pure diff-coverage gate decision + report emission (Phase-4 hardening).

Split out of ``tools/measure_diff_coverage.py`` so the gate DECISION — the logic
that turns a measured diff-coverage percentage into a CI pass/fail exit code —
is unit-testable in isolation, independent of the ``diff-cover`` subprocess. The
``measure_diff_coverage.py --fail-under`` entrypoint imports these; ci.yml's
warn-only step calls that entrypoint instead of raw ``diff-cover`` so the
fail-path is provable (``tools/tests/test_measure_diff_coverage_gate.py``).
"""

from __future__ import annotations

from pathlib import Path

# Gate exit codes. ``decide_gate`` is only reached once a report was PRODUCED, so
# ``diff is None`` there means a genuine empty diff ("no changed lines under
# coverage"), which PASSES — matching diff-cover's own ``--fail-under``. The
# distinct case "diff-cover produced NO report" (crash / unavailable) must NOT be
# collapsed into that PASS; the caller fails closed with ``GATE_EXIT_ERROR``
# BEFORE calling ``decide_gate`` (else a diff-cover crash silently greens the
# gate — strictly more lenient than raw diff-cover).
GATE_EXIT_PASS = 0
GATE_EXIT_FAIL = 2
GATE_EXIT_ERROR = 3


def decide_gate(diff: float | None, fail_under: float) -> int:
    """``GATE_EXIT_FAIL`` iff ``diff < fail_under``; ``GATE_EXIT_PASS`` when
    ``diff is None`` (empty, but MEASURED, diff) or ``diff >= fail_under``.
    Measurement failure (no report) is NOT this function's concern — the caller
    handles it as ``GATE_EXIT_ERROR`` before calling here."""
    if diff is None:
        return GATE_EXIT_PASS
    return GATE_EXIT_FAIL if diff < fail_under else GATE_EXIT_PASS


def print_gate_report(
    markdown_out: Path | None, diff: float | None, fail_under: float
) -> None:
    """ALWAYS emit the diff report (pass or fail): the diff-cover markdown file
    if present, else a one-line summary (pre-computed / empty-diff path)."""
    text = None
    if markdown_out is not None:
        try:
            text = Path(markdown_out).read_text(encoding="utf-8")
        except OSError:
            text = None
    if text:
        print(text)
    elif diff is not None:
        print(f"Diff coverage: {diff:.1f}% of changed lines covered "
              f"(threshold {fail_under:g}%).")
    else:
        print("No lines with coverage information in this diff.")
