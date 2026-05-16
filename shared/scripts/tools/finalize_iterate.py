#!/usr/bin/env python3
"""Deterministic iterate finalization — replaces manual F5a/F5b/F7/F11.

Runs all iterate finalization steps in correct order:
  1. Update build dashboard  (F5b)
  2. Update compliance docs  (F5a)
  3. Record work_completed event  (F7, if --commit given)
  4. Generate session handoff  (F11)

Each step is idempotent and best-effort: a failure in one step does not
block the others.  Returns structured JSON result on stdout.

Usage:
    uv run finalize_iterate.py --project-root <path> --run-id <id> [--commit <sha>] [--reason <text>]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))


def _update_dashboard(project_root: Path, session_id: str, run_id: str) -> str | None:
    """Update build_dashboard.md. Returns written path or None.

    ``run_id`` is embedded in the dashboard header so the F11 finalization
    verifier (check_build_dashboard_has_run_id) has a deterministic marker:
    F5b renders this dashboard BEFORE the F6 commit + F7 event, so the new
    commit SHA cannot yet be in it.
    """
    try:
        from tools.update_build_dashboard import generate_dashboard

        content = generate_dashboard(
            project_root, phase="iterate", session_id=session_id, run_id=run_id
        )
        out_path = project_root / ".shipwright" / "agent_docs" / "build_dashboard.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return str(out_path.relative_to(project_root))
    except Exception as exc:
        print(f"[finalize_iterate] dashboard failed: {exc}", file=sys.stderr)
        return None


def _update_compliance(project_root: Path) -> list[str]:
    """Regenerate compliance reports. Returns list of written paths."""
    # _SCRIPTS_DIR = shared/scripts → parent.parent = repo root
    compliance_plugin = _SCRIPTS_DIR.parent.parent / "plugins" / "shipwright-compliance"
    script = compliance_plugin / "scripts" / "tools" / "update_compliance.py"

    if not script.exists():
        return []

    try:
        result = subprocess.run(
            [sys.executable, str(script),
             "--project-root", str(project_root),
             "--phase", "iterate"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            compliance_dir = project_root / ".shipwright" / "compliance"
            if compliance_dir.is_dir():
                return [str(f.relative_to(project_root)) for f in compliance_dir.iterdir() if f.is_file()]
        else:
            print(f"[finalize_iterate] compliance failed: {result.stderr[:200]}", file=sys.stderr)
    except Exception as exc:
        print(f"[finalize_iterate] compliance failed: {exc}", file=sys.stderr)
    return []


def _record_event(project_root: Path, commit: str, run_id: str, description: str) -> str | None:
    """Record work_completed event. Returns event ID or None."""
    try:
        from tools.record_event import append_event, generate_event_id

        event = {
            "v": 1,
            "id": generate_event_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "work_completed",
            "source": "iterate",
        }
        if commit:
            event["commit"] = commit
        session = os.environ.get("SHIPWRIGHT_SESSION_ID", "")
        if session:
            event["session"] = session

        return append_event(project_root, event)
    except Exception as exc:
        print(f"[finalize_iterate] event recording failed: {exc}", file=sys.stderr)
        return None


def _generate_handoff(project_root: Path, session_id: str, run_id: str, reason: str) -> str | None:
    """Generate session handoff with canon marker. Returns written path or None."""
    try:
        from tools.generate_session_handoff import generate_handoff

        canon_fm = {
            "run_id": run_id,
            "phase": "iterate",
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        content = generate_handoff(
            project_root, session_id,
            reason=reason,
            canon_frontmatter=canon_fm,
        )
        out_path = project_root / ".shipwright" / "agent_docs" / "session_handoff.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return str(out_path.relative_to(project_root))
    except Exception as exc:
        print(f"[finalize_iterate] handoff failed: {exc}", file=sys.stderr)
        return None


def run(
    project_root: Path,
    run_id: str,
    commit: str = "",
    reason: str = "iterate finalization",
) -> dict:
    """Run all finalization steps. Returns structured result dict."""
    session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "unknown")
    result: dict = {"steps": {}, "project_root": str(project_root)}

    dashboard_path = _update_dashboard(project_root, session_id, run_id)
    result["steps"]["dashboard"] = {"written": dashboard_path} if dashboard_path else {"skipped": True}

    compliance_paths = _update_compliance(project_root)
    result["steps"]["compliance"] = {"written": compliance_paths} if compliance_paths else {"skipped": True}

    if commit:
        event_id = _record_event(project_root, commit, run_id, reason)
        result["steps"]["event"] = {"id": event_id} if event_id else {"skipped": True}
    else:
        result["steps"]["event"] = {"skipped": True, "reason": "no --commit provided"}

    handoff_path = _generate_handoff(project_root, session_id, run_id, reason)
    result["steps"]["handoff"] = {"written": handoff_path} if handoff_path else {"skipped": True}

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize iterate run")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--run-id", required=True, help="Iterate run ID")
    parser.add_argument("--commit", default="", help="Final commit SHA (optional)")
    parser.add_argument("--reason", default="iterate finalization", help="Handoff reason")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    result = run(project_root, args.run_id, args.commit, args.reason)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
