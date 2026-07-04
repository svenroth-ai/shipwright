"""Tests for gh_bridge — remote parsing + gh failure classification (hermetic)."""

from __future__ import annotations

import pytest

from gh_bridge import GhResult, gh_json, owner_repo_from_remote, run_gh


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/octocat/Hello-World.git", ("octocat", "Hello-World")),
    ("https://github.com/octocat/Hello-World", ("octocat", "Hello-World")),
    ("git@github.com:octocat/Hello-World.git", ("octocat", "Hello-World")),
    ("ssh://git@github.com/octocat/Hello-World", ("octocat", "Hello-World")),
    ("https://github.example.com/org/proj.git", ("org", "proj")),
])
def test_owner_repo_parsed(url, expected):
    assert owner_repo_from_remote(url) == expected


@pytest.mark.parametrize("url", ["", "https://gitlab.com/o/r.git", "not a url", "/local/path"])
def test_non_github_remote_is_none(url):
    assert owner_repo_from_remote(url) is None


@pytest.mark.parametrize("url", [
    "git@github.com:../evil.git",
    "https://github.com/../evil.git",
    "https://github.com/o w n/r",       # space is not a valid slug char
    "https://github.com/o/r%2fx",        # percent-encoded path segment
])
def test_malformed_slug_rejected(url):
    # A crafted remote must not inject `..`/odd chars into a gh api path.
    assert owner_repo_from_remote(url) is None


def test_gh_json_parses_stdout_on_success():
    def fake(_args, *, timeout=30):
        return GhResult(ok=True, stdout='{"visibility": "PUBLIC"}')
    result, data = gh_json(fake, ["repo", "view"])
    assert result.ok and data == {"visibility": "PUBLIC"}


def test_gh_json_none_on_failure():
    def fake(_args, *, timeout=30):
        return GhResult(ok=False, error="rate_limited")
    result, data = gh_json(fake, ["api", "x"])
    assert not result.ok and data is None


def test_gh_json_none_on_non_json():
    def fake(_args, *, timeout=30):
        return GhResult(ok=True, stdout="not json")
    _result, data = gh_json(fake, ["x"])
    assert data is None


def test_run_gh_missing_binary_is_not_found(monkeypatch):
    def boom(*_a, **_k):
        raise FileNotFoundError("gh")
    monkeypatch.setattr("gh_bridge.subprocess.run", boom)
    assert run_gh(["repo", "view"]).error == "not_found"


def test_run_gh_classifies_rate_limit(monkeypatch):
    class P:
        returncode = 1
        stdout = ""
        stderr = "HTTP 403: API rate limit exceeded"
    monkeypatch.setattr("gh_bridge.subprocess.run", lambda *a, **k: P())
    r = run_gh(["api", "x"])
    assert not r.ok and r.error == "rate_limited"


def test_run_gh_classifies_auth(monkeypatch):
    class P:
        returncode = 1
        stdout = ""
        stderr = "gh auth login required"
    monkeypatch.setattr("gh_bridge.subprocess.run", lambda *a, **k: P())
    assert run_gh(["api", "x"]).error == "auth"


def test_run_gh_timeout(monkeypatch):
    import subprocess as sp

    def boom(*_a, **_k):
        raise sp.TimeoutExpired(cmd="gh", timeout=1)
    monkeypatch.setattr("gh_bridge.subprocess.run", boom)
    assert run_gh(["api", "x"]).error == "timeout"
