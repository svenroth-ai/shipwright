"""Generate session_handoff.md from current project state.

Reads git status, config files, and decision log to produce a
human-readable handoff document for session recovery.

Usage (from target project root):
    uv run <SHIPWRIGHT_PLUGIN_ROOT>/../../shared/scripts/tools/generate_session_handoff.py

Writes to: agent_docs/session_handoff.md
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add shared lib to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.config import read_all_configs, read_events
from lib.state import detect_current_phase, get_checkpoint


def get_git_info(project_root: Path) -> dict[str, str]:
    """Get current git state."""
    info = {}
    try:
        info["branch"] = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=project_root,
        ).stdout.strip()
        info["last_commit"] = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            capture_output=True, text=True, cwd=project_root,
        ).stdout.strip()
        info["uncommitted_changes"] = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=project_root,
        ).stdout.strip()
    except FileNotFoundError:
        info["error"] = "git not found"
    return info


def generate_handoff(
    project_root: str | Path,
    session_id: str = "unknown",
    reason: str = "context compaction",
) -> str:
    """Generate session handoff markdown content."""
    project_root = Path(project_root)
    configs = read_all_configs(project_root)
    checkpoint = get_checkpoint(project_root)
    git_info = get_git_info(project_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Read decision log if it exists
    decision_log = project_root / "agent_docs" / "decision_log.md"
    recent_decisions = ""
    if decision_log.exists():
        content = decision_log.read_text(encoding="utf-8")
        # Extract last ADR entry (supports both compact ### ADR- and old ## ADR- format)
        for prefix in ("\n### ADR-", "\n## ADR-"):
            entries = content.split(prefix)
            if len(entries) > 1:
                recent_decisions = prefix.lstrip("\n") + entries[-1][:500]
                break

    lines = [
        f"# Session Handoff",
        "",
        f"> Auto-generated {timestamp}",
        "",
        "## Session Info",
        "",
        f"- **Session ID**: {session_id}",
        f"- **Timestamp**: {timestamp}",
        f"- **Reason**: {reason}",
        "",
    ]

    # Iterate 11.3 — render "## Last Iterate" from run_config.iterate_history
    # when present. This is the section most users actually want after a
    # finalized iterate run; the legacy build checkpoint block below is kept
    # for full-pipeline recovery flows.
    run_cfg = configs.get("run") or {}
    iterate_history = run_cfg.get("iterate_history") or []
    if iterate_history:
        last = iterate_history[-1]
        lines += [
            "## Last Iterate",
            "",
            f"- **Run ID**: {last.get('run_id', 'N/A')}",
        ]
        if last.get("date"):
            lines.append(f"- **Date**: {last['date']}")
        if last.get("type"):
            lines.append(f"- **Type**: {last['type']}")
        if last.get("complexity"):
            lines.append(f"- **Complexity**: {last['complexity']}")
        if last.get("branch"):
            lines.append(f"- **Branch**: {last['branch']}")
        if last.get("adr_id"):
            lines.append(f"- **ADR**: {last['adr_id']}")
        if last.get("description"):
            lines.append(f"- **Description**: {last['description']}")
        if "tests_passed" in last:
            lines.append(f"- **Tests passed**: {last['tests_passed']}")
        if last.get("spec"):
            lines.append(f"- **Spec**: {last['spec']}")
        lines.append("")

    lines += [
        "## Legacy build state",
        "",
        f"- **Phase**: {checkpoint['phase']}",
        f"- **Current Split**: {checkpoint.get('current_split', 'N/A')}",
        f"- **Current Section**: {checkpoint.get('current_section', 'N/A')}",
        "",
    ]

    if checkpoint.get("total_splits"):
        lines.append(f"- **Splits**: {checkpoint['completed_splits']}/{checkpoint['total_splits']} complete")
    if checkpoint.get("total_sections"):
        lines.append(f"- **Sections**: {checkpoint['completed_sections']}/{checkpoint['total_sections']} complete")

    lines += [
        "",
        "## Git State",
        "",
        f"- **Branch**: {git_info.get('branch', 'N/A')}",
        f"- **Last Commit**: {git_info.get('last_commit', 'N/A')}",
        f"- **Uncommitted Changes**: {'Yes' if git_info.get('uncommitted_changes') else 'None'}",
        "",
        "## Config Files to Read",
        "",
    ]

    for skill, config in configs.items():
        if skill == "events":
            continue  # Listed separately below
        status = "exists" if config else "missing"
        lines.append(f"- `shipwright_{skill}_config.json` — {status}")

    # Event log section (if exists)
    events = read_events(project_root)
    if events:
        # Show last 5 events
        recent = events[-5:]
        lines += [
            "",
            "## Last Events",
            "",
            "| Event | Type | Source | Date |",
            "|-------|------|--------|------|",
        ]
        for e in reversed(recent):
            eid = e.get("id", "—")
            etype = e.get("type", "—")
            source = e.get("source", e.get("phase", "—"))
            if etype == "work_completed":
                source = f"{e.get('source', '—')} ({e.get('section', e.get('description', '—'))})"
            ts = e.get("ts", "—")[:10]
            lines.append(f"| {eid} | {etype} | {source} | {ts} |")

        # Summary
        work_events = [e for e in events if e.get("type") == "work_completed"]
        iterate_events = [e for e in work_events if e.get("source") == "iterate"]
        phase_completed = [e for e in events if e.get("type") == "phase_completed"]

        lines += [
            "",
            "## Recovery",
            "",
            f"- **Pipeline**: {len(phase_completed)} phases completed",
            f"- **Total work events**: {len(work_events)}",
        ]
        if iterate_events:
            last_iter = iterate_events[-1]
            lines.append(f"- **Last iterate**: {last_iter.get('intent', 'change')} — {last_iter.get('description', '—')} ({last_iter.get('ts', '')[:10]})")
        lines.append("- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline")
    else:
        # Legacy: config file listing only
        pass

    if recent_decisions:
        lines += [
            "",
            "## Recent Decisions",
            "",
            recent_decisions,
        ]

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Generate session_handoff.md from project state")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project directory (default: CWD). Iterate 11 added this so the "
        "iterate skill's F11 step writes to the right project instead of "
        "whatever directory the skill was invoked from.",
    )
    parser.add_argument(
        "--reason",
        default="context compaction",
        help="Why this handoff was generated (shown in the output)",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve() if args.project_root else Path(os.getcwd())
    session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "unknown")

    content = generate_handoff(project_root, session_id, args.reason)

    # Ensure agent_docs/ exists
    agent_docs = project_root / "agent_docs"
    agent_docs.mkdir(exist_ok=True)

    handoff_path = agent_docs / "session_handoff.md"
    handoff_path.write_text(content, encoding="utf-8")
    print(f"Session handoff written to {handoff_path}")


if __name__ == "__main__":
    main()
