"""Tests for provenance_signal — change-traceability provenance (dim 3)."""

from __future__ import annotations

import json

from gh_bridge import GhResult
from network_policy import NetworkPolicy
from provenance_signal import _pr_association, compute_provenance_signal


def _enabled():
    return NetworkPolicy(enabled=True, requested=True, owner="octo", repo="repo",
                         visibility="public", note="")


def _disabled():
    return NetworkPolicy(enabled=False, requested=False, owner=None, repo=None,
                         visibility="local-only", note="")


def _history_gh(merged_flags):
    """A gh fake: defaultBranchRef → 'main', then a history of commits whose
    associatedPullRequests.merged matches ``merged_flags``."""
    nodes = [{"associatedPullRequests": {"nodes": ([{"merged": m}] if m is not None else [])}}
             for m in merged_flags]
    payload = {"data": {"repository": {"ref": {"target": {"history": {"nodes": nodes}}}}}}

    def fake(args, *, timeout=30):
        joined = " ".join(args)
        if "defaultBranchRef" in joined:
            return GhResult(ok=True, stdout='{"defaultBranchRef": {"name": "main"}}')
        return GhResult(ok=True, stdout=json.dumps(payload))
    return fake


def test_pr_association_ratio():
    gh = _history_gh([True, True, False, True])  # 3/4 linked to a merged PR
    assert _pr_association(gh, "octo", "repo") == 0.75


def test_pr_association_none_without_default_branch():
    def fake(args, *, timeout=30):
        return GhResult(ok=True, stdout="{}")  # no defaultBranchRef
    assert _pr_association(fake, "o", "r") is None


def test_pr_association_none_on_empty_history():
    def fake(args, *, timeout=30):
        joined = " ".join(args)
        if "defaultBranchRef" in joined:
            return GhResult(ok=True, stdout='{"defaultBranchRef": {"name": "main"}}')
        empty = {"data": {"repository": {"ref": {"target": {"history": {"nodes": []}}}}}}
        return GhResult(ok=True, stdout=json.dumps(empty))
    assert _pr_association(fake, "o", "r") is None


def test_pr_association_unlinked_commits_count_zero():
    gh = _history_gh([None, None, True])  # only 1/3 linked (two direct pushes)
    assert abs(_pr_association(gh, "octo", "repo") - 1 / 3) < 1e-9


def test_compute_measurable_when_network_resolves():
    sig = compute_provenance_signal(
        _enabled(), lambda *a, **k: None, assoc=lambda *_: 0.51)
    assert sig.measurable is True
    assert sig.ratio == 0.51
    assert sig.tier == "pr-association"
    assert "51%" in sig.detail


def test_compute_records_enrichment():
    policy = _enabled()
    compute_provenance_signal(policy, lambda *a, **k: None, assoc=lambda *_: 0.9)
    assert any("PR-association" in e for e in policy.enrichments)


def test_compute_falls_back_to_git_log_when_network_off():
    sig = compute_provenance_signal(
        _disabled(), lambda *a, **k: None, assoc=lambda *_: 0.99)
    assert sig.measurable is False
    assert sig.tier == "git-log"
    assert sig.ratio is None


def test_compute_falls_back_when_assoc_unavailable():
    sig = compute_provenance_signal(
        _enabled(), lambda *a, **k: None, assoc=lambda *_: None)
    assert sig.measurable is False
    assert sig.tier == "git-log"
