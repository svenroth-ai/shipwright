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
import shutil
import subprocess
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
