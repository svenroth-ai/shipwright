"""Tests for security_signal — code-scanning SARIF → open high/critical (dim 5).

Injects the ``gh`` runner (canned analyses list + SARIF payloads) but uses the
REAL shared suppression-aware SARIF parser + ci_security grade guard, so the
whole path — including nosemgrep suppression handling and the never-a-false-
CRITICAL rule — is integration-tested hermetically.
"""

from __future__ import annotations

import json

from network_policy import NetworkPolicy
from security_signal import compute_security_signal

_CLEAN = {"runs": [{"tool": {"driver": {"name": "CodeQL", "rules": []}}, "results": []}]}
_WITH_FINDINGS = {"runs": [{
    "tool": {"driver": {"name": "CodeQL", "rules": [
        {"id": "R1", "properties": {"security-severity": "9.1"}},   # critical
        {"id": "R2", "properties": {"security-severity": "7.5"}},   # high
        {"id": "R3", "properties": {"security-severity": "3.0"}},   # medium
    ]}},
    "results": [
        {"ruleId": "R1"},
        {"ruleId": "R2"},
        {"ruleId": "R3"},
        {"ruleId": "R1", "suppressions": [{"kind": "inSource"}]},   # dropped
    ],
}]}


def _enabled_policy():
    return NetworkPolicy(enabled=True, requested=True, owner="octo", repo="repo",
                         visibility="public", note="")


def _gh(*, analyses="[{\"id\": 42}]", sarif=None, analyses_error="",
        sarif_error="", default_branch="", calls=None):
    from gh_bridge import GhResult

    def fake(args, *, timeout=30):
        joined = " ".join(args)
        if calls is not None:
            calls.append(joined)
        if "defaultBranchRef" in joined:
            return GhResult(ok=True, stdout=(f'{{"defaultBranchRef": {{"name": '
                                             f'"{default_branch}"}}}}'
                                             if default_branch else "{}"))
        if "analyses/42" in joined:  # SARIF download
            if sarif_error:
                return GhResult(ok=False, error=sarif_error)
            return GhResult(ok=True, stdout=sarif or "")
        if "analyses" in joined:  # list
            if analyses_error:
                return GhResult(ok=False, error=analyses_error)
            return GhResult(ok=True, stdout=analyses)
        return GhResult(ok=False, error="http_error")
    return fake


def test_local_only_policy_is_na():
    policy = NetworkPolicy(enabled=False, requested=False, owner=None, repo=None,
                           visibility="local-only", note="")
    sig = compute_security_signal(policy, _gh())
    assert sig.measurable is False
    assert "local-only" in sig.detail


def test_clean_scan_is_zero_high_critical():
    sig = compute_security_signal(_enabled_policy(), _gh(sarif=json.dumps(_CLEAN)))
    assert sig.measurable is True
    assert sig.open_high_critical == 0


def test_findings_counted_and_suppressed_dropped():
    policy = _enabled_policy()
    sig = compute_security_signal(policy, _gh(sarif=json.dumps(_WITH_FINDINGS)))
    assert sig.measurable is True
    # critical R1 (one live, one suppressed→dropped) + high R2 = 2; medium excluded.
    assert sig.open_high_critical == 2
    assert any("code-scanning SARIF" in e for e in policy.enrichments)


def test_no_analyses_is_na():
    sig = compute_security_signal(_enabled_policy(), _gh(analyses="[]"))
    assert sig.measurable is False
    assert "no code-scanning analyses" in sig.detail


def test_403_on_analyses_is_na():
    sig = compute_security_signal(_enabled_policy(), _gh(analyses_error="rate_limited"))
    assert sig.measurable is False
    assert "code-scanning unavailable" in sig.detail


def test_invalid_sarif_is_na_not_clean():
    # Malformed payload must NOT read as a clean (0-finding) scan.
    sig = compute_security_signal(_enabled_policy(), _gh(sarif="not valid json"))
    assert sig.measurable is False
    assert "invalid SARIF" in sig.detail


def test_sarif_without_runs_is_na():
    sig = compute_security_signal(_enabled_policy(), _gh(sarif='{"version": "2.1.0"}'))
    assert sig.measurable is False
    assert "invalid SARIF" in sig.detail


def test_sarif_with_non_list_runs_is_na_not_clean():
    # A malformed payload where ``runs`` is a valid key but NOT an array must be
    # n/a, never read as a clean 0-finding scan (reviewer finding #1).
    for bad in ('{"runs": null}', '{"runs": "x"}', '{"runs": 5}'):
        sig = compute_security_signal(_enabled_policy(), _gh(sarif=bad))
        assert sig.measurable is False, bad
        assert "invalid SARIF" in sig.detail


def test_sarif_download_failure_is_na():
    sig = compute_security_signal(_enabled_policy(), _gh(sarif_error="http_error"))
    assert sig.measurable is False
    assert "could not be downloaded" in sig.detail


def test_absent_gh_is_na():
    # gh binary missing while the analyses call is attempted → graceful n/a.
    sig = compute_security_signal(_enabled_policy(), _gh(analyses_error="not_found"))
    assert sig.measurable is False
    assert "code-scanning unavailable" in sig.detail


def test_gh_auth_failure_is_na():
    sig = compute_security_signal(_enabled_policy(), _gh(analyses_error="auth"))
    assert sig.measurable is False
    assert "authentication required" in sig.detail


def test_analyses_filtered_by_default_branch():
    calls: list[str] = []
    compute_security_signal(
        _enabled_policy(),
        _gh(sarif=json.dumps(_CLEAN), default_branch="main", calls=calls))
    analyses_calls = [c for c in calls if "code-scanning/analyses?" in c]
    assert analyses_calls and "ref=refs/heads/main" in analyses_calls[0]
