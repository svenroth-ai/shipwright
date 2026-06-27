"""Tests for shared/scripts/github_api.py — owner_repo() resolution.

AC-10 of iterate-2026-05-20-triage-launch-surface: a local-first resolver
that returns ``"{owner}/{repo}"`` for recognised GitHub remotes (HTTPS, SSH,
enterprise) and ``None`` on missing/malformed/non-GitHub remotes. The
github action-unit producers depend on this returning a stable
``{owner}/{repo}`` string for their dedup keys.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402


# ---------------------------------------------------------------------------
# parse_github_remote — pure helper, no git invocation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "remote_url,expected",
    [
        # HTTPS — public github.com
        ("https://github.com/acme/foo.git", "acme/foo"),
        ("https://github.com/acme/foo", "acme/foo"),
        # HTTPS with trailing slash
        ("https://github.com/acme/foo/", "acme/foo"),
        # HTTPS with token in URL (e.g. https://x-access-token:...@github.com/...)
        ("https://x-access-token:abc@github.com/acme/foo.git", "acme/foo"),
        # SSH — public github.com
        ("git@github.com:acme/foo.git", "acme/foo"),
        ("git@github.com:acme/foo", "acme/foo"),
        # SSH protocol form (rare but valid)
        ("ssh://git@github.com/acme/foo.git", "acme/foo"),
        # GitHub Enterprise — HTTPS
        ("https://github.example.com/acme/foo.git", "acme/foo"),
        ("https://github.example.com/acme/foo", "acme/foo"),
        # GitHub Enterprise — SSH
        ("git@github.example.com:acme/foo", "acme/foo"),
        # Hyphens, dots, underscores in repo name
        ("https://github.com/acme-corp/my-tool.git", "acme-corp/my-tool"),
        ("https://github.com/acme/my.tool.js", "acme/my.tool.js"),
        ("git@github.com:acme_corp/my_tool.git", "acme_corp/my_tool"),
    ],
)
def test_parse_github_remote_accepts_recognised_shapes(
    remote_url: str, expected: str,
) -> None:
    assert github_api.parse_github_remote(remote_url) == expected


@pytest.mark.parametrize(
    "remote_url",
    [
        # Wrong host — not GitHub
        "https://gitlab.com/acme/foo",
        "https://bitbucket.org/acme/foo.git",
        "git@gitlab.com:acme/foo.git",
        # Empty / malformed
        "",
        "not a url at all",
        "https://github.com/",  # no owner/repo
        "https://github.com/acme",  # owner only, no repo
        # File-protocol (would not be a real GitHub remote)
        "file:///tmp/repo",
    ],
)
def test_parse_github_remote_rejects_invalid(remote_url: str) -> None:
    assert github_api.parse_github_remote(remote_url) is None


def test_parse_github_remote_handles_none() -> None:
    assert github_api.parse_github_remote(None) is None  # type: ignore[arg-type]


def test_parse_github_remote_no_catastrophic_backtracking() -> None:
    """Regression for CodeQL py/redos on ``_GITHUB_HOST_RE``.

    Before the fix the host group ``(github(?:\\.[a-zA-Z0-9.-]+)+)`` had the dot
    in the inner class, making the partition of a ``.-.-.-…`` tail ambiguous —
    exponential backtracking when the trailing ``[:/]owner/repo`` failed. The
    de-ambiguated class resolves it in linear time. A pathological input that
    would hang the old regex must now return ``None`` near-instantly.
    """
    import time

    evil = "git@github" + ".-" * 60 + "!"  # fails [:/]; old regex backtracks
    start = time.perf_counter()
    assert github_api.parse_github_remote(evil) is None
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"parse took {elapsed:.2f}s — ReDoS regression"


# ---------------------------------------------------------------------------
# owner_repo — integration with git remote
# ---------------------------------------------------------------------------

def test_owner_repo_returns_parsed_value_when_remote_resolvable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Happy path: git remote returns a recognised URL; helper returns owner/repo."""

    def fake_git_remote(project_root: Path) -> str | None:
        assert Path(project_root) == tmp_path
        return "git@github.com:acme/foo.git"

    monkeypatch.setattr(github_api, "_git_remote_origin", fake_git_remote)
    assert github_api.owner_repo(tmp_path) == "acme/foo"


def test_owner_repo_returns_none_when_remote_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """No remote configured → None + a single stderr warning."""
    monkeypatch.setattr(github_api, "_git_remote_origin", lambda _: None)
    assert github_api.owner_repo(tmp_path) is None
    captured = capsys.readouterr()
    assert "owner_repo" in captured.err.lower() or "remote" in captured.err.lower()


def test_owner_repo_returns_none_when_remote_unparseable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """git remote returns a value but parse rejects it."""
    monkeypatch.setattr(
        github_api,
        "_git_remote_origin",
        lambda _: "https://gitlab.com/acme/foo",
    )
    assert github_api.owner_repo(tmp_path) is None


def test_owner_repo_does_not_call_gh(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Local-first: must NEVER reach `gh api` (gh requires owner/repo to even call repos/).

    Drift protection — if a future change accidentally calls _gh_api,
    this test catches it.
    """
    monkeypatch.setattr(
        github_api,
        "_git_remote_origin",
        lambda _: "git@github.com:acme/foo.git",
    )

    def boom(*args, **kwargs):
        raise AssertionError(f"unexpected _gh_api call: {args=} {kwargs=}")

    monkeypatch.setattr(github_api, "_gh_api", boom)
    assert github_api.owner_repo(tmp_path) == "acme/foo"
