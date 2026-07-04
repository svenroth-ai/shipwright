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

# TEST-specific check names only. Deliberately EXCLUDES bare "build"/"ci": a
# green build or generic CI status is not evidence that TESTS ran, so counting
# it would inflate the Scorecard-style "tests-run-on-merged-PRs" ratio (external
# review, GPT #5). "test" already subsumes pytest/vitest/unittest/testsuite/go-test.
_TEST_CHECK_RE = re.compile(
    r"(test|spec|jest|vitest|mocha|cypress|playwright|e2e|integration|unit|tox)",
    re.IGNORECASE)
_MERGED_PR_QUERY = (
    "query($owner:String!,$repo:String!){repository(owner:$owner,name:$repo){"
    "pullRequests(states:MERGED,first:20,orderBy:{field:UPDATED_AT,direction:DESC})"
    "{nodes{mergeCommit{statusCheckRollup{contexts(first:30){nodes{__typename "
    "... on CheckRun{name conclusion} ... on StatusContext{context state}}}}}}}}}"
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
    if not isinstance(node, dict):
        return False
    name = node.get("name") or node.get("context") or ""
    conclusion = (node.get("conclusion") or node.get("state") or "").upper()
    return bool(_TEST_CHECK_RE.search(str(name))) and conclusion == "SUCCESS"


def _tier2_scorecard(gh: GhRunner, owner: str, repo: str) -> tuple[int, int] | None:
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
        rollup = (((pr or {}).get("mergeCommit") or {}).get("statusCheckRollup")
                  if isinstance(pr, dict) else None)
        if not isinstance(rollup, dict):
            continue
        contexts = ((rollup.get("contexts") or {}).get("nodes")) or []
        total += 1
        if any(_is_successful_test_check(n) for n in contexts):
            passed += 1
    return (passed, total) if total else None


def compute_test_health_signal(
    policy: NetworkPolicy,
    gh: GhRunner,
    *,
    tier1: Callable[[GhRunner, str, str], JUnitResult | None] | None = None,
    tier2: Callable[[GhRunner, str, str], tuple[int, int] | None] | None = None,
) -> TestHealthSignal:
    """Best-available test-health; ``n/a`` (static-inventory floor) otherwise."""
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
        if checks is not None:
            passed, total = checks
            policy.record(f"PR check-runs ({owner}/{repo})")
            return TestHealthSignal(
                measurable=True, passed=passed, total=total,
                tier="scorecard-checks",
                detail=(f"{passed}/{total} recent merged PRs ran a passing test "
                        "check in CI (Scorecard CI-Tests)"))
    return TestHealthSignal(
        measurable=False, passed=None, total=None, tier="static-inventory",
        detail="static test inventory only — no executed pass ratio available")
