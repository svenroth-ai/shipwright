#!/usr/bin/env python3
"""Aikido Security API client for shipwright-security.

Queries the Aikido REST API for security findings on connected GitHub repos.
Supports 4 subcommands: issues, repos, summary, report.

Output is always JSON via structured_success / structured_error.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

def _fix_windows_encoding() -> None:
    """Fix Windows console encoding for Unicode characters."""
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent.parent
SHARED_ROOT = PLUGIN_ROOT.parent.parent / "shared"

# Try importing shared errors; fall back to inline implementation
try:
    sys.path.insert(0, str(SHARED_ROOT / "scripts"))
    from lib.errors import structured_error, structured_success  # noqa: E402
except (ImportError, ModuleNotFoundError):
    # Inline fallback when running outside full Shipwright context
    def structured_error(what_failed, what_was_attempted, error_category, is_retryable,
                         partial_results=None, alternatives=None, context=None):
        return {
            "success": False,
            "error": {
                "what_failed": what_failed,
                "what_was_attempted": what_was_attempted,
                "error_category": error_category,
                "is_retryable": is_retryable,
                "partial_results": partial_results or {},
                "alternatives": alternatives or [],
                "context": context or {},
            },
        }

    def structured_success(data=None):
        result = {"success": True}
        if data:
            result.update(data)
        return result

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "https://app.aikido.dev/api"
TOKEN_URL = f"{API_BASE}/oauth/token"

# Finding classification rules
AUTO_FIXABLE_TYPES = {"dependency", "sca"}
AGENT_FIXABLE_TYPES = {"sast", "secret_detection"}

SETUP_URL = "https://app.aikido.dev/settings/integrations/api/aikido/rest"


# ---------------------------------------------------------------------------
# Environment loading — centralized via shared/scripts/lib/env.py
# ---------------------------------------------------------------------------

sys.path.insert(0, str(SHARED_ROOT / "scripts" / "lib"))
from env import load_shipwright_env
load_shipwright_env()


# ---------------------------------------------------------------------------
# Aikido API Client
# ---------------------------------------------------------------------------

class AikidoClient:
    """Client for the Aikido Security REST API."""

    def __init__(self) -> None:
        self.client_id = os.environ.get("AIKIDO_CLIENT_ID", "")
        self.client_secret = os.environ.get("AIKIDO_CLIENT_SECRET", "")
        self._token: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _authenticate(self) -> str:
        """Get an OAuth2 bearer token via client credentials grant."""
        import requests

        credentials = f"{self.client_id}:{self.client_secret}"
        b64 = base64.b64encode(credentials.encode()).decode()

        resp = requests.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("access_token", data.get("token", ""))

    def _get_token(self) -> str:
        """Get cached token or authenticate."""
        if not self._token:
            self._token = self._authenticate()
        return self._token

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make an authenticated GET request to the Aikido API."""
        import requests

        token = self._get_token()
        resp = requests.get(
            f"{API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Finding classification
# ---------------------------------------------------------------------------

def classify_finding(finding: dict[str, Any]) -> str:
    """Classify a finding into a remediation category.

    Returns one of: auto-fixable, agent-fixable, needs-review, informational.
    """
    severity = finding.get("severity", "").lower()
    finding_type = finding.get("type", "").lower()

    # Low severity and informational → just log
    if severity in ("low", "info", "informational"):
        return "informational"

    # Dependency/SCA issues with known patches → auto-fixable
    if finding_type in AUTO_FIXABLE_TYPES:
        return "auto-fixable"

    # SAST / secret detection → agent can analyze and fix
    if finding_type in AGENT_FIXABLE_TYPES:
        return "agent-fixable"

    # Everything else (architecture, business logic, etc.) → human review
    return "needs-review"


def normalize_issues(data: Any) -> list[dict[str, Any]]:
    """Normalize Aikido API response to a list of issue dicts.

    Defensive: handles both list and dict responses since exact API shape
    is not yet confirmed.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("issues", data.get("data", data.get("results", [])))
    return []


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_issues(client: AikidoClient, args: argparse.Namespace) -> dict[str, Any]:
    """Fetch and filter security issues."""
    params: dict[str, Any] = {}

    if args.repo:
        params["filter_code_repo_name"] = args.repo
    if args.severity:
        params["filter_severities"] = args.severity
    if args.status:
        params["filter_status"] = args.status
    if args.type:
        params["filter_type"] = args.type

    data = client.get("/issues/export", params)
    issues = normalize_issues(data)

    # Add classification to each issue
    for issue in issues:
        issue["_remediation_class"] = classify_finding(issue)

    return structured_success(data={
        "command": "issues",
        "data": issues,
        "count": len(issues),
        "filters": params,
    })


def cmd_repos(client: AikidoClient, _args: argparse.Namespace) -> dict[str, Any]:
    """List connected repositories."""
    data = client.get("/code-repos")
    repos = data if isinstance(data, list) else data.get("repositories", data.get("data", []))

    return structured_success(data={
        "command": "repos",
        "data": repos,
        "count": len(repos),
    })


def cmd_summary(client: AikidoClient, args: argparse.Namespace) -> dict[str, Any]:
    """Generate a summary dashboard with counts by severity, type, status."""
    params: dict[str, Any] = {}
    if args.repo:
        params["filter_code_repo_name"] = args.repo

    data = client.get("/issues/export", params)
    issues = normalize_issues(data)

    severity_counts = Counter(i.get("severity", "unknown") for i in issues)
    type_counts = Counter(i.get("type", "unknown") for i in issues)
    status_counts = Counter(i.get("status", "unknown") for i in issues)
    class_counts = Counter(classify_finding(i) for i in issues)

    return structured_success(data={
        "command": "summary",
        "total": len(issues),
        "by_severity": dict(severity_counts),
        "by_type": dict(type_counts),
        "by_status": dict(status_counts),
        "by_remediation_class": dict(class_counts),
        "filters": params,
    })


def cmd_report(client: AikidoClient, args: argparse.Namespace) -> dict[str, Any]:
    """Fetch data for a security report. Claude formats and writes the file."""
    params: dict[str, Any] = {}
    if args.repo:
        params["filter_code_repo_name"] = args.repo

    data = client.get("/issues/export", params)
    issues = normalize_issues(data)

    # Add classification
    for issue in issues:
        issue["_remediation_class"] = classify_finding(issue)

    severity_counts = Counter(i.get("severity", "unknown") for i in issues)
    class_counts = Counter(classify_finding(i) for i in issues)

    repo_name = args.repo or "all-repos"
    safe_name = repo_name.replace("/", "-")

    return structured_success(data={
        "command": "report",
        "data": issues,
        "count": len(issues),
        "by_severity": dict(severity_counts),
        "by_remediation_class": dict(class_counts),
        "filters": params,
        "report_instructions": {
            "suggested_filename": f"aikido-report-{safe_name}.md",
            "output_path": args.output if args.output else None,
        },
    })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aikido Security API client for shipwright-security",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # issues
    p_issues = sub.add_parser("issues", help="List security issues with filters")
    p_issues.add_argument("--repo", help="Filter by repo (owner/name)")
    p_issues.add_argument("--severity", help="Filter by severity (critical,high,medium,low)")
    p_issues.add_argument("--status", help="Filter by status (open,closed,ignored)")
    p_issues.add_argument("--type", help="Filter by type (sast,sca,secret_detection,iac)")

    # repos
    sub.add_parser("repos", help="List connected repositories")

    # summary
    p_summary = sub.add_parser("summary", help="Security dashboard with counts")
    p_summary.add_argument("--repo", help="Filter by repo (owner/name)")

    # report
    p_report = sub.add_parser("report", help="Fetch data for security report")
    p_report.add_argument("--repo", help="Filter by repo (owner/name)")
    p_report.add_argument("--output", help="Output file path for report")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    client = AikidoClient()

    if not client.is_configured:
        result = structured_error(
            what_failed="Aikido API credentials not configured",
            what_was_attempted=f"Running '{args.command}' command",
            error_category="permission",
            is_retryable=False,
            alternatives=[
                f"Create API credentials at {SETUP_URL}",
                "Add AIKIDO_CLIENT_ID and AIKIDO_CLIENT_SECRET to <shipwright_root>/.env.local",
                "See references/setup-guide.md for step-by-step instructions",
            ],
        )
        print(json.dumps(result, ensure_ascii=False))
        return 1

    try:
        commands = {
            "issues": cmd_issues,
            "repos": cmd_repos,
            "summary": cmd_summary,
            "report": cmd_report,
        }
        result = commands[args.command](client, args)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    except Exception as e:
        error_msg = str(e)
        category = "transient"
        retryable = True

        if "401" in error_msg or "403" in error_msg:
            category = "permission"
            retryable = False
        elif "422" in error_msg or "400" in error_msg:
            category = "validation"
            retryable = False

        result = structured_error(
            what_failed=f"Aikido API call failed: {error_msg}",
            what_was_attempted=f"Running '{args.command}' command",
            error_category=category,
            is_retryable=retryable,
            alternatives=["Check API credentials", "Verify network connectivity"],
            context={"command": args.command},
        )
        print(json.dumps(result, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())
