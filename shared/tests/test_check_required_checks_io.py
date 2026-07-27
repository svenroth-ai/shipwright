"""The required-check producer's host-call primitives.

@FR-01.17

Everything here is about the two questions that must be answered before any
policy can be compared: *can I run `gh` at all*, and *which repository am I even
talking about*. Both were wrong in the first draft and both fail silently.

The decisions taken once the host HAS answered live in
``test_check_required_checks_cli.py``; the pure set comparison lives in
``test_required_checks_drift.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _required_checks_fakes import (  # noqa: E402
    NOT_FOUND,
    REPO_ROOT,
    Resp,
    load_producer,
)

crc = load_producer()


# ---------------------------------------------------------------------------
# _gh — the two failures users actually hit
# ---------------------------------------------------------------------------


def test_missing_gh_binary_is_a_controlled_error(monkeypatch) -> None:
    """`gh` absent raises FileNotFoundError, which is not CalledProcessError.

    So it was caught by nothing and escaped as a traceback with exit 1, while
    the docstring promised exit 2 — for the single most common user failure.
    """
    def _boom(*a, **k):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(crc.subprocess, "run", _boom)
    with pytest.raises(crc.GhError) as excinfo:
        crc._gh(["api", "repos/o/r"])
    assert "not installed" in str(excinfo.value)
    assert excinfo.value.status is None


def test_gh_timeout_is_a_controlled_error(monkeypatch) -> None:
    def _hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="gh", timeout=60)

    monkeypatch.setattr(crc.subprocess, "run", _hang)
    with pytest.raises(crc.GhError) as excinfo:
        crc._gh(["api", "repos/o/r"])
    assert "timed out" in str(excinfo.value)


def test_http_status_is_carried_off_stderr(monkeypatch) -> None:
    """404-vs-403 is the whole basis for 'no policy' vs 'could not ask'."""
    monkeypatch.setattr(crc.subprocess, "run", lambda *a, **k: NOT_FOUND)
    with pytest.raises(crc.GhError) as excinfo:
        crc._gh(["api", "repos/o/r"])
    assert excinfo.value.status == 404


def test_a_failure_with_no_http_code_carries_no_status(monkeypatch) -> None:
    """A network error must not be mistaken for an API answer."""
    monkeypatch.setattr(
        crc.subprocess, "run", lambda *a, **k: Resp(1, "", "dial tcp: no route to host")
    )
    with pytest.raises(crc.GhError) as excinfo:
        crc._gh(["api", "repos/o/r"])
    assert excinfo.value.status is None


# ---------------------------------------------------------------------------
# resolve_repo — a slug is READ, never assumed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/o/r.git\n", "o/r"),
    ("https://github.com/o/r\n", "o/r"),
    ("git@github.com:o/r.git\n", "o/r"),
    ("ssh://git@github.com/o/r.git\n", "o/r"),
])
def test_github_remotes_resolve_to_owner_name(monkeypatch, url, expected) -> None:
    monkeypatch.setattr(crc.subprocess, "run", lambda *a, **k: Resp(0, url))
    assert crc.resolve_repo(REPO_ROOT) == expected


@pytest.mark.parametrize("url", [
    "gh:o/r\n",                           # SSH host alias — no github.com anywhere
    "https://git.example.com/o/r.git\n",  # GitHub Enterprise / another forge
    "https://github.com/\n",              # the host, but no owner/name
])
def test_a_non_github_remote_is_refused_not_guessed_at(monkeypatch, url) -> None:
    """`rsplit` on a missing separator returns the WHOLE string.

    Without this guard the raw URL became the "slug" and was handed to
    `gh api repos/<url>` — a malformed identity presented as a real one.
    """
    monkeypatch.setattr(crc.subprocess, "run", lambda *a, **k: Resp(0, url))
    with pytest.raises(RuntimeError) as excinfo:
        crc.resolve_repo(REPO_ROOT)
    assert "--repo" in str(excinfo.value), "the error must name the way out"


def test_missing_origin_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(crc.subprocess, "run", lambda *a, **k: Resp(0, "\n"))
    with pytest.raises(RuntimeError, match="no `origin` remote"):
        crc.resolve_repo(REPO_ROOT)


def test_git_itself_failing_is_a_controlled_error(monkeypatch) -> None:
    def _boom(*a, **k):
        raise OSError("git not found")

    monkeypatch.setattr(crc.subprocess, "run", _boom)
    with pytest.raises(RuntimeError, match="could not run `git`"):
        crc.resolve_repo(REPO_ROOT)
