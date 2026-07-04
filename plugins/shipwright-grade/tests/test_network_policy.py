"""Tests for network_policy — the local-only default + private auto-disable."""

from __future__ import annotations

from gh_bridge import GhResult
from network_policy import resolve_network_policy

_REMOTE = "https://github.com/octocat/Hello-World.git"


def _gh(visibility="PUBLIC", *, error=""):
    def fake(_args, *, timeout=30):
        if error:
            return GhResult(ok=False, error=error)
        return GhResult(ok=True, stdout=f'{{"visibility": "{visibility}"}}')
    return fake


def test_default_is_local_only():
    p = resolve_network_policy(
        allow_network=False, allow_private=False, remote_url=_REMOTE, gh=_gh())
    assert p.enabled is False
    assert p.requested is False
    assert "local-only" in p.note


def test_public_repo_enriches_when_requested():
    p = resolve_network_policy(
        allow_network=True, allow_private=False, remote_url=_REMOTE, gh=_gh("PUBLIC"))
    assert p.enabled is True
    assert (p.owner, p.repo) == ("octocat", "Hello-World")
    assert p.visibility == "public"


def test_private_repo_auto_disabled():
    p = resolve_network_policy(
        allow_network=True, allow_private=False, remote_url=_REMOTE, gh=_gh("PRIVATE"))
    assert p.enabled is False
    assert "auto-disabled" in p.note
    assert "--allow-network-private" in p.note


def test_private_repo_override_enables():
    p = resolve_network_policy(
        allow_network=True, allow_private=True, remote_url=_REMOTE, gh=_gh("PRIVATE"))
    assert p.enabled is True
    assert p.visibility == "private"


def test_unverifiable_visibility_is_conservative():
    # gh failed (rate-limited) → visibility unknown → auto-disabled unless override.
    p = resolve_network_policy(
        allow_network=True, allow_private=False, remote_url=_REMOTE,
        gh=_gh(error="rate_limited"))
    assert p.enabled is False
    assert "unverifiable" in p.note


def test_unverifiable_with_private_override_enables():
    p = resolve_network_policy(
        allow_network=True, allow_private=True, remote_url=_REMOTE,
        gh=_gh(error="rate_limited"))
    assert p.enabled is True


def test_gh_missing_is_local_only():
    p = resolve_network_policy(
        allow_network=True, allow_private=False, remote_url=_REMOTE,
        gh=_gh(error="not_found"))
    assert p.enabled is False
    assert "gh CLI is not available" in p.note


def test_no_github_remote_is_local_only():
    p = resolve_network_policy(
        allow_network=True, allow_private=False,
        remote_url="https://gitlab.com/o/r.git", gh=_gh())
    assert p.enabled is False
    assert "no GitHub remote" in p.note


def test_record_dedupes_enrichments():
    p = resolve_network_policy(
        allow_network=True, allow_private=False, remote_url=_REMOTE, gh=_gh())
    p.record("code-scanning SARIF")
    p.record("code-scanning SARIF")
    p.record("CI JUnit")
    assert p.enrichments == ["code-scanning SARIF", "CI JUnit"]
