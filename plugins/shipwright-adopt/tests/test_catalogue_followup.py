"""The follow-up that takes the derived catalogue to a person (FR-01.13/AC03).

``catalogue_followup.confirmation_triage`` is the real, deterministic seam:
reading the code is a start and is not enough, so onboarding must leave a
tracked follow-up (a Triage Inbox card) that walks the derived requirements
through the shared questioning method (`requirement-elicitation.md`) with a
person. These tests exercise the real function against a real
``DerivedCatalogue``, not a re-implementation of its logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.catalogue_followup import confirmation_triage  # noqa: E402
from lib.derived_catalogue import (  # noqa: E402
    CONFIRMATION_DEDUP_KEY,
    ELICITATION_DOC,
    DerivedCatalogue,
    DerivedRequirement,
)


def _catalogue(*, confirmed: int, unconfirmed: int) -> DerivedCatalogue:
    reqs = tuple(
        DerivedRequirement(fr_id=f"FR-01.{i:02d}", name=f"req-{i}", basis="interview", confirmed=True)
        for i in range(confirmed)
    ) + tuple(
        DerivedRequirement(fr_id=f"FR-02.{i:02d}", name=f"req-{i}", basis="code", confirmed=False)
        for i in range(unconfirmed)
    )
    return DerivedCatalogue(split_name="01-adopted", requirements=reqs)


@pytest.mark.covers("FR-01.13/AC03")
def test_unconfirmed_requirements_leave_a_tracked_follow_up() -> None:
    """The real behavior: reading code is not enough, so a card is filed."""
    catalogue = _catalogue(confirmed=1, unconfirmed=3)
    card = confirmation_triage(catalogue, split_name="01-adopted")

    assert card is not None
    assert card["dedup_key"] == CONFIRMATION_DEDUP_KEY
    assert card["severity"] == "high"
    # Pinned to the exact phrase, not a bare digit, so a coincidental "3"
    # elsewhere (a date, an FR-id fragment) cannot make this pass falsely
    # (external code review, glm, low).
    assert "(3 unconfirmed at onboarding)" in card["title"]
    assert "3 had been confirmed by nobody" in card["detail"]
    # The card names the shared questioning method, not an ad-hoc one.
    assert ELICITATION_DOC in card["detail"]
    assert "01-adopted" in card["detail"]


@pytest.mark.covers("FR-01.13/AC03")
def test_a_fully_confirmed_catalogue_files_no_follow_up() -> None:
    """No unconfirmed requirement means there is nothing left to grill —
    filing a card here would be a false positive, not caution."""
    catalogue = _catalogue(confirmed=2, unconfirmed=0)
    assert confirmation_triage(catalogue, split_name="01-adopted") is None


@pytest.mark.covers("FR-01.13/AC03")
def test_the_card_states_totals_as_of_onboarding_not_a_live_count() -> None:
    """The count is a snapshot; the card must say so rather than imply the
    figure stays accurate as the project evolves."""
    catalogue = _catalogue(confirmed=0, unconfirmed=5)
    card = confirmation_triage(catalogue, split_name="01-adopted")

    assert card is not None
    # Pinned to the production sentence, not a bare substring, so wording
    # drift that drops the semantic claim would fail this test rather than
    # coincidentally still contain the words (external code review, glm, low).
    assert "These figures are as of onboarding" in card["detail"]
    assert "5 had been confirmed by nobody" in card["detail"]
