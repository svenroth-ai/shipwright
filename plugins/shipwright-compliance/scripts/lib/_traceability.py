"""Dashboard traceability metrics (BP-1).

Two consumers, one shared SSOT:

- :func:`count_traced` feeds the Control-Grade requirement-traceability
  dimension (``GradeInputs.events_fr_tagged``). A change counts as *traced* when
  it is FR-linked OR a *satisfied no-FR change* (valid change_type + one-line
  none_reason, behavior-preserving) — the discriminating definition the Spec
  handoff seam asked for.
- :func:`render_traced_row` surfaces the **FR-tagging freeze** as a
  Quality-Indicators row and flags a drop. This is the honesty counterweight:
  even as the grade credits classified no-FR work, the dashboard transparently
  shows that FR-tagging *itself* is rare (mostly framework infra).

Both key off the shared :mod:`fr_classification` SSOT, loaded pollution-free via
``audit_adapters.load_shared_lib`` so "classified" (the record_event gate) and
"traced" (the grade) can never drift.
"""

from __future__ import annotations

from scripts.audit.audit_adapters import load_shared_lib

_fc = load_shared_lib("fr_classification")

# How many most-recent iterate changes the freeze metric looks back over.
_RECENT_WINDOW = 30


def _is_traced(we) -> bool:
    """A work event is traced to a requirement decision.

    Build events trace via their planned section→FR mapping; iterate events via
    the shared FR-or-satisfied-no-FR predicate."""
    if we.source != "iterate":
        return bool(we.section) or _fc.is_fr_tagged(we.affected_frs, we.new_frs)
    return _fc.is_traced(
        we.affected_frs, we.new_frs, we.change_type, we.none_reason,
        we.spec_impact,
    )


def count_traced(work_events) -> int:
    """Number of work events traced to a requirement decision (the
    ``events_fr_tagged`` grade input)."""
    return sum(1 for we in work_events if _is_traced(we))


def _iterate_needs_tests(we) -> bool:
    """True iff this iterate change is EXPECTED to carry tests.

    The test-side mirror of BP-1's traced-credit: a behavior-preserving
    **satisfied no-FR change** (a recognized non-feature ``change_type`` —
    docs/tooling/compliance/infra — with a valid one-line ``none_reason`` and no
    behavior impact) is legitimately test-free, so it is NOT expected to carry
    tests. Everything else that is real iterate work — feature/change/bug work or
    any behavior-affecting change — is.

    Only ``source == "iterate"`` events are in scope. Build sections are credited
    by the sections-reviewed metric; synthetic ``backfill*`` / ``*-retro`` /
    ``*-merge-retro`` sources are not iterate work at all and never enter the
    denominator.

    The discriminator is behavior-preservation, NOT FR-linkage: a behavior-
    preserving docs/tooling/compliance/infra change is test-free even if it
    incidentally references an FR (``is_satisfied_no_fr`` already requires
    ``spec_impact`` to be non-behavior-affecting, so any add/modify/remove change
    — FR-linked or not — is always retained). Excluding such a change is the goal
    (fewer false deficits); keying on FR-linkage instead would re-flag
    behavior-preserving FR-referencing docs as untested."""
    if we.source != "iterate":
        return False
    return not _fc.is_satisfied_no_fr(we.change_type, we.none_reason, we.spec_impact)


def iterate_test_coverage(work_events) -> tuple[int, int]:
    """Return ``(tested, testable)`` over iterate changes expected to carry tests.

    ``testable`` excludes behavior-preserving no-FR changes
    (docs/tooling/compliance/infra) so the dashboard's "Iterate tests passing"
    row stops counting legitimately test-free work as a deficit (alarm-fatigue,
    the same root flaw BP-1 fixed for the traced-% metric). ``tested`` counts the
    testable changes that recorded ≥1 test. The residual gap (FR-linked or
    behavior-affecting work with no recorded tests) is honest signal and stays a
    WARN. Shares :data:`_fc`'s ``is_satisfied_no_fr`` with :func:`count_traced`
    so "traced" and "testable" can never disagree about what a non-feature
    change is."""
    testable = [we for we in work_events if _iterate_needs_tests(we)]
    tested = sum(1 for we in testable if we.tests_total > 0)
    return tested, len(testable)


def _pct(num: int, den: int) -> float:
    return (num / den) if den else 0.0


def render_traced_row(work_events) -> str:
    """The '% of recent changes traced to an FR' Quality-Indicators row.

    Measures genuine FR-linkage (``affected_frs``/``new_frs``) — NOT the broader
    'classified' notion — over the last :data:`_RECENT_WINDOW` iterate changes,
    and WARNs when that rate has dropped below the all-time rate (a freeze)."""
    iterate = [we for we in work_events if we.source == "iterate"]
    if not iterate:
        return (
            "| Recent changes traced to an FR | n/a | n/a | "
            "no iterate changes recorded yet |"
        )

    all_tagged = sum(
        1 for we in iterate if _fc.is_fr_tagged(we.affected_frs, we.new_frs))
    window = iterate[-_RECENT_WINDOW:]
    recent_tagged = sum(
        1 for we in window if _fc.is_fr_tagged(we.affected_frs, we.new_frs))

    recent_pct = _pct(recent_tagged, len(window))
    all_pct = _pct(all_tagged, len(iterate))

    # WARN on a freeze, two ways: a relative drop below the all-time rate, OR an
    # absolute floor — zero FR-tags in the recent window (a steady-state freeze
    # that the relative test misses once all-time decays toward recent). The raw
    # "X/N (P%)" stays honest regardless of the badge.
    if recent_tagged == 0:
        why = (
            f"no recent change carries an FR tag (last {len(window)}) — "
            "FR-tagging is frozen; see the Control Verdict traceability dimension"
        )
        badge = "WARN"
    elif recent_pct < all_pct:
        why = (
            f"FR-tagging dropped to {recent_pct:.0%} (last {len(window)}) vs "
            f"{all_pct:.0%} all-time — recent changes classified no-FR; see the "
            "Control Verdict traceability dimension"
        )
        badge = "WARN"
    else:
        why = ""
        badge = "PASS"
    return (
        f"| Recent changes traced to an FR | {recent_tagged}/{len(window)} "
        f"({recent_pct:.0%}) | {badge} | {why} |"
    )
