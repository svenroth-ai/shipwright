"""Pure shape check for one acceptance criterion (Group I — I7).

iterate-2026-09-06-fr-hygiene-touched-rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.fr_criterion_shape import is_well_formed_criterion  # noqa: E402


def test_well_formed_given_when_then():
    assert is_well_formed_criterion(
        "Given a registered user, when they submit valid credentials, "
        "then they are signed in.",
    )


def test_case_insensitive():
    assert is_well_formed_criterion("GIVEN x, WHEN y, THEN z.")


def test_out_of_order_is_not_well_formed():
    assert not is_well_formed_criterion("When y, given x, then z.")


def test_prose_status_report_is_not_well_formed():
    assert not is_well_formed_criterion(
        "Scaffold-creation half - verified (auth.ts, test_auth.py): "
        "confirmed by running the existing suite. Write-denial half - not "
        "yet covered.",
    )


def test_whole_word_keywords_only():
    """'whenever'/'thenceforth' must not satisfy the shape by substring."""
    assert not is_well_formed_criterion("Given x, whenever y, thenceforth z.")


def test_empty_is_not_well_formed():
    assert not is_well_formed_criterion("")
