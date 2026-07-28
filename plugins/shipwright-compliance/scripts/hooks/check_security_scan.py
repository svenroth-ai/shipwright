#!/usr/bin/env python3
"""PreToolUse hook: Soft-block deploy when critical security findings exist.

Reads the committed CI-security summary
(``.shipwright/compliance/ci-security.json``) — the scanner chain's own
public-safe output, produced by ``ci_security.summarize_ci_security``.

Until 2026-07-28 it read the RTM row ``| Unresolved findings | N |``: code-review
findings summed over ``work_completed`` events, unrelated to any scan, and
under-reporting by construction. See ``docs/hooks-and-pipeline.md`` and
iterate-2026-07-28-hygiene-sweep (trg-17f53a39). This hook now gates on the
subject it is named for.

This module is the shell: payload parsing, deploy-command detection, and the
fail-open wrapper. **The gate itself is `lib/security_gate.decide`** — read its
docstring for the branch table, the fail-closed posture, and why the threshold is
compared against `by_severity.critical` rather than `open_high_critical`.

Exit codes: 0 = allow (no summary, or clean within threshold);
2 = soft-block (user can say "Continue anyway", gets logged).
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

    # The whole decision lives in lib/security_gate.decide (see its docstring).
    # An import failure here must NOT reach the fail-open wrapper: being unable
    # to evaluate a security gate is not the same as passing it, so it blocks.
    try:
        lib_dir = Path(__file__).resolve().parent.parent / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        from security_gate import decide  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(json.dumps(_hook_block(
            reason=("the security gate could not be loaded "
                    f"({type(exc).__name__}) — refusing to assume a clean scan"),
            details={"state": "gate-unavailable"},
        )))
        return 2

    blocked, reason, details = decide(project_root)
    if not blocked:
        return 0
    print(json.dumps(_hook_block(reason=reason, details=details)))
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
