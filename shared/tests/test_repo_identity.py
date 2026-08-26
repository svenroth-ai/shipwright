"""Tests for `repo_identity.py` — normalizing a git `origin` remote to a
GitHub `owner/repo` identity, shared by the release-notes link-host
allowlist and every `gh --repo` call."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from repo_identity import normalize_github_origin, resolve_repo_identity  # noqa: E402


@pytest.mark.parametrize(
    "url,expected",
    [
        ("git@github.com:svenroth-ai/shipwright.git", "svenroth-ai/shipwright"),
        ("git@github.com:svenroth-ai/shipwright", "svenroth-ai/shipwright"),
        ("ssh://git@github.com/svenroth-ai/shipwright.git", "svenroth-ai/shipwright"),
        ("ssh://git@github.com/svenroth-ai/shipwright", "svenroth-ai/shipwright"),
        ("https://github.com/svenroth-ai/shipwright.git", "svenroth-ai/shipwright"),
        ("https://github.com/svenroth-ai/shipwright", "svenroth-ai/shipwright"),
        ("https://github.com/svenroth-ai/shipwright/", "svenroth-ai/shipwright"),
        ("https://gitlab.com/svenroth-ai/shipwright", None),
        ("not a url", None),
    ],
)
def test_normalize_github_origin(url, expected):
    assert normalize_github_origin(url) == expected


def test_resolve_repo_identity_reads_git_remote(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:acme/widgets.git"],
        cwd=tmp_path, check=True,
    )
    assert resolve_repo_identity(tmp_path) == "acme/widgets"


def test_resolve_repo_identity_no_remote_returns_none(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert resolve_repo_identity(tmp_path) is None


def test_resolve_repo_identity_none_when_git_itself_fails(tmp_path: Path):
    with patch("repo_identity.subprocess.run", side_effect=OSError("git not found")):
        assert resolve_repo_identity(tmp_path) is None
