#!/usr/bin/env python3
"""PreToolUse hook: Soft-block deploy when critical security findings exist.

Checks compliance reports for unresolved critical findings and blocks
deploy commands if any remain.

Exit codes:
  0 = allow (no findings data, or no critical findings)
  2 = soft-block (user can say "Continue anyway", gets logged)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


def _resolve_project_root() -> str:
    """Resolve the managed project root.

    Hooks fire with cwd = workspace root, which in a subdirectory-project
    layout is one level ABOVE the managed project. ``os.getcwd()`` therefore
    found no compliance RTM and the deploy gate silently failed open (F5).
    ``resolve_project_root`` auto-descends into the single managed subdir (and
    honors ``SHIPWRIGHT_PROJECT_ROOT``), falling back to cwd otherwise.
    """
    try:
        shared_scripts = Path(__file__).resolve().parents[4] / "shared" / "scripts"
        if str(shared_scripts) not in sys.path:
            sys.path.insert(0, str(shared_scripts))
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return str(resolve_project_root())
    except (ImportError, ValueError):
        env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
        return env_root if env_root else os.getcwd()


def _hook_block(reason: str, details: dict[str, Any]) -> dict[str, Any]:
    """Build soft-block hook output with override support."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"BLOCKED: {reason}\n\n"
                "The user may say 'Continue anyway' to override this check. "
                "If they do, log the override to .shipwright/agent_docs/compliance_overrides.log "
                "with timestamp, hook name 'check_security_scan', and reason.\n\n"
                "Note: Security findings will be flagged again before production deploy."
            ),
            "blocked": True,
            "reason": reason,
            "details": details,
        }
    }


def get_unresolved_findings(project_root: str) -> tuple[int, list[str]]:
    """Parse unresolved findings count and details from RTM.

    Returns (unresolved_count, finding_descriptions).
    """
    rtm_path = str(Path(project_root) / ".shipwright" / "compliance" / "traceability-matrix.md")
    if not os.path.exists(rtm_path):
        return 0, []

    try:
        with open(rtm_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return 0, []

    # Match "| Unresolved findings | N |"
    match = re.search(r"Unresolved findings\s*\|\s*(\d+)", content)
    unresolved = int(match.group(1)) if match else 0

    # Collect sections with FAIL status
    failing = []
    for line in content.splitlines():
        if line.startswith("|") and "FAIL" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                failing.append(parts[2])  # section name

    return unresolved, failing


def get_threshold(project_root: str) -> int:
    """Load allowed critical findings from compliance config."""
    config_path = os.path.join(project_root, "shipwright_compliance_config.json")
    if not os.path.exists(config_path):
        return 0  # default: zero tolerance

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        return config.get("enforcement", {}).get("allowed_critical_findings", 0)
    except (json.JSONDecodeError, OSError):
        return 0


# Command families this gate soft-blocks (the actual deploy CLIs / scripts).
_DEPLOY_PATTERNS = ("deploy", "jelastic", "vercel", "fly deploy", "railway up")
# Quoted argument spans — where justifications, commit messages, and `echo`
# prose live. Stripped BEFORE matching so a deploy-family word inside an
# argument *value* never false-triggers the gate.
_QUOTED_SPAN_RE = re.compile(r'"[^"]*"|\'[^\']*\'')


def _is_deploy_command(command: str) -> bool:
    """True iff the command *structure* (not a quoted argument value) names a
    deploy.

    The gate used to substring-match the raw command, so any unrelated command
    that merely *mentioned* a deploy word in a quoted value — e.g.
    ``surface_verification.py --justification "...no status.json in any
    deployed flow..."`` or ``echo "no deploy-family words"`` — was wrongly
    soft-blocked during iterate finalization. Quoted spans are data, not the
    command, so they are removed first; the real deploy CLI / script / path
    (``vercel``, ``jelastic ...``, ``bash deploy.sh``, ``railway up``) stays
    visible and still triggers the gate.
    """
    unquoted = _QUOTED_SPAN_RE.sub(" ", command).lower()
    return any(p in unquoted for p in _DEPLOY_PATTERNS)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0

    # Only check Bash tool calls that actually invoke a deploy (quoted argument
    # values are ignored — see _is_deploy_command).
    command = payload.get("tool_input", {}).get("command", "")
    if not _is_deploy_command(command):
        return 0

    project_root = _resolve_project_root()

    unresolved, failing_sections = get_unresolved_findings(project_root)
    if unresolved == 0:
        return 0

    threshold = get_threshold(project_root)
    if unresolved <= threshold:
        return 0

    print(json.dumps(_hook_block(
        reason=f"{unresolved} unresolved finding(s) exceed allowed threshold ({threshold})",
        details={
            "unresolved_findings": unresolved,
            "allowed_threshold": threshold,
            "failing_sections": failing_sections,
        },
    )))
    return 2


def _run() -> int:
    """Entrypoint with fail-open semantics.

    A PreToolUse ``Bash`` hook fires on every Bash call; an unhandled crash here
    would make Claude Code hard-block the unrelated command. Route ``main()``
    through ``run_failopen`` so any internal error logs + ALLOWs (exit 0). The
    deliberate soft-block (``main`` returns 2) passes through unchanged. Even the
    guard's own import failing must not hard-block — fall back to ALLOW.
    """
    try:
        lib_dir = Path(__file__).resolve().parent.parent / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        from hook_failopen import run_failopen  # noqa: PLC0415

        return run_failopen("check_security_scan", main)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(_run())
