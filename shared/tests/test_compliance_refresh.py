"""The refresh set, its classification, and how a refresh judges itself.

Subject: ``shared/scripts/lib/compliance_refresh.py`` — the pure half of the
release-time / on-demand compliance refresh (Weg B,
iterate-2026-07-31-derived-docs-at-release). No git and no compliance plugin is
needed to run any of this, which is the point of the ``lib`` ⟷ ``tools`` split.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.churn_merge import (  # noqa: E402
    CI_SECURITY_SUMMARY,
    COMPLIANCE_MDS,
    TEST_RESULTS,
    TEST_TRACEABILITY,
)
from lib.compliance_refresh import (  # noqa: E402
    CLASSIFICATION,
    CONTENT_FLOOR_RATIO,
    DERIVES_FROM_CI_HISTORY,
    DERIVES_FROM_TREE,
    EXCLUDED,
    PRODUCER_TARGETS,
    REFRESH_SET,
    RUN_WRITTEN,
    SESSION_SCOPED,
    SUCCESS_OUTCOMES,
    TREE_DERIVED,
    branch_name,
    content_floor_violation,
    converged,
    docs_commit_message,
    failed_paths,
    pr_body,
    unclassified,
)
from lib.derived_snapshots import DERIVED_SNAPSHOTS  # noqa: E402

_COMPLIANCE_DIR = ".shipwright/compliance/"


# --- AC-1: the set is declared, and complete ---------------------------------


def test_every_derived_snapshot_carries_a_classification():
    """AC-1. A new derived snapshot with no class fails HERE rather than
    defaulting into or out of the refresh set silently."""
    assert unclassified() == frozenset(), (
        "these DERIVED_SNAPSHOTS paths have no entry in CLASSIFICATION — decide "
        f"whether a refresh may rewrite them: {sorted(unclassified())}"
    )


def test_refresh_set_is_exactly_the_compliance_directory():
    """AC-1. The literal and the directory rule agree.

    ``REFRESH_SET`` is written out as a literal so widening it is a deliberate
    edit, but a literal can fall behind. This pins the two definitions together
    without letting the prefix rule BE the definition — a new file dropped into
    the compliance directory fails this test instead of joining the commit,
    UNLESS it is explicitly named in ``EXCLUDED`` (a second producer sharing
    the directory, e.g. the throughput report — a decision, not an oversight).
    """
    by_directory = {
        rel for rel in CLASSIFICATION
        if rel.startswith(_COMPLIANCE_DIR) and rel not in EXCLUDED
    }
    assert REFRESH_SET == by_directory


def test_the_refresh_set_is_the_seven():
    assert REFRESH_SET == frozenset(COMPLIANCE_MDS) | {
        TEST_TRACEABILITY, CI_SECURITY_SUMMARY,
    }
    assert len(REFRESH_SET) == 7


# --- AC-2: every exclusion is named, with a reason ---------------------------


def test_every_non_refreshed_snapshot_is_excluded_by_name_with_a_reason():
    """AC-2. Exclusion by omission is indistinguishable from an oversight."""
    assert frozenset(EXCLUDED) == frozenset(DERIVED_SNAPSHOTS) - REFRESH_SET
    for rel, reason in EXCLUDED.items():
        assert reason.strip(), f"{rel} is excluded with an empty reason"


@pytest.mark.parametrize(
    "rel,expected",
    [
        (".shipwright/agent_docs/build_dashboard.md", SESSION_SCOPED),
        (".shipwright/agent_docs/session_handoff.md", SESSION_SCOPED),
        (TEST_RESULTS, RUN_WRITTEN),
        (CI_SECURITY_SUMMARY, DERIVES_FROM_CI_HISTORY),
        (TEST_TRACEABILITY, DERIVES_FROM_TREE),
    ],
)
def test_the_load_bearing_classifications(rel, expected):
    """Each of these was decided for a stated reason and must not drift."""
    assert CLASSIFICATION[rel] == expected


def test_triage_inbox_is_tree_derived_yet_deliberately_out_of_the_set():
    """AC-2. The one exclusion its class does NOT explain.

    It is genuinely tree-derived and genuinely refreshable — it is out because it
    lives outside the compliance directory and the release phase does not
    recompute it. Recorded as a scope pin so a later hand reads it as a decision
    rather than as a classification mistake to 'fix'.
    """
    rel = ".shipwright/agent_docs/triage_inbox.md"
    assert CLASSIFICATION[rel] == DERIVES_FROM_TREE
    assert rel not in REFRESH_SET
    assert "outside the compliance directory" in EXCLUDED[rel].lower()


def test_no_session_scoped_or_run_written_path_can_reach_the_refresh_set():
    """AC-2. The invariant, not just the current membership."""
    for rel in REFRESH_SET:
        assert CLASSIFICATION[rel] in {DERIVES_FROM_TREE, DERIVES_FROM_CI_HISTORY}


def test_the_producer_is_asked_for_exactly_what_we_commit():
    """``regenerate_tracked_snapshots`` expands any COMPLIANCE_MDS member into one
    ``_update_compliance`` call that also rewrites both ``.json`` snapshots. So
    asking for the five MDs asks for exactly the seven — naming the ``.json``
    paths too would be a no-op that reads as if they were separately producible."""
    assert PRODUCER_TARGETS == frozenset(COMPLIANCE_MDS)
    assert PRODUCER_TARGETS <= REFRESH_SET
    assert REFRESH_SET - PRODUCER_TARGETS == {TEST_TRACEABILITY, CI_SECURITY_SUMMARY}


# --- AC-3: convergence is claimed only where it is claimable -----------------


def test_ci_security_is_outside_the_fixpoint_claim():
    """AC-3/AC-6. It reads the latest completed CI run, not the tree, so two
    passes can legitimately differ. Demanding byte-equality would make an honest
    refresh flake; claiming it converged would overclaim."""
    assert CI_SECURITY_SUMMARY not in TREE_DERIVED
    assert TREE_DERIVED == REFRESH_SET - {CI_SECURITY_SUMMARY}


def test_converged_ignores_paths_outside_the_tree_derived_set():
    md = sorted(COMPLIANCE_MDS)[0]
    previous = {md: "aaa", CI_SECURITY_SUMMARY: "one"}
    current = {md: "aaa", CI_SECURITY_SUMMARY: "two"}
    assert converged(previous, current) is True


def test_converged_is_false_when_a_tree_derived_path_moved():
    md = sorted(COMPLIANCE_MDS)[0]
    assert converged({md: "aaa"}, {md: "bbb"}) is False


def test_a_path_that_stopped_being_emitted_is_drift_not_convergence():
    """Absent is not unchanged: a pass that stops emitting a document must not
    read as a fixpoint."""
    md = sorted(COMPLIANCE_MDS)[0]
    assert converged({md: "aaa"}, {}) is False


# --- AC-4: a failed pass is not a pass that found nothing --------------------


def test_an_unknown_outcome_is_a_failure():
    """AC-4. The success vocabulary is CLOSED. A producer leg that starts saying
    something new is a failure until somebody adds the word on purpose — matching
    the literal 'error' is what made this class of bug invisible before."""
    md = sorted(COMPLIANCE_MDS)[0]
    assert failed_paths({md: "skipped (symlink)"}) == [md]
    assert failed_paths({md: "seed-error: boom"}) == [md]
    assert failed_paths({md: "error"}) == [md]


def test_known_success_outcomes_are_not_failures():
    md = sorted(COMPLIANCE_MDS)[0]
    for outcome in sorted(SUCCESS_OUTCOMES):
        assert failed_paths({md: outcome}) == []


def test_failed_paths_tolerates_nothing_at_all():
    assert failed_paths(None) == []
    assert failed_paths({}) == []


# --- AC-5: the content floor -------------------------------------------------


def test_an_emptied_document_violates_the_floor():
    assert content_floor_violation(b"x" * 100, b"") is not None
    assert content_floor_violation(b"x" * 100, b"   \n ") is not None
    assert content_floor_violation(b"x" * 100, None) is not None


def test_a_document_under_the_ratio_violates_the_floor():
    before = b"x" * 100
    after = b"x" * int(100 * CONTENT_FLOOR_RATIO)
    assert content_floor_violation(before, after[:-1]) is not None


def test_a_document_at_or_above_the_ratio_passes():
    before = b"x" * 100
    assert content_floor_violation(before, b"x" * 50) is None
    assert content_floor_violation(before, b"x" * 200) is None


def test_a_path_absent_from_head_has_nothing_to_fall_below():
    assert content_floor_violation(None, b"") is None
    assert content_floor_violation(b"", b"") is None


def test_allow_shrink_waives_the_ratio_floor_only():
    """AC-5. A legitimate large removal can halve a document, so the ratio floor
    is overridable. Emptying one is never legitimate and stays blocked — that is
    the shape a timed-out collector produces."""
    before = b"x" * 100
    assert content_floor_violation(before, b"x" * 10, allow_shrink=True) is None
    assert content_floor_violation(before, b"", allow_shrink=True) is not None


# --- wording -----------------------------------------------------------------


def test_the_branch_and_commit_name_the_base_and_read_as_maintenance():
    sha = "dcf85f874e8e528e9961f3d4d615a8a7c8dfee4b"
    assert branch_name(sha) == "chore/compliance-docs-dcf85f874e8e"
    message = docs_commit_message(sha, "iterate-2026-07-31-x")
    assert message.startswith("chore(compliance): ")
    assert "dcf85f874e8e" in message
    # `chore` sits inside B7's default non-functional exclusion, so the refresh
    # reads as expected maintenance rather than as unexplained drift.
    assert message.split(":")[0] == "chore(compliance)"


def test_the_branch_name_carries_nothing_but_the_base():
    """No clock in the name: two refreshes at the same base produce the same
    branch, which is honest — there is nothing new to say.

    Asserting `branch_name(sha) == branch_name(sha)` would be tautological for a
    pure function of one argument, and a date-stamped name would pass it (it is
    stable *within* a run). So this asserts the SHAPE instead: nothing after the
    prefix but the twelve sha characters (Stage-2 code review, low).
    """
    sha = "abcdef0123456789" + "0" * 24
    assert branch_name(sha) == f"chore/compliance-docs-{sha[:12]}"
    assert re.fullmatch(r"chore/compliance-docs-[0-9a-f]{12}", branch_name(sha))


def test_the_pr_body_names_the_base_the_files_and_the_ci_dependency():
    body = pr_body("b" * 40, [sorted(COMPLIANCE_MDS)[0]], "frozen: no completed scan")
    assert "bbbbbbbbbbbb" in body
    assert sorted(COMPLIANCE_MDS)[0] in body
    assert "frozen: no completed scan" in body
    assert "not continuously" in body


def test_the_pr_body_says_so_when_nothing_differed():
    body = pr_body("c" * 40, [], "fresh")
    assert "none differed" in body


def test_the_docs_commit_carries_the_trailer_the_staleness_audit_recognises():
    """Stage-2 code review, high — and the least obvious defect in this change.

    `audit_staleness.find_snapshot_commit` recognises a compliance snapshot by
    EITHER a `Run-ID:` trailer or a `chore(release)` subject, and its docstring
    says verbatim that a manual `chore(compliance)` regen is *deliberately NOT
    recognised* — that is the hand-edit case Group E exists to catch. So this
    subject, alone, is the one string the audit refuses. Without the trailer the
    docs-only PR merges, the next audit skips it, falls back to the previous
    release, and reports the FRESHEST possible evidence as stale.
    """
    message = docs_commit_message("b" * 40, "iterate-2026-07-31-derived-docs")
    assert "Run-ID: iterate-2026-07-31-derived-docs" in message
    # The audit greps with --fixed-strings, so a literal substring is the test.
    assert "Run-ID:" in message
