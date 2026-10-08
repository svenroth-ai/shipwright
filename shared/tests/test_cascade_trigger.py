"""F11 gate ``check_cascade_trigger``: at small, a risk flag or a diff > 100 lines needs a code-review answer.

Counting and the review-record vocabulary. The cases where an input is unknown
live in ``test_cascade_trigger_unknown.py``; the real-git fixtures in
``_cascade_trigger_fixtures.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from _cascade_trigger_fixtures import (  # noqa: E402, F401 - hermetic_git is an autouse fixture
    REVIEWED,
    check,
    git,
    hermetic_git,
    lines,
    make_repo,
    not_run,
    write_run,
)
from tools.verifiers import _finalization_claims as claims  # noqa: E402
from tools.verifiers import cascade_trigger as ct  # noqa: E402


@pytest.mark.covers("FR-01.11")
def test_quiet_small_run_is_not_triggered(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(10)})
    write_run(root)
    result = check(root, sha)
    assert result.ok and "not triggered" in result.detail and "10 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_101_lines_with_free_text_not_run_fails_naming_the_count(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(101)})
    write_run(root)
    result = check(root, sha)
    assert not result.ok
    assert "101 changed lines > 100" in result.detail
    assert "reason_code" in result.detail


@pytest.mark.covers("FR-01.11")
def test_exactly_100_lines_does_not_trigger(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(100)})
    write_run(root)
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11")
def test_removed_lines_count_too(tmp_path):
    """Added + removed: deleting the 200-line base file is a 200-line change."""
    root, sha = make_repo(tmp_path, {}, removed=["base.txt"])
    write_run(root)
    result = check(root, sha)
    assert not result.ok and "200 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("code", sorted(ct.ACCEPTED_CODES))
def test_an_accepted_not_run_code_passes(tmp_path, code):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(150)})
    write_run(root, code=not_run(code))
    result = check(root, sha)
    assert result.ok and code in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("code,why", [
    ("diff-below-threshold", "says the trigger did not fire"),
    ("complexity-below-threshold", "says the trigger did not fire"),
    ("trivial-auto", "says the trigger did not fire"),
    ("missing-keys", "external review leg"),
    ("config-disabled", "external review leg"),
])
def test_a_code_outside_the_allowlist_is_refused(tmp_path, code, why):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(150)})
    write_run(root, code=not_run(code))
    result = check(root, sha)
    assert not result.ok and why in result.detail and "accepted:" in result.detail


@pytest.mark.covers("FR-01.11")
def test_an_unknown_reason_code_string_is_refused(tmp_path):
    """The gate refuses it, and the record reader already does: one fault, one message."""
    assert "not in the closed review_not_run vocabulary" in ct._not_run_problem("not_run", "felt-fine")
    root, sha = make_repo(tmp_path, {"src/a.py": lines(150)})
    write_run(root, code=not_run("felt-fine"))
    result = check(root, sha)
    assert result.detail.startswith("skipped (the review record is unreadable")


@pytest.mark.covers("FR-01.11")
def test_completed_code_with_evidence_passes_and_without_fails(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(150)})
    write_run(root, code=REVIEWED)
    assert check(root, sha).ok
    write_run(root, code={"status": "completed"})
    result = check(root, sha)
    assert not result.ok and "no evidence" in result.detail


@pytest.mark.covers("FR-01.11")
def test_not_applicable_is_refused_even_with_a_closed_code(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(150)})
    write_run(root, code={"status": "not_applicable", "disposition": "the rule that applies",
                          "reason_code": "unavailable"})
    result = check(root, sha)
    assert not result.ok and "applicable" in result.detail


@pytest.mark.covers("FR-01.11")
def test_recorded_risk_flag_triggers_on_a_tiny_diff(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(3)})
    write_run(root, plan_flags=["touches_auth"])
    result = check(root, sha)
    assert not result.ok and "touches_auth" in result.detail


@pytest.mark.covers("FR-01.11")
def test_campaign_recheck_flag_with_delegation_code_passes(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(3)})
    write_run(root, recheck_flags=["touches_io_boundary"], code=not_run("delegated-to-orchestrator"))
    result = check(root, sha)
    assert result.ok and "touches_io_boundary" in result.detail


@pytest.mark.covers("FR-01.11")
def test_cross_component_is_recomputed_from_the_diff(tmp_path):
    """No flag recorded anywhere: the diff itself still raises cross_component."""
    root, sha = make_repo(tmp_path, {"plugins/x/hooks/hooks.json": "{}\n"})
    write_run(root)
    result = check(root, sha)
    assert not result.ok and "cross_component" in result.detail


@pytest.mark.covers("FR-01.11")
def test_finalization_records_are_not_counted(tmp_path):
    root, sha = make_repo(tmp_path, {
        ".shipwright/agent_docs/iterates/x.test-results.json": lines(300),
        "CHANGELOG-unreleased.d/added/x.md": lines(50),
        "shipwright_test_results.json": lines(80),
        "src/a.py": lines(5),
    })
    write_run(root)
    result = check(root, sha)
    assert result.ok and "5 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("complexity", ["trivial", "medium", "large"])
def test_other_complexities_are_skipped(tmp_path, complexity):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(150)})
    write_run(root, complexity=complexity)
    result = check(root, sha)
    assert result.ok and result.detail.startswith("skipped")


@pytest.mark.covers("FR-01.11")
def test_complexity_label_is_compared_trimmed_and_case_folded(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(150)})
    write_run(root, complexity=" Small ")
    result = check(root, sha)
    assert not result.ok and "150 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_pure_rename_counts_both_sides(tmp_path):
    """Rename detection is off, so moving the 200-line file is 200 removed + 200 added."""
    root, sha = make_repo(tmp_path, {}, moved={"base.txt": "moved.txt"})
    write_run(root)
    result = check(root, sha)
    assert not result.ok and "400 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_multi_commit_branch_is_measured_whole_not_by_its_tip(tmp_path):
    root, _ = make_repo(tmp_path, {"src/a.py": lines(150)})
    (root / "src" / "b.py").write_text("x\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "tiny tip")
    write_run(root)
    result = check(root, git(root, "rev-parse", "HEAD"))
    assert not result.ok and "151 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_remote_less_repo_trusts_its_lone_local_trunk(tmp_path):
    """Greenfield: no remote can go stale, so local ``main`` alone is the base."""
    root, sha = make_repo(tmp_path, {"src/a.py": lines(150)}, origin=False)
    write_run(root)
    result = check(root, sha)
    assert not result.ok and "150 changed lines > 100" in result.detail


@pytest.mark.covers("FR-01.11")
def test_gate_is_registered_in_the_claim_registry():
    assert ct.check_cascade_trigger in claims.CLAIM_CHECKS
