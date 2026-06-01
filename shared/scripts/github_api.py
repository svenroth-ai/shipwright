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
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

# `gh` calls are network-bound — a bounded timeout keeps a hung request
# from ever stalling the SessionStart hook.
_TIMEOUT_SECONDS = 30

# Artifact download can pull a few-MB zip on slow networks. Give it a
# longer ceiling than a JSON API call, but still strictly bounded.
_DOWNLOAD_TIMEOUT_SECONDS = 60

# Default freshness window for the shipwright-security artifact path —
# 14 days mirrors a typical sprint cycle. A run older than this is
# treated as stale (returns None from latest_security_workflow_run).
# Overridable via the env var (Iterate C — external review HIGH #5).
_ARTIFACT_MAX_AGE_DEFAULT_DAYS = 14.0
_ENV_ARTIFACT_MAX_AGE = "SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS"

# Workflow file basename used by the shipwright-security CI scan. The
# canonical path is locked by ``shared/scripts/lib/security_workflow.py``;
# this constant is the URL-suffix form (basename only) for the
# ``actions/workflows/{file}/runs`` endpoint.
_SECURITY_WORKFLOW_FILE = "security.yml"

# Artifact name produced by ``.github/workflows/security.yml`` —
# ``actions/upload-artifact@v4 with: name: security-scan-results``.
_SECURITY_ARTIFACT_NAME = "security-scan-results"


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


# ---------------------------------------------------------------------------
# Artifact-based security ingestion (Iterate C —
# security-artifact-producer). Added for repos without GHAS Code
# Scanning: pulls the shipwright-security workflow's ``findings.json``
# artifact as a third parallel source alongside cs_alerts + db_alerts.
# ---------------------------------------------------------------------------

def artifact_max_age_days() -> float:
    """Freshness cutoff (in days) for the shipwright-security artifact path.

    Default 14d; overridable via ``SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS``.
    Non-positive / unparseable env values fall back to the default —
    matches the throttle-hours resolution pattern in github_triage.
    """
    raw = os.environ.get(_ENV_ARTIFACT_MAX_AGE)
    if raw:
        try:
            parsed = float(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return _ARTIFACT_MAX_AGE_DEFAULT_DAYS


def latest_security_workflow_run() -> dict | None:
    """Latest successful run of ``.github/workflows/security.yml`` on the
    default branch, gated by the freshness cutoff.

    Iterate C contract:

    1. Branch is auto-resolved via ``default_branch()`` — callers do NOT
       supply it (review finding openai-7: explicit branch handling).
    2. API query: ``actions/workflows/security.yml/runs?branch=<default>
       &status=success&per_page=10`` — filters at the source so feature-
       branch runs cannot leak through (review finding openai-6,
       gemini-3).
    3. The most recent run whose ``created_at`` is within the freshness
       cutoff (``artifact_max_age_days()``) is returned. Older runs
       are skipped (review finding openai-5).
    4. ``None`` on any failure — gh missing, API error, no successful
       run, all runs too stale, unparseable timestamps. Distinguish
       failure from empty per the ADR-052 invariant.
    """
    branch = default_branch()
    encoded_branch = quote(branch, safe="")
    data = _gh_api(
        f"repos/{{owner}}/{{repo}}/actions/workflows/"
        f"{_SECURITY_WORKFLOW_FILE}/runs"
        f"?branch={encoded_branch}&status=success&per_page=10"
    )
    if not isinstance(data, dict):
        return None
    runs = data.get("workflow_runs")
    if not isinstance(runs, list) or not runs:
        return None
    cutoff = datetime.now(timezone.utc).timestamp() - (
        artifact_max_age_days() * 86400.0
    )
    for run in runs:
        if not isinstance(run, dict):
            continue
        # Recency check uses ``run_started_at`` when present — it
        # reflects when the workflow actually started executing, closer
        # to the "scan completion" timestamp than ``created_at`` which
        # is when the run was queued. ``created_at`` is the universally
        # present fallback (external review code finding openai-3).
        ts_str = run.get("run_started_at") or run.get("created_at")
        if not isinstance(ts_str, str):
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts.timestamp() >= cutoff:
            return run
    return None


def download_security_findings(run_id: int) -> list[dict] | None:
    """SAST/SCA findings from the ``security-scan-results`` artifact's
    ``findings.json``. Contract (subprocess hygiene, rglob discovery, semantic
    list-validation, ADR-052 None-vs-``[]``) lives in ``_download_artifact_findings``.
    """
    return _download_artifact_findings(run_id, "findings.json")


def download_prompt_risks(run_id: int) -> list[dict] | None:
    """Prompt-injection findings from the artifact's ``prompt_risks.json`` (same
    contract as ``download_security_findings`` — see ``_download_artifact_findings``)."""
    return _download_artifact_findings(run_id, "prompt_risks.json")


def _download_artifact_findings(run_id: int, filename: str) -> list[dict] | None:
    """Shared impl for the artifact-download helpers: download the
    ``security-scan-results`` artifact and return the ``findings`` array out of
    ``filename`` (``findings.json`` | ``prompt_risks.json``). Same hygiene as
    the original ``download_security_findings`` (argv subprocess, robust rglob,
    semantic list-validation, tempdir cleanup, ADR-052 None-vs-``[]``).
    """
    tmpdir = tempfile.mkdtemp(prefix="shipwright-artifact-")
    try:
        cmd: list[str] = [
            "gh", "run", "download", str(run_id),
            "--name", _SECURITY_ARTIFACT_NAME,
            "--dir", tmpdir,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        # Robust discovery: gh usually flattens, but nested layouts are tolerated.
        matches = list(Path(tmpdir).rglob(filename))
        if not matches:
            return None
        try:
            raw = matches[0].read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        findings = payload.get("findings")
        # Semantic validation — ``findings`` must be a list (possibly empty).
        # Trusting the redundant aggregate would be unsafe if it disagreed.
        if not isinstance(findings, list):
            return None
        # Defensive: every element should be a dict; non-dict entries
        # are silently dropped so the caller's mapper never crashes on
        # malformed individual entries.
        return [f for f in findings if isinstance(f, dict)]
    finally:
        # Best-effort cleanup — never raise if the tempdir already vanished.
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except OSError:
            pass
