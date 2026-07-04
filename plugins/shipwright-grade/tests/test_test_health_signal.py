"""Tests for test_health_signal — layered tiers, best-available wins (dim 2)."""

from __future__ import annotations

import json

from gh_bridge import GhResult
from junit_xml import JUnitResult
from network_policy import NetworkPolicy
from test_health_signal import (
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
