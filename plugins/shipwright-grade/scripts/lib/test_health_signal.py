"""test_health_signal — layered test-health, best-available wins (dim 2).

Three tiers, in preference order; the chosen tier is stamped in provenance
(plan §5). Only tiers that yield a real pass/total light the score:

1. **CI JUnit** (network): the latest completed CI run's JUnit → true pass/total.
2. **Scorecard CI-Tests** (network): ONE GraphQL ``statusCheckRollup`` over recent
   merged PRs (never per-PR/commit — Gemini #4/GPT #7) → ``passed`` = PRs whose
   merge commit carried a **successful test check**, ``total`` = PRs examined.
   This is exactly OpenSSF Scorecard's CI-Tests signal, so mapping it into the
   pass-ratio dimension is faithful.
3. **Static inventory** (local floor): a count of test files cannot fabricate a
   pass ratio, so the score stays ``n/a`` — surfaced as detail, not a number.

On ``403``/rate-limit/no-network each network tier degrades to the next, then to
the ``n/a`` floor (deterministic, tested).
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from gh_bridge import GhRunner, default_branch, gh_json
from junit_xml import JUnitResult, parse_junit_files
from network_policy import NetworkPolicy

# TEST-specific check names. A green check literally named "test"/"e2e"/… is
# unambiguous evidence a test ran. "test" already subsumes pytest/vitest/unittest.
_TEST_CHECK_RE = re.compile(
    r"(test|spec|jest|vitest|mocha|cypress|playwright|e2e|integration|unit|tox)",
    re.IGNORECASE)
# The CI-system identity is the Scorecard-faithful signal (G6 root cause 2): real
# test legs are named by matrix (`3.12`, `Windows`, `PyPy`) — a test-word never
# appears — but they are posted by a recognized CI system. OpenSSF Scorecard's
# CI-Tests check keys on exactly this (its `isTest` matches the CI app/context),
# so a successful check from one of these systems counts as a passing test run.
# A non-CI app (dependabot, socket-security, codecov) is NOT in the set, so a
# security/coverage bot's green check never inflates the ratio.
_CI_SYSTEM_APPS = frozenset({
    "github-actions", "circleci", "travis-ci", "appveyor", "jenkins",
    "azure-pipelines", "semaphoreci", "buildkite",
})
# Legacy commit-status contexts (Travis/AppVeyor via the Status API) carry no
# check-suite app — recognize the CI system in the context name instead.
_CI_SYSTEM_RE = re.compile(
    r"(github[- ]?actions|circle[- ]?ci|travis|appveyor|jenkins|"
    r"azure-pipelines|semaphore|buildkite|continuous-integration)",
    re.IGNORECASE)
# The check rollup selection, reused for the merge commit AND the PR head commit.
_ROLLUP = (
    "statusCheckRollup{contexts(first:30){nodes{__typename "
    "... on CheckRun{name conclusion checkSuite{app{slug}}} "
    "... on StatusContext{context state}}}}")
# Read BOTH the merge commit's rollup and the PR head commit's rollup: a repo that
# runs CI `on: pull_request` only (a common well-run setup) attaches checks to the
# PR head SHA, not the squash/rebase merge commit — reading only the merge commit
# would score such a repo 0 and collapse it to F (Scorecard's CI-Tests inspects the
# PR's own commit). A PR passes if EITHER commit carried a passing CI test check.
_MERGED_PR_QUERY = (
    "query($owner:String!,$repo:String!){repository(owner:$owner,name:$repo){"
    "pullRequests(states:MERGED,first:20,orderBy:{field:UPDATED_AT,direction:DESC})"
    "{nodes{mergeCommit{" + _ROLLUP + "}"
    "commits(last:1){nodes{commit{" + _ROLLUP + "}}}}}}}"
)


@dataclass(frozen=True)
class TestHealthSignal:
    __test__ = False  # not a pytest test class (name starts with "Test")
    measurable: bool
    passed: int | None
    total: int | None
    tier: str            # ci-junit | scorecard-checks | static-inventory
    detail: str


def _tier1_ci_junit(gh: GhRunner, owner: str, repo: str) -> JUnitResult | None:
    branch = default_branch(gh, owner, repo)
    if not branch:
        return None
    slug = f"{owner}/{repo}"
    result, data = gh_json(gh, ["run", "list", "-R", slug, "-b", branch, "-s",
                                "completed", "-L", "1", "--json", "databaseId"])
    if not result.ok or not isinstance(data, list) or not data:
        return None
    run_id = data[0].get("databaseId") if isinstance(data[0], dict) else None
    if not isinstance(run_id, int):
        return None
    with tempfile.TemporaryDirectory(prefix="grade-junit-") as td:
        dl = gh(["run", "download", str(run_id), "-R", slug, "-D", td], timeout=90)
        if not dl.ok:
            return None
        return parse_junit_files(list(Path(td).rglob("*.xml")))


def _is_successful_test_check(node: dict) -> bool:
    """A check counts as a passing test run iff it SUCCEEDED and is a test/CI check.

    "Is a test check" is true when the check name matches an explicit test-runner
    word OR names a CI system OR was posted by a recognized CI-system app (the
    Scorecard-faithful signal — matrix-named legs like `3.12` carry no test-word
    but are github-actions checks). A non-CI app (dependabot/socket-security) is
    excluded, so a security/coverage bot never inflates the ratio.
    """
    if not isinstance(node, dict):
        return False
    if (node.get("conclusion") or node.get("state") or "").upper() != "SUCCESS":
        return False
    name = str(node.get("name") or node.get("context") or "")
    if _TEST_CHECK_RE.search(name) or _CI_SYSTEM_RE.search(name):
        return True
    suite = node.get("checkSuite")
    slug = (suite.get("app") or {}).get("slug") if isinstance(suite, dict) else None
    return slug in _CI_SYSTEM_APPS


def _rollup_has_passing_test(rollup: object) -> bool:
    """True when a commit's ``statusCheckRollup`` carried a passing CI test check."""
    if not isinstance(rollup, dict):
        return False
    contexts = ((rollup.get("contexts") or {}).get("nodes")) or []
    return any(_is_successful_test_check(n) for n in contexts)


