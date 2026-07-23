"""SSOT for the work_completed ``tests`` block skip-vs-failure semantics.

``total`` counts selected tests (passed + failed + skipped), so genuine failures
are ``total - passed - skipped``. A work_completed event is green-at-merge (Iron
Law), so a ``passed < total`` gap WITHOUT an explicit ``skipped`` count is
host-gated skips, not failures. Every reader shares the SAME present/absent
predicate — ``isinstance(skipped, int)`` — so the write guard, the D4 detective
(``group_d._failed_count``, the same predicate), the test-evidence renderer, and
the build dashboard cannot disagree.

Lives at ``shared/scripts/`` top-level (like ``markdown_table``) rather than under
``lib/`` so the compliance plugin can import it without colliding with its own
``lib`` package (ADR-045). Introduced by iterate-2026-07-23-tests-skipped-tracking.
"""

from __future__ import annotations


def validate_tests_block(tests: dict) -> None:
    """Fail closed (raise ``ValueError``) on a corrupt tests block: ``skipped``
    (when present) a non-negative int, and ``passed + skipped <= total``. Applied
    to BOTH the record_event ``--tests-*`` flag path and an ``event_amended``
    ``fields.tests`` correction, so the readers can trust ``total - passed -
    skipped`` as the genuine failure count from every supported write route."""
    skipped = tests.get("skipped")
    if skipped is not None and (
            isinstance(skipped, bool) or not isinstance(skipped, int) or skipped < 0):
        raise ValueError(f"tests.skipped must be a non-negative integer, got {skipped!r}")
    passed, total = tests.get("passed"), tests.get("total")
    if (isinstance(passed, int) and isinstance(total, int)
            and isinstance(skipped, int) and passed + skipped > total):
        raise ValueError(f"tests passed ({passed}) + skipped ({skipped}) > total ({total})")


def skip_suffix(tests: dict) -> str:
    """`` (N skipped)`` for an explicit positive int skip count, else ``''`` — so a
    legacy row (absent / zero / non-int skipped) renders byte-unchanged."""
    skipped = tests.get("skipped")
    return f" ({skipped} skipped)" if isinstance(skipped, int) and skipped > 0 else ""


def progression_result(passed: int, total: int, skipped: object, baseline: int) -> str:
    """Render the test-evidence Test Progression Result cell.

    No explicit skip count (every legacy event, or a malformed non-int) → the
    green-at-merge gap is treated wholly as skips (charitable rendering, preserved
    byte-for-byte from iterate-2026-06-16-compliance-rendering-fixes). Explicit
    skip count → genuine failures are ``total - passed - skipped``; the count is
    disclosed even at ``passed == total`` and a residual renders FAIL, not a
    dishonest PASS. The ``isinstance(int)`` predicate matches D4 + skip_suffix, so
    a non-int skipped is charitable here too (never a crash), not divergent.
    """
    if total <= 0:
        return "—"
    if not isinstance(skipped, int):
        gap = total - passed
        if gap <= 0:
            return "PASS"
        if baseline > 0 and gap <= baseline:
            return "PASS (baseline)"
        return f"PASS ({gap} skipped)"
    failed = max(0, total - passed - skipped)
    if failed <= 0:
        return f"PASS ({skipped} skipped)" if skipped else "PASS"
    return (
        f"FAIL ({failed} failed, {skipped} skipped)"
        if skipped else f"FAIL ({failed} failed)"
    )
