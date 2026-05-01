"""Group registration bootstrap for the detective audit.

Imports each ``group_*.py`` and registers its ``run`` function with
``audit_detector``. Keeping registration here (rather than at import-time
inside each group module) means ``audit_detector.py`` stays importable
for unit tests that want an empty registry.
"""

from __future__ import annotations

from scripts.audit import audit_detector


def register_all() -> None:
    """Register every implemented group with the detector.

    Sub-Iterate C (plan v7 Steps 7+8) wired Groups E and G; the registry
    now covers every Plan-v7 group A..G. Future iterates that add
    cross-cutting checks should register here in alphabetical order.
    """
    # Reset registry to avoid double-registration when called twice
    # (tests call this repeatedly with fresh fixtures).
    audit_detector._GROUPS.clear()

    # Group A — Artifact / path integrity (Step 4).
    from scripts.audit import group_a
    audit_detector.register_group("A", group_a.run)

    # Group B — Config / event-log coherence (Step 5).
    from scripts.audit import group_b
    audit_detector.register_group("B", group_b.run)

    # Group C — Planning coherence (Step 6).
    from scripts.audit import group_c
    audit_detector.register_group("C", group_c.run)

    # Group D — Event-log FR coverage (Step 4).
    from scripts.audit import group_d
    audit_detector.register_group("D", group_d.run)

    # Group E — Compliance-doc content staleness (Step 7).
    from scripts.audit import group_e
    audit_detector.register_group("E", group_e.run)

    # Group F — ADR structural integrity (Step 6).
    from scripts.audit import group_f
    audit_detector.register_group("F", group_f.run)

    # Group G — Agent-docs freshness vs. git activity (Step 8).
    from scripts.audit import group_g
    audit_detector.register_group("G", group_g.run)