def _pr_head_rollup(pr: dict) -> object:
    """The PR head commit's rollup (the `on: pull_request` CI target), or None."""
    nodes = ((pr.get("commits") or {}).get("nodes")) or []
    if not nodes or not isinstance(nodes[-1], dict):
        return None
    commit = nodes[-1].get("commit")
    return commit.get("statusCheckRollup") if isinstance(commit, dict) else None


def _tier2_scorecard(gh: GhRunner, owner: str, repo: str) -> tuple[int, int] | None:
    """(passed, total) over recent merged PRs, or None when none are examinable.

    ``total`` counts every merged PR that has a merge commit (an examinable change
    that landed); ``passed`` counts those whose merge commit OR PR head commit
    carried a passing CI test check. A merged PR that no passing CI check gated
    therefore scores 0 for that PR — so a repo that stopped running CI on its merges
    reads LOW (a real control gap), not a silent n/a (G6 decision 2). The low-vs-n/a
    call for a test-LESS repo is made by :func:`compute_test_health_signal`.
    """
    result, data = gh_json(gh, ["api", "graphql", "-f", f"query={_MERGED_PR_QUERY}",
                                "-f", f"owner={owner}", "-f", f"repo={repo}"])
    if not result.ok or not isinstance(data, dict):
        return None
    try:
        prs = data["data"]["repository"]["pullRequests"]["nodes"]
    except (KeyError, TypeError):
        return None
    if not isinstance(prs, list):
        return None
    passed = total = 0
    for pr in prs:
        merge_commit = (pr or {}).get("mergeCommit") if isinstance(pr, dict) else None
        if not isinstance(merge_commit, dict):
            continue  # unmerged / merge commit gone — not an examinable landed change
        total += 1
        if (_rollup_has_passing_test(merge_commit.get("statusCheckRollup"))
                or _rollup_has_passing_test(_pr_head_rollup(pr))):
            passed += 1
    return (passed, total) if total else None


def compute_test_health_signal(
    policy: NetworkPolicy,
    gh: GhRunner,
    *,
    has_test_infra: bool = True,
    tier1: Callable[[GhRunner, str, str], JUnitResult | None] | None = None,
    tier2: Callable[[GhRunner, str, str], tuple[int, int] | None] | None = None,
) -> TestHealthSignal:
    """Best-available test-health; ``n/a`` (static-inventory floor) otherwise.

    ``has_test_infra`` gates the low-vs-n/a call for the Scorecard tier: a repo that
    has a test suite AND a CI setup but whose recent merged PRs show no passing CI
    test check scores LOW (decayed / ungated CI — a real control gap). A repo with no
    test suite, or that does not use CI at all, stays honest ``n/a`` (nothing to run
    in CI, so 0 is not a failure — not a living repo "put on blast"). A non-zero pass
    count always scores, regardless of the inventory read.
    """
    tier1 = tier1 or _tier1_ci_junit
    tier2 = tier2 or _tier2_scorecard
    if policy.enabled and policy.owner and policy.repo:
        owner, repo = policy.owner, policy.repo
        junit = tier1(gh, owner, repo)
        if junit is not None:
            policy.record(f"CI JUnit ({owner}/{repo})")
            return TestHealthSignal(
                measurable=True, passed=junit.passed, total=junit.total,
                tier="ci-junit",
                detail=f"latest CI suite {junit.passed}/{junit.total} passed")
        checks = tier2(gh, owner, repo)
        if checks is not None and (checks[0] > 0 or has_test_infra):
            passed, total = checks
            policy.record(f"PR check-runs ({owner}/{repo})")
            decayed = "" if passed else " — no CI test gate on recent merges"
            return TestHealthSignal(
                measurable=True, passed=passed, total=total,
                tier="scorecard-checks",
                detail=(f"{passed}/{total} recent merged PRs ran a passing test "
                        f"check in CI (Scorecard CI-Tests){decayed}"))
    return TestHealthSignal(
        measurable=False, passed=None, total=None, tier="static-inventory",
        detail="static test inventory only — no executed pass ratio available")
