#!/usr/bin/env python3
"""Stop hook: regenerate `.shipwright/agent_docs/triage_inbox.md`.

AC-3 of iterate-2026-05-11-triage-inbox-1a. Wraps
`shared/scripts/tools/aggregate_triage.py:main` for invocation from
plugin `hooks.json`.

Contract:
- **Never blocks.** Always exits 0, even on internal errors.
- **Greenfield-safe.** Silent no-op when project_root isn't a
  Shipwright-managed project (no `shipwright_run_config.json`).
- **Schema-compliant Stop output** (ADR-042). NO `additionalContext`;
  diagnostics → stderr.
- **Order:** registered as the LAST Stop hook in
  `plugins/shipwright-iterate/hooks/hooks.json` so the aggregate
  observes everything the upstream producers wrote in this Stop chain.

Usage (from `hooks.json`):

    uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/aggregate_triage_on_stop.py"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.project_root import resolve_project_root  # noqa: E402

# aggregate_triage lives at shared/scripts/tools/aggregate_triage.py
from tools import aggregate_triage  # noqa: E402


SHIPWRIGHT_MARKER = "shipwright_run_config.json"


def _resolve_project_root() -> Path:
    try:
        return resolve_project_root()
    except Exception:  # noqa: BLE001
        return Path.cwd()


def _is_shipwright_project(project_root: Path) -> bool:
    return (project_root / SHIPWRIGHT_MARKER).exists()


def _consume_stdin() -> None:
    """Hook protocol sends a JSON payload on stdin; consume + ignore."""
    try:
        json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    _consume_stdin()

    project_root = _resolve_project_root()
    if not _is_shipwright_project(project_root):
        # Greenfield-safe — silent no-op.
        return 0

    try:
        # Reuse the public CLI entry point so behavior is identical to
        # `uv run shared/scripts/tools/aggregate_triage.py`.
        aggregate_triage.main([
            "--project-root", str(project_root),
        ])
    except Exception as exc:  # noqa: BLE001 — never block Stop chain
        # ADR-042: diagnostics on Stop go to stderr, not additionalContext.
        sys.stderr.write(
            f"[aggregate_triage_on_stop] error: {type(exc).__name__}: {exc}\n"
        )
        # Always exit 0 — observability hook, not gate.

    return 0


if __name__ == "__main__":
    sys.exit(main())
