"""Commit Change Log generator.

Produces .shipwright/compliance/change-history.md from git conventional commits.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scripts.lib.mermaid import commit_type_pie

if TYPE_CHECKING:
    from scripts.lib.data_collector import CommitEntry, ComplianceData


# Display labels for commit types
_TYPE_LABELS = {
    "feat": "Features",
    "fix": "Fixes",
    "refactor": "Refactoring",
    "docs": "Documentation",
    "test": "Tests",
    "chore": "Chores",
    "style": "Style",
    "perf": "Performance",
    "ci": "CI/CD",
    "build": "Build",
    "other": "Other",
}


def generate(data: ComplianceData) -> str:
    """Generate Change History Report as Markdown string."""
    commits = data.commits

    lines = [
        "# Commit Change Log",
        "",
        f"Generated: {data.timestamp}",
        f"Total commits: {len(commits)}",
        "",
    ]

    if not commits:
        lines.append("_No commits found in git history._")
        return "\n".join(lines) + "\n"

    # Commit distribution
    lines.extend([
        "## Commit Distribution",
        "",
        commit_type_pie(commits),
        "",
    ])

    # Group by type
    grouped: dict[str, list[CommitEntry]] = {}
    for c in commits:
        grouped.setdefault(c.type, []).append(c)

    lines.append("## Changes by Type")
    lines.append("")

    for type_key, type_commits in sorted(grouped.items(), key=lambda x: -len(x[1])):
        label = _TYPE_LABELS.get(type_key, type_key.title())
        lines.extend([
            f"### {label} ({type_key}) — {len(type_commits)} commits",
            "",
            "| Date | Scope | Description | Commit |",
            "|------|-------|-------------|--------|",
        ])
        for c in type_commits:
            date = c.date[:10] if len(c.date) >= 10 else c.date
            scope = c.scope or "—"
            lines.append(f"| {date} | {scope} | {c.description} | {c.hash} |")
        lines.append("")

    # AI attribution
    ai_commits = sum(1 for c in commits if "Claude" in c.author or "claude" in c.author.lower())
    lines.extend([
        "## AI Attribution",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total commits | {len(commits)} |",
        f"| AI-assisted commits | {ai_commits} |",
        f"| Human-authored commits | {len(commits) - ai_commits} |",
        "",
    ])

    return "\n".join(lines) + "\n"


COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"


def generate_file(project_root: Path, data: ComplianceData | None = None) -> Path:
    """Generate Change History Report and write to .shipwright/compliance/change-history.md."""
    if data is None:
        from scripts.lib.data_collector import collect_all
        data = collect_all(project_root)

    output_dir = project_root / COMPLIANCE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "change-history.md"
    output_path.write_text(generate(data), encoding="utf-8")
    return output_path
