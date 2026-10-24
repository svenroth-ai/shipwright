"""Design gate #9 (iteration touches only the flagged screens), extracted from
``design_gate_extras`` (which re-exports it). Behaviour unchanged."""

from __future__ import annotations

import re

try:
    from .design_gate_result import GateResult  # loaded as lib.<module> (shared/tests)
except ImportError:
    # loaded as top-level — check-design-gates.py puts shared/scripts/lib itself on sys.path.
    from design_gate_result import GateResult


# --------------------------------------------------------------------------- #
# #9 — iteration touches only the flagged screen(s)
# --------------------------------------------------------------------------- #

_ROUND_ENTRY_RE = re.compile(
    r"^###\s+#\d+\s+.+?\s+—\s+(?P<status>CHANGES|REJECTED|APPROVED|REVIEWED)\s*$"
    r"\n\n\*\*File:\*\*\s*(?P<file>\S+)",
    re.MULTILINE,
)


def parse_feedback_round(content: str) -> list[tuple[str, str]]:
    """``[(file, status)]`` for every per-screen entry in a
    ``design-feedback-round{N}.md`` export (format:
    ``review-viewer-template.md``'s ``exportFeedback``)."""
    return [(m.group("file"), m.group("status")) for m in _ROUND_ENTRY_RE.finditer(content)]


def iteration_touched_flagged_screens(
    flagged_files: list[str], git_modified_files: list[str]
) -> GateResult:
    """**#9** — every screen flagged CHANGES/REJECTED in this round must
    actually have been touched. Extra modified files beyond the flagged set
    are a warning, not a failure: Chrome Change Propagation legitimately
    touches every screen in one round, indistinguishable from a drive-by
    change without reading the decision log."""
    modified = set(git_modified_files)
    untouched = [f for f in flagged_files if f not in modified]
    if untouched:
        return GateResult(
            False,
            f"{len(untouched)} flagged screen(s) were not actually regenerated: {untouched}",
        )
    extra = sorted(modified - set(flagged_files))
    warnings = (
        (f"{len(extra)} screen(s) changed beyond the flagged set: {extra} — "
         "legitimate if this round was a chrome-wide propagation",)
        if extra else ()
    )
    return GateResult(True, f"all {len(flagged_files)} flagged screen(s) were touched", warnings)
