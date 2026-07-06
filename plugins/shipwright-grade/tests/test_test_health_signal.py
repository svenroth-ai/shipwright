"""Tests for test_health_signal — layered tiers, best-available wins (dim 2)."""

from __future__ import annotations

import json

from gh_bridge import GhResult
from junit_xml import JUnitResult
from network_policy import NetworkPolicy
from test_health_signal import (
    _is_successful_test_check,
    _tier1_ci_junit,
    _tier2_scorecard,
    compute_test_health_signal,
)


def _enabled():
    return NetworkPolicy(enabled=True, requested=True, owner="octo", repo="repo",
                         visibility="public", note="")


def _disabled():
    return NetworkPolicy(enabled=False, requested=False, owner=None, repo=None,
                         visibility="local-only", note="")


# --- best-available orchestration (injected tiers) ------------------------- #

def test_tier1_wins_when_available():
    sig = compute_test_health_signal(
        _enabled(), lambda *a, **k: None,
        tier1=lambda *_: JUnitResult(passed=95, total=100),
        tier2=lambda *_: (10, 10))
    assert sig.tier == "ci-junit"
    assert (sig.passed, sig.total) == (95, 100)
    assert sig.measurable is True


def test_tier2_used_when_tier1_absent():
    sig = compute_test_health_signal(
        _enabled(), lambda *a, **k: None,
        tier1=lambda *_: None, tier2=lambda *_: (7, 9))
    assert sig.tier == "scorecard-checks"
    assert (sig.passed, sig.total) == (7, 9)


def test_static_floor_when_both_absent():
    sig = compute_test_health_signal(
        _enabled(), lambda *a, **k: None, tier1=lambda *_: None, tier2=lambda *_: None)
    assert sig.tier == "static-inventory"
    assert sig.measurable is False
    assert sig.passed is None


def test_disabled_policy_is_static_floor():
    sig = compute_test_health_signal(
        _disabled(), lambda *a, **k: None,
        tier1=lambda *_: JUnitResult(1, 1), tier2=lambda *_: (1, 1))
    assert sig.tier == "static-inventory"  # network never consulted


def test_tier1_records_enrichment():
    policy = _enabled()
    compute_test_health_signal(policy, lambda *a, **k: None,
                               tier1=lambda *_: JUnitResult(1, 1), tier2=lambda *_: None)
    assert any("CI JUnit" in e for e in policy.enrichments)


# --- real tier fetchers with injected gh ----------------------------------- #

def _junit_gh():
    def fake(args, *, timeout=30):
        joined = " ".join(args)
        if "defaultBranchRef" in joined:
            return GhResult(ok=True, stdout='{"defaultBranchRef": {"name": "main"}}')
        if joined.startswith("run list"):
            return GhResult(ok=True, stdout='[{"databaseId": 99}]')
        if joined.startswith("run download"):
            dest = args[args.index("-D") + 1]
            from pathlib import Path
            (Path(dest) / "results.xml").write_text(
                '<testsuite tests="10" failures="2"/>', encoding="utf-8")
            return GhResult(ok=True)
        return GhResult(ok=False, error="http_error")
    return fake


def test_real_tier1_downloads_and_parses_junit():
    r = _tier1_ci_junit(_junit_gh(), "octo", "repo")
    assert r == JUnitResult(passed=8, total=10)


def test_real_tier1_none_without_default_branch():
    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout="{}")  # no defaultBranchRef
    assert _tier1_ci_junit(fake, "o", "r") is None


_GRAPHQL = {"data": {"repository": {"pullRequests": {"nodes": [
    {"mergeCommit": {"statusCheckRollup": {"contexts": {"nodes": [
        {"__typename": "CheckRun", "name": "unit-tests", "conclusion": "SUCCESS"}]}}}},
    {"mergeCommit": {"statusCheckRollup": {"contexts": {"nodes": [
        {"__typename": "CheckRun", "name": "pytest", "conclusion": "FAILURE"}]}}}},
    {"mergeCommit": {"statusCheckRollup": {"contexts": {"nodes": [
        {"__typename": "StatusContext", "context": "lint", "state": "SUCCESS"}]}}}},
]}}}}


