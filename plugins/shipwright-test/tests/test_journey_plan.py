"""Reading planned user journeys out of the E2E plan.

Split from ``test_journey_coverage.py`` to mirror the module split (and keep
both files inside the 300-line guideline): this pins *what the plan promised*,
the sibling pins *whether it is tested*.

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
from journey_plan import parse_journeys, slugify  # noqa: E402
from text_safety import sanitize  # noqa: E402

PLAN = """# E2E Test Plan

## Test Environment
- Base URL: http://localhost:3000

## User Flows

### Flow 1: User Registration
- Navigate to /auth/signup

### Flow 2: Course Enrollment
- Browse the catalogue

### Flow 3: Checkout
- Pay

## Page Object Model

### LoginPage
- URL: /auth/login
"""



@pytest.mark.covers("FR-01.06")
def test_flows_are_read_from_the_plan_in_order():
    journeys = parse_journeys(PLAN)
    assert [j.title for j in journeys] == [
        "User Registration", "Course Enrollment", "Checkout",
    ]
    assert [j.slug for j in journeys] == [
        "user-registration", "course-enrollment", "checkout",
    ]


@pytest.mark.covers("FR-01.06")
def test_page_object_headings_are_not_mistaken_for_journeys():
    # `### LoginPage` sits under Page Object Model, not User Flows.
    assert "LoginPage" not in [j.title for j in parse_journeys(PLAN)]


@pytest.mark.covers("FR-01.06")
def test_journey_identity_carries_its_position_so_duplicates_stay_distinct():
    plan = "## User Flows\n\n### Flow 1: Checkout\n\n### Flow 2: Checkout\n"
    journeys = parse_journeys(plan)
    assert len(journeys) == 2
    assert journeys[0].identity != journeys[1].identity
    assert journeys[0].identity == "01-checkout"
    assert journeys[1].identity == "02-checkout"


@pytest.mark.covers("FR-01.06")
def test_a_plan_with_no_flows_yields_nothing():
    assert parse_journeys("# E2E Test Plan\n\nNothing here.\n") == []


@pytest.mark.covers("FR-01.06")
def test_a_plainly_headed_journey_is_read_too():
    """External code review C2 — the `Flow N:` prefix is canonical, not required.

    A hand-written or older plan that heads journeys plainly must not report
    `undetermined`; that would hand back the all-or-nothing behaviour.
    """
    plan = "## User Flows\n\n### User Registration\n- go\n\n### Checkout\n- pay\n"
    assert [j.title for j in parse_journeys(plan)] == ["User Registration", "Checkout"]


@pytest.mark.covers("FR-01.06")
def test_both_spellings_of_the_same_journey_give_the_same_slug():
    prefixed = parse_journeys("## User Flows\n\n### Flow 7: Checkout\n")
    plain = parse_journeys("## User Flows\n\n### Checkout\n")
    assert prefixed[0].slug == plain[0].slug == "checkout"
    assert prefixed[0].title == plain[0].title == "Checkout"


@pytest.mark.covers("FR-01.06")
def test_numbered_steps_are_not_mistaken_for_journeys():
    # The numbered/bulleted lines under a heading are the journey's STEPS.
    # Reading them as journeys would manufacture phantom gaps.
    plan = "## User Flows\n\n### Checkout\n1. Add to cart\n2. Pay\n- Confirm\n"
    assert [j.title for j in parse_journeys(plan)] == ["Checkout"]


@pytest.mark.covers("FR-01.06")
def test_control_characters_in_a_title_are_stripped():
    """A plan heading must not be able to rewrite the operator's terminal."""
    plan = "## User Flows\n\n### Check\x1b[31mout\x00\n"
    [journey] = parse_journeys(plan)
    assert journey.title == "Check[31mout"
    assert "\x1b" not in journey.title and "\x00" not in journey.title
    assert "\x1b" not in journey.identity


@pytest.mark.covers("FR-01.06")
def test_sanitize_keeps_ordinary_text_and_collapses_whitespace():
    assert sanitize("  Sign   up  ") == "Sign up"
    assert sanitize("Sign	up") == "Sign up"


@pytest.mark.covers("FR-01.06")
def test_slugify_is_derived_from_the_cleaned_string():
    # Or the same journey could key two ways in triage.
    assert slugify("Checkout") == "checkout"
    assert slugify("  Sign   Up  ") == "sign-up"
