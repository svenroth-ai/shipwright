#!/usr/bin/env python3
"""Thin GitHub CLI (`gh`) client for the triage importer.

Every fetch function is best-effort and returns ``None`` on ANY failure
(`gh` missing, unauthenticated, HTTP error, JSON parse error) so callers
can distinguish a *failed* fetch (``None``) from a *successful empty* fetch
(``[]``) — the auto-resolve pass in ``github_triage`` depends on that
distinction (a failed fetch must never be read as "all findings cleared").

`gh api` substitutes the ``{owner}`` / ``{repo}`` placeholders from the
current repository's git remote, so no repo slug needs configuring.

Part of iterate-2026-05-19-github-triage-importer. Sibling module:
``github_triage`` (mapping + throttle + orchestrator).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

# `gh` calls are network-bound — a bounded timeout keeps a hung request
# from ever stalling the SessionStart hook.
_TIMEOUT_SECONDS = 30


def gh_available() -> bool:
    """True only if the `gh` CLI is installed AND authenticated.

    Both are required — an installed-but-unauthenticated `gh` fails every
    API call. ``gh auth status`` is a fast token-validation check.
    """
    if shutil.which("gh") is None:
        return False
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _gh_api(path: str, *, paginate: bool = False) -> Any | None:
    """Run ``gh api <path>`` and return parsed JSON, or ``None`` on failure."""
    cmd = ["gh", "api", path]
    if paginate:
        cmd.append("--paginate")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout or "null")
    except json.JSONDecodeError:
        return None


def default_branch() -> str:
    """The repository's default branch; falls back to ``main`` on any failure."""
    data = _gh_api("repos/{owner}/{repo}")
    if isinstance(data, dict):
        branch = data.get("default_branch")
        if isinstance(branch, str) and branch:
            return branch
    return "main"


def _fetch_alert_list(endpoint: str) -> list[dict] | None:
    """Fetch a paginated ``state=open`` alerts endpoint; ``None`` on failure."""
    data = _gh_api(
        f"repos/{{owner}}/{{repo}}/{endpoint}?state=open&per_page=100",
        paginate=True,
    )
    return data if isinstance(data, list) else None


def fetch_code_scanning_alerts() -> list[dict] | None:
    """Open code-scanning alerts (CodeQL + uploaded SARIF results)."""
    return _fetch_alert_list("code-scanning/alerts")


def fetch_dependabot_alerts() -> list[dict] | None:
    """Open Dependabot (dependency-vulnerability) alerts."""
    return _fetch_alert_list("dependabot/alerts")


def fetch_secret_scanning_alerts() -> list[dict] | None:
    """Open secret-scanning alerts."""
    return _fetch_alert_list("secret-scanning/alerts")


# ---------------------------------------------------------------------------
# owner_repo() — local-first repository identity resolution
# Added in iterate-2026-05-20-triage-launch-surface for the github action-unit
# producers. NEVER calls `gh api` (gh expects owner/repo to be passed
# IN — chicken-and-egg). Pure git-remote parse.
# ---------------------------------------------------------------------------

# Capture group 1 = owner, group 2 = repo. Anchored at end so trailing
# ``.git`` (optional) and a single trailing slash are tolerated. Accepts
# `github.com` and any `github.*` host (GitHub Enterprise).
_GITHUB_HOST_RE = re.compile(
    r"^(?:https?://(?:[^@/]+@)?|ssh://(?:git@)?|git@)"
    r"(github(?:\.[a-zA-Z0-9.-]+)+)"
    r"[:/]"
    r"([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"/"
    r"([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"(?:\.git)?/?$"
)


def parse_github_remote(remote_url: str | None) -> str | None:
    """Parse a git remote URL into ``"{owner}/{repo}"``, or ``None`` if unrecognised.

    Accepts the common forms produced by ``git remote get-url``:

    - ``https://github.com/owner/repo[.git][/]``
    - ``https://x-access-token:TOKEN@github.com/owner/repo[.git]``
    - ``git@github.com:owner/repo[.git]``
    - ``ssh://git@github.com/owner/repo[.git]``
    - GitHub Enterprise variants (``github.example.com``)

    Anything else (gitlab, bitbucket, file://, malformed, empty) returns
    ``None``. The match accepts hyphens / dots / underscores in owner +
    repo segments but rejects single-segment paths (no owner, or no repo).
    """
    if not isinstance(remote_url, str) or not remote_url.strip():
        return None
    match = _GITHUB_HOST_RE.match(remote_url.strip())
    if match is None:
        return None
    owner = match.group(2)
    repo = match.group(3)
    # The repo segment may greedily include a trailing ``.git`` because
    # ``.`` is a valid mid-segment character (e.g. ``my.tool.js``). Strip
    # it explicitly — the trailing ``(?:\.git)?`` group in the regex only
    # fires when the greedy class didn't already eat it.
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return f"{owner}/{repo}"


def _git_remote_origin(project_root: Path | str) -> str | None:
    """Return the ``origin`` remote URL via ``git remote get-url``, or ``None``.

    Isolated as a thin shim so tests can monkeypatch it without touching the
    parser. Captures stderr; never raises.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def owner_repo(project_root: Path | str) -> str | None:
    """Return ``"{owner}/{repo}"`` for the project's ``origin`` remote.

    Local-first: parses ``git remote get-url origin``. Never calls ``gh api``
    because ``gh api repos/{owner}/{repo}`` requires owner/repo to already
    be known (the very value this helper is trying to produce).

    On any failure (no remote, malformed URL, non-GitHub host) returns
    ``None`` and writes a single concise warning to stderr so producers
    can skip emission of repo-scoped action-units without emitting
    malformed dedup keys like ``gh-security:`` (review finding #4 of
    iterate-2026-05-20-triage-launch-surface).
    """
    remote_url = _git_remote_origin(project_root)
    if remote_url is None:
        sys.stderr.write(
            "[github-api] owner_repo: no `origin` remote configured "
            f"in {project_root}; skipping repo-scoped action-units.\n"
        )
        return None
    parsed = parse_github_remote(remote_url)
    if parsed is None:
        sys.stderr.write(
            f"[github-api] owner_repo: remote {remote_url!r} is not a "
            "recognised GitHub URL; skipping repo-scoped action-units.\n"
        )
        return None
    return parsed


def fetch_workflow_runs(branch: str) -> list[dict] | None:
    """Recent workflow runs on ``branch`` (newest first); ``None`` on failure."""
    encoded_branch = quote(branch, safe="")
    data = _gh_api(
        f"repos/{{owner}}/{{repo}}/actions/runs?branch={encoded_branch}&per_page=100"
    )
    if isinstance(data, dict):
        runs = data.get("workflow_runs")
        if isinstance(runs, list):
            return runs
    return None
