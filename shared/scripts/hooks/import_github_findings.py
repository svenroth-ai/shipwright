#!/usr/bin/env python3
"""SessionStart hook: import GitHub-reported findings into the triage inbox.

Throttled (default 6h, configurable) and fail-soft — ALWAYS exits 0 so it
can never block a session. Pull-based via the `gh` CLI; the import logic
lives in ``shared/scripts/github_triage``.

Exit codes:
  0 = allow (always — informational only, never blocks)

Part of iterate-2026-05-19-github-triage-importer.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Hook bootstrap — add `shared/scripts` so `github_triage` (and its `triage`
# / `github_api` siblings) resolve regardless of the hook's launch cwd.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))


def _resolve_project_root() -> str:
    """Resolve the project root, falling back to the current directory."""
    try:
        from lib.project_root import resolve_project_root  # noqa: PLC0415
        return str(resolve_project_root())
    except (ImportError, ValueError):
        return os.getcwd()


def run(project_root: str) -> int:
    """Throttled GitHub-findings import. Returns 0 unconditionally (fail-soft)."""
    try:
        import github_triage  # noqa: PLC0415 — after sys.path bootstrap
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[github-triage] module import failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return 0

    try:
        if not github_triage.is_due(project_root):
            return 0  # throttled — no gh call this session

        result = github_triage.import_findings(project_root)

        if not result.get("gh_available"):
            sys.stderr.write(
                "[github-triage] gh CLI unavailable or unauthenticated — "
                "skipped (will retry next session).\n"
            )
            return 0

        # gh was reachable — advance the throttle clock even if 0 findings,
        # so a quiet repo is not re-polled every session.
        github_triage.write_last_import(project_root, datetime.now(timezone.utc))

        appended = result.get("appended", 0)
        resolved = result.get("resolved", 0)
        if appended or resolved:
            message = (
                f"GitHub findings synced to triage: {appended} new, "
                f"{resolved} auto-resolved. "
                "Review: .shipwright/agent_docs/triage_inbox.md"
            )
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": message,
                }
            }))
    except Exception as exc:  # noqa: BLE001 — fail-soft, never block a session
        sys.stderr.write(
            f"[github-triage] import error: {type(exc).__name__}: {exc}\n"
        )
    return 0


def main() -> int:
    return run(_resolve_project_root())


if __name__ == "__main__":
    sys.exit(main())
