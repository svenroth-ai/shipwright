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

    Missing groups (not yet implemented in this plan's Steps 4-8) are
    silently absent from the registry; the detector's ``run_all`` reports
    them as ``groups_skipped`` with reason ``not-implemented``.
    """
    # Reset registry to avoid double-registration when called twice
    # (tests call this repeatedly with fresh fixtures).
    audit_detector._GROUPS.clear()

    # Group A — Artifact / path integrity (Step 4).
    from scripts.audit import group_a
    audit_detector.register_group("A", group_a.run)

    # Group C — Planning coherence (Step 6).
    from scripts.audit import group_c
    audit_detector.register_group("C", group_c.run)

    # Group D — Event-log FR coverage (Step 4).
    from scripts.audit import group_d
    audit_detector.register_group("D", group_d.run)

    # Group F — ADR structural integrity (Step 6).
    from scripts.audit import group_f
    audit_detector.register_group("F", group_f.run)

    # Steps 5/7/8 add Groups B, E, G here.
