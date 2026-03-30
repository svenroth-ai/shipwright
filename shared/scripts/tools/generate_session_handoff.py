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

from lib.config import read_all_configs
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
        "## Current State",
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
        status = "exists" if config else "missing"
        lines.append(f"- `shipwright_{skill}_config.json` — {status}")

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
    import os

    project_root = Path(os.getcwd())
    session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "unknown")

    reason = sys.argv[1] if len(sys.argv) > 1 else "context compaction"

    content = generate_handoff(project_root, session_id, reason)

    # Ensure agent_docs/ exists
    agent_docs = project_root / "agent_docs"
    agent_docs.mkdir(exist_ok=True)

    handoff_path = agent_docs / "session_handoff.md"
    handoff_path.write_text(content, encoding="utf-8")
    print(f"Session handoff written to {handoff_path}")


if __name__ == "__main__":
    main()
