"""I9 (M7 "Rewritability") — rendering for the rationale-link check.

Split out of ``group_i`` the moment its addition first crossed the 300-line
size guideline, following the same bloat-extraction recipe already used for
``group_i_rows`` / ``group_i_criteria`` / ``group_i_tbd_age`` (see each
module's own docstring): the detector lives in its own pure sibling,
``group_i`` keeps only finding assembly.

The classification itself (linked / unlinked / could_not_determine) lives one
hop further out, in ``shared/scripts/lib/rewritability_links.py`` — this
module is a thin renderer over that scan's result. It stays a *separate*
module from ``group_i.py`` rather than one more function inside it because
rendering needs ``group_i``'s own ``_finding``/``_PREVIEW_CAP`` — importing
those back from a module ``group_i`` itself imports would be circular — so
this module returns plain text, and ``group_i._rewritability_finding`` wraps
it in a ``Finding``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from scripts.audit.audit_adapters import load_shared_lib

_PREVIEW_CAP = 5


def rewritability_detail(project_root: Path, fr_ids: Iterable[str]) -> str:
    """One rendered detail string for I9.

    Always the advisory/``pass`` wording — see ``group_i._ADVISORY_CHECKS``'
    comment for why this check can never fail a build, including when the
    event log itself could not be read.
    """
    rw = load_shared_lib("rewritability_links")
    try:
        scan = rw.scan_fr_rationale_links(project_root, fr_ids)
    except rw.EventLogUnreadable as exc:
        # "NOT EVALUATED" up front, deliberately — external plan review (glm,
        # low): a reader skimming the dashboard must not mistake this for the
        # clean "all requirements linked" pass below, which starts with
        # different words for exactly this reason.
        return (
            f"advisory — NOT EVALUATED: could not read the event log to "
            f"check rationale links this run: {exc}"
        )

    # "co-occurring" / "proxy signal", not "explains" or "documents" —
    # external plan review (openai, HIGH): the underlying signal is run-level
    # (a run that changed this FR also wrote SOME decision-drop/ADR), not a
    # verified claim that the ADR's prose is ABOUT this specific requirement.
    # Stated in the rendered text itself, not only in the module docstring a
    # dashboard reader never opens.
    if scan.unlinked:
        shown = ", ".join(scan.unlinked[:_PREVIEW_CAP])
        more = (f" (+{len(scan.unlinked) - _PREVIEW_CAP} more)"
                if len(scan.unlinked) > _PREVIEW_CAP else "")
        unlinked_part = (
            f"{len(scan.unlinked)} requirement(s) changed in a run with no "
            f"decision-drop/ADR of its own (no co-occurring rationale "
            f"record): {shown}{more}"
        )
    else:
        unlinked_part = None
    if scan.could_not_determine:
        undetermined_part = (
            f"{len(scan.could_not_determine)} requirement(s) with no "
            f"recorded change history at all — cannot determine"
        )
    else:
        undetermined_part = None
    parts = [p for p in (unlinked_part, undetermined_part) if p]
    if not parts:
        # Guards the vacuous case (external code review, glm, low): with no
        # `fr_ids` at all, `scan.linked` is also empty, and "all 0
        # requirement(s) ... were changed" reads as a false claim rather than
        # an empty one. `group_i.run()`'s own STATE_ROWS branch never reaches
        # this function with an empty `rows`, but the lib function is public,
        # so guarding here rather than trusting every future caller.
        if not scan.linked:
            return "no requirements to evaluate this run"
        return (
            f"all {len(scan.linked)} requirement(s) with recorded changes "
            f"were changed in a run that also recorded a decision-drop/ADR "
            f"(co-occurring rationale — a proxy signal, not a verified "
            f"per-requirement link; see rewritability_links.py)"
        )
    corrupt = (f"; {scan.corrupt_fragments} unreadable event-log fragment(s)"
               if scan.corrupt_fragments else "")
    return "advisory — " + "; ".join(parts) + corrupt


__all__ = ["rewritability_detail"]
