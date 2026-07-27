"""The follow-up that takes the derived catalogue to a person (FR-01.13).

Split from ``derived_catalogue`` at the 300-LOC source cap, and the seam is a
real one rather than a size accident: that module owns the *model* and the block
that describes it, this one owns the **card Step E.18 files**. A module that
merely describes a catalogue has no business knowing about the Triage Inbox.

The card exists because reading the code is a start and is not enough. Note the
scope that made it necessary: the campaign phase that grills requirements covers
Shipwright's own repositories — nothing else would ever give an ONBOARDED
project the same treatment, so onboarding files the follow-up itself.

Imports no ``lib`` package (ADR-045): Step E.18 loads it bare, in an interpreter
that must leave ``lib`` free for the shared ``triage``'s own ``lib.file_lock``.
"""

from __future__ import annotations

from typing import Any

try:  # tool context: lib/ is on sys.path
    from derived_catalogue import (
        CONFIRMATION_DEDUP_KEY,
        ELICITATION_DOC,
        SUMMARY_REL,
        DerivedCatalogue,
    )
except ImportError:  # test / package context: scripts/ on sys.path
    from lib.derived_catalogue import (  # type: ignore[no-redef]
        CONFIRMATION_DEDUP_KEY,
        ELICITATION_DOC,
        SUMMARY_REL,
        DerivedCatalogue,
    )


def confirmation_triage(
    catalogue: DerivedCatalogue, *, split_name: str,
) -> dict[str, Any] | None:
    """The follow-up that takes the derived catalogue to a person.

    Returns ``None`` when every requirement was already confirmed — there is
    nothing to ask. Filed by Step E.18, which is the first step that runs after
    the Triage Inbox exists (Step E.16).

    The count is stated **as of onboarding**, not as a live figure. The dedup key
    is deliberately count-free so a re-adopt duplicates nothing, and the triage
    layer has no update path — so a card claiming to hold the current number
    would go quietly stale. An as-of statement stays true, and the card points at
    ``SUMMARY_REL`` for what is true now.
    """
    if catalogue.unconfirmed == 0:
        return None
    spec_rel = f".shipwright/planning/{split_name}/spec.md"
    detail = (
        f"At onboarding, {catalogue.total} requirement(s) in `{spec_rel}` were "
        f"derived by reading this codebase and {catalogue.unconfirmed} had been "
        f"confirmed by nobody. Work through them with someone who knows the "
        f"product, following `{ELICITATION_DOC}` — one question at a time, each "
        f"with a recommendation, and not finished until every context dimension "
        f"is answered or explicitly recorded as an assumption. Update each row's "
        f"`Basis` to `interview` as it is confirmed. These figures are as of "
        f"onboarding; `{SUMMARY_REL}` carries the current ones and is refreshed "
        f"on every adopt run."
    )
    return {
        "dedup_key": CONFIRMATION_DEDUP_KEY,
        "severity": "high",
        "kind": "improvement",
        "title": (
            f"Confirm the derived requirements catalogue with a person "
            f"({catalogue.unconfirmed} unconfirmed at onboarding)"
        ),
        "detail": detail,
        "fr_id": None,
    }


__all__ = ["confirmation_triage"]