def test_real_tier2_counts_passing_test_checks():
    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout=json.dumps(_GRAPHQL))
    # PR1 passing test check; PR2 failing test check; PR3 non-test check.
    assert _tier2_scorecard(fake, "octo", "repo") == (1, 3)


def test_real_tier2_none_on_error():
    def fake(args, *, timeout=30):
        return GhResult(ok=False, error="rate_limited")
    assert _tier2_scorecard(fake, "o", "r") is None


def test_real_tier2_none_on_empty_prs():
    empty = {"data": {"repository": {"pullRequests": {"nodes": []}}}}

    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout=json.dumps(empty))
    assert _tier2_scorecard(fake, "o", "r") is None


def _pr(name, conclusion, kind="CheckRun"):
    key = "name" if kind == "CheckRun" else "context"
    concl_key = "conclusion" if kind == "CheckRun" else "state"
    return {"mergeCommit": {"statusCheckRollup": {"contexts": {"nodes": [
        {"__typename": kind, key: name, concl_key: conclusion}]}}}}


def test_real_tier2_build_and_ci_checks_are_not_tests():
    # External review GPT #5: a green "build"/"ci"/"lint" check is NOT evidence
    # that tests ran — it must not count toward the test-health ratio.
    graphql = {"data": {"repository": {"pullRequests": {"nodes": [
        _pr("build", "SUCCESS"),
        _pr("ci", "SUCCESS"),
        _pr("lint", "SUCCESS", kind="StatusContext"),
        _pr("unit-tests", "SUCCESS"),  # the only real test check
    ]}}}}

    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout=json.dumps(graphql))
    # 4 PRs examined, only the unit-tests PR counts.
    assert _tier2_scorecard(fake, "octo", "repo") == (1, 4)


def test_real_tier2_common_test_runners_count():
    graphql = {"data": {"repository": {"pullRequests": {"nodes": [
        _pr("jest", "SUCCESS"), _pr("cypress e2e", "SUCCESS"),
        _pr("RSpec", "SUCCESS", kind="StatusContext"), _pr("tox", "SUCCESS"),
    ]}}}}

    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout=json.dumps(graphql))
    assert _tier2_scorecard(fake, "octo", "repo") == (4, 4)


# --- CI-system app-slug recognition (root cause 2: matrix-named checks) ----- #

def _app_pr(name, conclusion, slug):
    """A merged PR whose merge-commit rollup carries one CheckRun with an app slug."""
    return {"mergeCommit": {"statusCheckRollup": {"contexts": {"nodes": [
        {"__typename": "CheckRun", "name": name, "conclusion": conclusion,
         "checkSuite": {"app": {"slug": slug}}}]}}}}


def test_matrix_named_github_actions_check_counts():
    # flask's real shape: a test leg named "3.12" (no test-word) posted by the
    # github-actions app, green. OpenSSF Scorecard keys on the CI-system app slug.
    assert _is_successful_test_check(
        {"name": "3.12", "conclusion": "SUCCESS",
         "checkSuite": {"app": {"slug": "github-actions"}}}) is True


def test_non_ci_app_check_does_not_count():
    # socket-security (a security bot, its own app slug) is NOT a CI test system.
    assert _is_successful_test_check(
        {"name": "Socket Security", "conclusion": "SUCCESS",
         "checkSuite": {"app": {"slug": "socket-security"}}}) is False


def test_failing_ci_app_check_does_not_count():
    assert _is_successful_test_check(
        {"name": "3.12", "conclusion": "FAILURE",
         "checkSuite": {"app": {"slug": "github-actions"}}}) is False


def test_legacy_travis_status_context_counts_by_ci_system_name():
    # A StatusContext (legacy commit-status API, no checkSuite app) is recognized by
    # the CI-system name in its `context`; its success field is `state`, not
    # `conclusion`. Both GitHub enums use "SUCCESS", normalized via .upper().
    assert _is_successful_test_check(
        {"context": "continuous-integration/travis-ci/pr", "state": "SUCCESS"}) is True
    assert _is_successful_test_check(
        {"context": "continuous-integration/travis-ci/pr", "state": "FAILURE"}) is False


