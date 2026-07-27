"""Per-journey browser-test coverage.

Generation used to be skipped wholesale the moment ``e2e/`` contained any
``.spec.ts`` file at all, so the first journey got a test and every journey
added to the plan afterwards got nothing — and nothing reported the gap.

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
from journey_coverage import check_journey_coverage  # noqa: E402

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


def _project(tmp_path: Path, *, plan: str | None = PLAN, specs=(), adopted=False) -> Path:
    planning = tmp_path / ".shipwright" / "planning" / "01-core"
    planning.mkdir(parents=True)
    if plan is not None:
        (planning / "claude-plan-e2e.md").write_text(plan, encoding="utf-8")
    if specs:
        flows = tmp_path / "e2e" / "flows"
        flows.mkdir(parents=True)
        for name, body in specs:
            (flows / name).write_text(body, encoding="utf-8")
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"adoption": {"adopted_at": "2026-01-01"}} if adopted else {"scope": "full_app"}),
        encoding="utf-8",
    )
    return tmp_path


def _read_triage(project: Path) -> list[dict]:
    path = project / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# check_journey_coverage — the per-journey answer
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_a_journey_with_no_spec_is_reported_even_though_other_specs_exist(tmp_path):
    """AC1 — the defect itself: one spec file used to silence the whole check."""
    project = _project(tmp_path, specs=[
        ("01-user-registration.spec.ts", "test('signs up', async () => {});"),
    ])
    report = check_journey_coverage(project, emit_triage=False)

    assert report["status"] == "gaps"
    assert [j["identity"] for j in report["covered"]] == ["01-user-registration"]
    assert [j["identity"] for j in report["uncovered"]] == [
        "02-course-enrollment", "03-checkout",
    ]


@pytest.mark.covers("FR-01.06")
def test_every_journey_covered_is_a_clean_report(tmp_path):
    project = _project(tmp_path, specs=[
        ("01-user-registration.spec.ts", "x"),
        ("02-course-enrollment.spec.ts", "x"),
        ("03-checkout.spec.ts", "x"),
    ])
    report = check_journey_coverage(project, emit_triage=False)

    assert report["status"] == "covered"
    assert report["uncovered"] == []
    assert report["blocking"] is False


@pytest.mark.covers("FR-01.06")
def test_a_journey_named_only_inside_a_spec_body_counts_as_covered(tmp_path):
    # Filename does not match, but the spec declares the journey by title.
    project = _project(tmp_path, specs=[
        ("all-flows.spec.ts",
         "test.describe('User Registration', () => {});\n"
         "test.describe('Course Enrollment', () => {});\n"
         "test.describe('Checkout', () => {});\n"),
    ])
    report = check_journey_coverage(project, emit_triage=False)
    assert report["status"] == "covered"


@pytest.mark.covers("FR-01.06")
def test_specs_are_found_anywhere_under_the_e2e_tree(tmp_path):
    project = _project(tmp_path)
    nested = project / "e2e" / "suites" / "deep"
    nested.mkdir(parents=True)
    for name in ("01-user-registration.spec.ts", "02-course-enrollment.spec.ts",
                 "03-checkout.spec.ts"):
        (nested / name).write_text("x", encoding="utf-8")

    assert check_journey_coverage(project, emit_triage=False)["status"] == "covered"


# ---------------------------------------------------------------------------
# Honesty: three states, never a false "uncovered"
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_no_plan_file_is_undetermined_with_a_diagnostic(tmp_path):
    project = _project(tmp_path, plan=None)
    report = check_journey_coverage(project, emit_triage=False)

    assert report["status"] == "undetermined"
    assert report["blocking"] is False
    assert report["diagnostic"]


@pytest.mark.covers("FR-01.06")
def test_a_plan_with_no_parseable_journeys_is_undetermined_not_covered(tmp_path):
    project = _project(tmp_path, plan="# E2E Test Plan\n\nfree prose, no flows\n")
    report = check_journey_coverage(project, emit_triage=False)

    assert report["status"] == "undetermined"
    assert "no user journeys" in report["diagnostic"].lower()


@pytest.mark.covers("FR-01.06")
def test_no_e2e_directory_leaves_generation_to_the_existing_step(tmp_path):
    # Nothing generated yet is step-2.5's own job, not a coverage gap.
    project = _project(tmp_path)
    report = check_journey_coverage(project, emit_triage=False)

    assert report["status"] == "no_specs"
    assert report["blocking"] is False


# ---------------------------------------------------------------------------
# AC2 — greenfield blocks, brownfield files a follow-up
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_greenfield_gaps_block(tmp_path):
    project = _project(tmp_path, specs=[("01-user-registration.spec.ts", "x")])
    report = check_journey_coverage(project, emit_triage=False)

    assert report["mode"] == "greenfield"
    assert report["blocking"] is True


@pytest.mark.covers("FR-01.06")
def test_brownfield_gaps_do_not_block_and_leave_a_follow_up(tmp_path):
    project = _project(tmp_path, adopted=True,
                       specs=[("01-user-registration.spec.ts", "x")])
    report = check_journey_coverage(project)

    assert report["mode"] == "brownfield"
    assert report["blocking"] is False
    assert report["triage_appended"] == 2

    items = [i for i in _read_triage(project) if i.get("event") == "append"]
    assert len(items) == 2
    assert {i["dedupKey"] for i in items} == {
        "journey-coverage:02-course-enrollment", "journey-coverage:03-checkout",
    }


@pytest.mark.covers("FR-01.06")
def test_the_brownfield_follow_up_routes_to_the_onboarding_phase(tmp_path):
    """External review R5 — routing is the structured launchPayload field."""
    project = _project(tmp_path, adopted=True,
                       specs=[("01-user-registration.spec.ts", "x")])
    check_journey_coverage(project)

    items = [i for i in _read_triage(project) if i.get("event") == "append"]
    assert all(i["launchPayload"].startswith("/shipwright-adopt") for i in items)
    assert all(i["frId"] == "FR-01.06" for i in items)


@pytest.mark.covers("FR-01.06")
def test_greenfield_gaps_do_not_flood_triage(tmp_path):
    # Greenfield blocks the run instead; the gap is not a backlog item.
    project = _project(tmp_path, specs=[("01-user-registration.spec.ts", "x")])
    report = check_journey_coverage(project)

    assert report["triage_appended"] == 0
    assert _read_triage(project) == []


@pytest.mark.covers("FR-01.06")
def test_a_persistent_gap_stays_one_follow_up_across_runs(tmp_path):
    project = _project(tmp_path, adopted=True,
                       specs=[("01-user-registration.spec.ts", "x")])
    first = check_journey_coverage(project)
    second = check_journey_coverage(project)

    assert first["triage_appended"] == 2
    assert second["triage_appended"] == 0
    assert len([i for i in _read_triage(project) if i.get("event") == "append"]) == 2


@pytest.mark.covers("FR-01.06")
def test_two_journeys_with_the_same_title_stay_two_follow_ups(tmp_path):
    project = _project(
        tmp_path, adopted=True,
        plan="## User Flows\n\n### Flow 1: Checkout\n\n### Flow 2: Checkout\n",
        specs=[("00-unrelated.spec.ts", "x")],
    )
    report = check_journey_coverage(project)

    assert report["triage_appended"] == 2
    keys = {i["dedupKey"] for i in _read_triage(project) if i.get("event") == "append"}
    assert keys == {"journey-coverage:01-checkout", "journey-coverage:02-checkout"}
