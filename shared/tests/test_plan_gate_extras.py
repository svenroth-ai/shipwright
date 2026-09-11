"""FR-01.03 #1, #8, #10, #11 — the four plan-phase gates the ledger walk
found nowhere in code. One test class per criterion, named for it.
"""

from lib.plan_gate_extras import (
    decisions_recorded,
    e2e_journeys_named,
    findings_addressed,
    review_key_honesty,
)


# --------------------------------------------------------------------------- #
# #1 — review_key_honesty
# --------------------------------------------------------------------------- #


def test_available_route_and_completed_marker_is_honest():
    marker = {"status": "completed", "verdicts": {"glm": "approve", "openai": "approve"}}
    assert review_key_honesty(marker, "available").ok is True


def test_available_route_but_skipped_marker_is_a_violation():
    marker = {"status": "skipped_user_opt_out", "reason": "offline demo"}
    result = review_key_honesty(marker, "available")
    assert result.ok is False
    assert "silently skipped" in result.detail


def test_missing_keys_route_permits_a_skip():
    marker = {"status": "skipped_user_opt_out", "reason": "no keys"}
    assert review_key_honesty(marker, "missing_keys").ok is True


def test_user_disabled_route_permits_a_skip():
    marker = {"status": "skipped_config_disabled", "reason": "feedback_iterations: 0"}
    assert review_key_honesty(marker, "user_disabled").ok is True


def test_no_marker_yet_is_not_a_false_skip():
    assert review_key_honesty(None, "available").ok is True


# --------------------------------------------------------------------------- #
# #8 — decisions_recorded
# --------------------------------------------------------------------------- #

LOG_WITH_INTERVIEW_DECISION = """# Decision Log

---

### ADR-001: ORM over raw SQL
- **Date:** 2026-07-23
- **Section:** Plan Interview — 01-auth
- **Context:** x
- **Decision:** y
- **Commit:** n/a
"""

LOG_WITH_UNRELATED_SPLIT = """# Decision Log

---

### ADR-001: Something else
- **Date:** 2026-07-23
- **Section:** Plan Interview — 02-billing
- **Context:** x
- **Decision:** y
- **Commit:** n/a
"""


def test_a_logged_interview_decision_satisfies_the_gate():
    result = decisions_recorded(LOG_WITH_INTERVIEW_DECISION, "01-auth")
    assert result.ok is True


def test_no_entry_for_this_split_fails():
    result = decisions_recorded("# Decision Log\n", "01-auth")
    assert result.ok is False
    assert "01-auth" in result.detail


def test_an_entry_for_a_different_split_does_not_count():
    result = decisions_recorded(LOG_WITH_UNRELATED_SPLIT, "01-auth")
    assert result.ok is False


def test_a_non_plan_section_tag_does_not_count():
    log = (
        "# Decision Log\n\n---\n\n### ADR-001: x\n"
        "- **Section:** Build — 01-auth\n- **Context:** x\n- **Decision:** y\n- **Commit:** n/a\n"
    )
    assert decisions_recorded(log, "01-auth").ok is False


# --------------------------------------------------------------------------- #
# #10 — findings_addressed
# --------------------------------------------------------------------------- #

LOG_TWO_EXTERNAL_REVIEW_FINDINGS = """# Decision Log

---

### ADR-001: fix a
- **Section:** External Review — 01-auth
- **Context:** x
- **Decision:** y
- **Commit:** n/a

---

### ADR-002: decline b
- **Section:** External Review — 01-auth
- **Context:** x
- **Decision:** y
- **Commit:** n/a
"""


def test_zero_findings_needs_nothing_logged():
    assert findings_addressed("# Decision Log\n", "01-auth", 0).ok is True


def test_findings_count_met_by_logged_entries():
    result = findings_addressed(LOG_TWO_EXTERNAL_REVIEW_FINDINGS, "01-auth", 2)
    assert result.ok is True


def test_findings_count_exceeds_logged_entries():
    result = findings_addressed(LOG_TWO_EXTERNAL_REVIEW_FINDINGS, "01-auth", 5)
    assert result.ok is False
    assert "5" in result.detail and "2" in result.detail


def test_findings_for_a_different_split_do_not_count():
    log = LOG_TWO_EXTERNAL_REVIEW_FINDINGS.replace("01-auth", "02-billing")
    result = findings_addressed(log, "01-auth", 1)
    assert result.ok is False


LOG_TWO_INTERNAL_REVIEW_FINDINGS = LOG_TWO_EXTERNAL_REVIEW_FINDINGS.replace(
    "External Review", "Internal Plan Review"
)


def test_internal_review_carrying_the_gate_counts_too():
    """Stage-1 spec review, iterate-2026-09-11-e1-checks-plan-design (2nd
    pass): when no external key is available, the Pre-5b Checkpoint has
    Step 5b set `findings_count` from the internal review (opus-plan-
    reviewer) instead, whose findings are logged as `"Internal Plan Review
    — {split}"`, not `"External Review — {split}"` (step-5-external-
    review.md). Counting only the external tag false-failed this real,
    documented path."""
    result = findings_addressed(LOG_TWO_INTERNAL_REVIEW_FINDINGS, "01-auth", 2)
    assert result.ok is True


# --------------------------------------------------------------------------- #
# #11 — e2e_journeys_named
# --------------------------------------------------------------------------- #


def test_non_ui_project_needs_no_e2e_file(tmp_path):
    result = e2e_journeys_named(tmp_path / "claude-plan-e2e.md", expect_e2e=False)
    assert result.ok is True


def test_ui_project_missing_the_file_fails(tmp_path):
    result = e2e_journeys_named(tmp_path / "claude-plan-e2e.md", expect_e2e=True)
    assert result.ok is False
    assert "does not exist" in result.detail


def test_a_file_with_no_flow_heading_fails(tmp_path):
    p = tmp_path / "claude-plan-e2e.md"
    p.write_text("# E2E Test Plan\n\n## Test Environment\n- Base URL: x\n", encoding="utf-8")
    result = e2e_journeys_named(p, expect_e2e=True)
    assert result.ok is False
    assert "names no flow" in result.detail


def test_a_file_naming_a_flow_passes(tmp_path):
    p = tmp_path / "claude-plan-e2e.md"
    p.write_text(
        "# E2E Test Plan\n\n## User Flows\n\n### Flow 1: User Registration\n- steps\n",
        encoding="utf-8",
    )
    result = e2e_journeys_named(p, expect_e2e=True)
    assert result.ok is True


def test_a_flow_shaped_word_with_no_number_does_not_count(tmp_path):
    """Stage-2 code review, iterate-2026-09-11-e1-checks-plan-design: the
    original `.*flow.*` regex matched any heading containing "flow" as a
    substring ("## Workflow Notes", "## Overflow Handling"), not a
    numbered journey — silently defeating the guarantee this gate exists
    to add."""
    p = tmp_path / "claude-plan-e2e.md"
    p.write_text(
        "# E2E Test Plan\n\n## Workflow Notes\n\n## Overflow Handling\n- steps\n",
        encoding="utf-8",
    )
    result = e2e_journeys_named(p, expect_e2e=True)
    assert result.ok is False
    assert "names no flow" in result.detail
