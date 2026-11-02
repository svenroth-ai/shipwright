"""The "no test was scanned" note for the cross-layer gate's failure text (GitHub issue #972).

Split out of ``layer_coverage.py`` to keep that module under the 300-line cap (ADR-099).
"""

from __future__ import annotations


def no_scan_note(head: dict) -> str:
    """A note for the failure text when the regenerated head manifest links NO test at all.

    "No executed-passing test" is the wrong diagnosis when the collector never saw a test: the
    project's tests sit outside the folders it scans (a nested ``server/`` + ``client/`` layout
    has none of the conventional top-level ones). The gate enumerates untagged tests too, so an
    orphan, an untagged test or a malformed tag each prove that test files WERE scanned and keep
    the note silent (the fix is then the tag, not the folders). Never raises -- a malformed
    manifest just yields no note and the original advice stands.
    """
    try:
        for node in (head.get("requirements") or {}).values():
            if isinstance(node, dict) and any((node.get("tests") or {}).values()):
                return ""
        if head.get("orphans") or head.get("untagged_tests") or head.get("invalid_tags"):
            return ""
    except (AttributeError, TypeError):
        return ""
    return (
        "the regenerated traceability manifest links no test at all, so no test file was found "
        "in the folders the collector scans. If the project already has tests, they sit outside "
        "those folders: set traceability.test_roots in shipwright_compliance_config.json (a stack "
        "profile's test_roots reaches this gate only when shipwright_run_config.json is committed)"
    )
