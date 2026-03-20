"""Append a decision entry to agent_docs/decision_log.md.

Auto-numbers entries sequentially and auto-dates with today's date.
Never overwrites existing entries — always appends.

Usage (from target project root):
    uv run <path>/write_decision_log.py --section "Section 03: Auth" --commit abc1234 \
        --context "Code review found session-based auth" \
        --decision "Keep JWT, refresh 7 days" \
        --consequences "Stateless for scaling" \
        --rejected "Session cookies, OAuth-only"
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path


def get_next_adr_number(content: str) -> int:
    """Extract the highest ADR number and return next."""
    numbers = re.findall(r"## ADR-(\d+)", content)
    if not numbers:
        return 1
    return max(int(n) for n in numbers) + 1


def format_entry(
    number: int,
    section_ref: str,
    commit_hash: str,
    context: str,
    decision: str,
    consequences: str,
    rejected: str = "",
    status: str = "Accepted",
) -> str:
    """Format a single ADR entry."""
    today = date.today().isoformat()

    lines = [
        "",
        "---",
        "",
        f"## ADR-{number:03d} | {today} | {section_ref} | Commit {commit_hash}",
        "",
        f"### Status: {status}",
        "",
        "### Context",
        context,
        "",
        "### Decision",
        decision,
        "",
        "### Consequences",
        f"- {consequences}",
    ]

    if rejected:
        lines.append(f"- Alternatives rejected: {rejected}")

    lines.append("")
    return "\n".join(lines)


def append_decision(
    project_root: str | Path,
    section_ref: str,
    commit_hash: str,
    context: str,
    decision: str,
    consequences: str,
    rejected: str = "",
    status: str = "Accepted",
) -> int:
    """Append a decision entry to the decision log. Returns the ADR number."""
    project_root = Path(project_root)
    log_path = project_root / "agent_docs" / "decision_log.md"

    # Ensure agent_docs/ exists
    log_path.parent.mkdir(exist_ok=True)

    # Read existing or create header
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
    else:
        content = "# Decision Log\n\n> Project-specific decisions only. Profile-level decisions are implicit in the stack profile.\n"

    number = get_next_adr_number(content)
    entry = format_entry(number, section_ref, commit_hash, context, decision, consequences, rejected, status)
    content += entry

    log_path.write_text(content, encoding="utf-8")
    return number


def main() -> None:
    """CLI entry point."""
    import os

    parser = argparse.ArgumentParser(description="Append a decision to the decision log")
    parser.add_argument("--section", required=True, help="Section reference (e.g. 'Section 03: Auth')")
    parser.add_argument("--commit", required=True, help="Commit hash")
    parser.add_argument("--context", required=True, help="Context/background for the decision")
    parser.add_argument("--decision", required=True, help="The decision made")
    parser.add_argument("--consequences", required=True, help="Consequences of the decision")
    parser.add_argument("--rejected", default="", help="Rejected alternatives")
    parser.add_argument("--status", default="Accepted", help="Status (default: Accepted)")
    args = parser.parse_args()

    project_root = Path(os.getcwd())
    number = append_decision(
        project_root,
        section_ref=args.section,
        commit_hash=args.commit,
        context=args.context,
        decision=args.decision,
        consequences=args.consequences,
        rejected=args.rejected,
        status=args.status,
    )
    print(f"ADR-{number:03d} appended to agent_docs/decision_log.md")


if __name__ == "__main__":
    main()