def test_tier2_counts_matrix_named_ci_checks():
    graphql = {"data": {"repository": {"pullRequests": {"nodes": [
        _app_pr("3.12", "SUCCESS", "github-actions"),
        _app_pr("Windows", "SUCCESS", "github-actions"),
        _app_pr("Socket Security", "SUCCESS", "socket-security"),  # not CI
    ]}}}}

    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout=json.dumps(graphql))
    # 3 examinable merged PRs; the two github-actions legs count, socket-security does not.
    assert _tier2_scorecard(fake, "octo", "repo") == (2, 3)


# --- examinable-merged-PR denominator + low-vs-n/a (decision 2) ------------- #

def _merged_no_checks():
    """A merged PR with a merge commit but NO CI rollup (deprecated / ungated)."""
    return {"mergeCommit": {"oid": "abc", "statusCheckRollup": None}}


def test_tier2_no_rollup_prs_count_toward_denominator():
    # request/superpowers: merged PRs exist but nothing gated them → 0/N, not None.
    graphql = {"data": {"repository": {"pullRequests": {"nodes": [
        _merged_no_checks(), _merged_no_checks(), _merged_no_checks(),
    ]}}}}

    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout=json.dumps(graphql))
    assert _tier2_scorecard(fake, "o", "r") == (0, 3)


def _pr_head_only(name, conclusion, slug="github-actions"):
    """A merged PR whose MERGE commit has no rollup but whose PR HEAD commit does
    (the `on: pull_request`-only CI shape)."""
    head_check = {"__typename": "CheckRun", "name": name, "conclusion": conclusion,
                  "checkSuite": {"app": {"slug": slug}}}
    head_rollup = {"contexts": {"nodes": [head_check]}}
    return {
        "mergeCommit": {"oid": "m", "statusCheckRollup": None},
        "commits": {"nodes": [{"commit": {"statusCheckRollup": head_rollup}}]},
    }


def test_tier2_counts_pr_head_checks_when_merge_commit_has_none():
    # A well-run repo that runs CI only on the PR head (no push CI on the merge
    # commit) must NOT read 0 → F. The PR-head rollup is the fallback.
    graphql = {"data": {"repository": {"pullRequests": {"nodes": [
        _pr_head_only("3.12", "SUCCESS"),
        _pr_head_only("3.12", "FAILURE"),  # head ran but failed → not passing
    ]}}}}

    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout=json.dumps(graphql))
    assert _tier2_scorecard(fake, "octo", "repo") == (1, 2)


def test_tier2_unmerged_prs_are_not_examinable():
    graphql = {"data": {"repository": {"pullRequests": {"nodes": [
        {"mergeCommit": None},  # no merge commit → not examinable
        _app_pr("3.12", "SUCCESS", "github-actions"),
    ]}}}}

    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout=json.dumps(graphql))
    assert _tier2_scorecard(fake, "o", "r") == (1, 1)


def test_zero_passing_scores_low_when_repo_has_test_infra():
    # A repo WITH test infra whose merges show no passing CI test check → LOW (decayed),
    # not n/a — the honest control-gap signal that ranks deprecated repos below well-run.
    sig = compute_test_health_signal(
        _enabled(), lambda *a, **k: None, has_test_infra=True,
        tier1=lambda *_: None, tier2=lambda *_: (0, 20))
    assert sig.measurable is True
    assert (sig.passed, sig.total) == (0, 20)
    assert sig.tier == "scorecard-checks"


def test_zero_passing_is_na_without_test_infra():
    # A test-less repo (e.g. a README list) must degrade to honest n/a, never F.
    sig = compute_test_health_signal(
        _enabled(), lambda *a, **k: None, has_test_infra=False,
        tier1=lambda *_: None, tier2=lambda *_: (0, 20))
    assert sig.measurable is False
    assert sig.tier == "static-inventory"


def test_some_passing_scores_even_without_test_infra():
    # If any CI test check passed, score it regardless of the local inventory read.
    sig = compute_test_health_signal(
        _enabled(), lambda *a, **k: None, has_test_infra=False,
        tier1=lambda *_: None, tier2=lambda *_: (5, 20))
    assert sig.measurable is True
    assert (sig.passed, sig.total) == (5, 20)
