"""Render a dry-run report of files that /shipwright-adopt would create."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProposedWrite:
    path: str  # relative POSIX
    action: str  # "create" | "modify" | "skip"
    reason: str = ""


@dataclass
class DryRunReport:
    writes: list[ProposedWrite] = field(default_factory=list)
    excluded_paths: list[str] = field(default_factory=list)
    commit_message: str = ""
    crawl_enabled: bool = False

    def render(self) -> str:
        creates = [w for w in self.writes if w.action == "create"]
        mods = [w for w in self.writes if w.action == "modify"]
        skips = [w for w in self.writes if w.action == "skip"]
        lines = [
            "=" * 80,
            "SHIPWRIGHT-ADOPT DRY RUN — NO FILES WILL BE WRITTEN",
            "=" * 80,
            "",
        ]
        lines.append(f"Files to be CREATED ({len(creates)}):")
        for w in creates:
            reason = f"  # {w.reason}" if w.reason else ""
            lines.append(f"  {w.path}{reason}")
        lines.append("")
        lines.append(f"Files to be MODIFIED ({len(mods)}):")
        for w in mods:
            reason = f"  # {w.reason}" if w.reason else ""
            lines.append(f"  {w.path}{reason}")
        if skips:
            lines.append("")
            lines.append(f"Writes SKIPPED ({len(skips)}):")
            for w in skips:
                lines.append(f"  {w.path}  # {w.reason or '—'}")
        lines.append("")
        if self.excluded_paths:
            lines.append(f"Paths IGNORED (nested projects): {', '.join(self.excluded_paths)}")
            lines.append("")
        lines.append(f"Playwright crawl: {'enabled' if self.crawl_enabled else 'disabled (AST fallback)'}")
        lines.append("")
        lines.append("Commit to be created:")
        for cm in self.commit_message.splitlines():
            lines.append(f"  {cm}")
        lines.append("")
        lines.append("To apply, re-run /shipwright-adopt without --dry-run.")
        lines.append("=" * 80)
        return "\n".join(lines)


def plan_standard_writes(
    project_root: Path,
    *,
    split_name: str,
    write_sync: bool,
    crawl_succeeded: bool,
    nested_excluded: list[str],
) -> DryRunReport:
    """Produce the canonical list of proposed writes for a standard adopt run."""
    writes: list[ProposedWrite] = [
        ProposedWrite("CLAUDE.md", "create", "project overview"),
        ProposedWrite(".shipwright/agent_docs/architecture.md", "create", "stack + layers + ASCII diagram"),
        ProposedWrite(".shipwright/agent_docs/conventions.md", "create", "linter/formatter/rules"),
        ProposedWrite(".shipwright/agent_docs/decision_log.md", "create", "adoption ADR (next-free 3-digit id) + retroactive ADRs"),
        ProposedWrite(".shipwright/agent_docs/build_dashboard.md", "create", "adoption snapshot"),
        ProposedWrite(f".shipwright/planning/{split_name}/spec.md", "create", "IREB spec from inferred features"),
        ProposedWrite(".shipwright/compliance/sbom.md", "create", "via shipwright-compliance"),
        ProposedWrite(".shipwright/compliance/change-history.md", "create", "via shipwright-compliance"),
        ProposedWrite(".shipwright/compliance/traceability-matrix.md", "create", "RTM skeleton"),
        ProposedWrite(".shipwright/compliance/test-evidence.md", "create", "stub — fills from first /shipwright-test"),
        ProposedWrite(".shipwright/compliance/dashboard.md", "create", "via shipwright-compliance"),
        ProposedWrite("shipwright_project_config.json", "create", "splits + requirements"),
        ProposedWrite("shipwright_plan_config.json", "create", "adopted, empty sections"),
        ProposedWrite("shipwright_build_config.json", "create", "adopted-baseline section"),
        ProposedWrite("shipwright_iterate_config.json", "create", "external_review.feedback_iterations=1, external_code_review.enabled=true"),
        ProposedWrite("shipwright_compliance_config.json", "create", "seeded_by_adopt=true"),
        ProposedWrite("shipwright_run_config.json", "create", "status=complete, written LAST"),
        ProposedWrite("shipwright_events.jsonl", "create", "1x adopted event + backfilled commits"),
        # NB: .claude/settings.json is NOT written — the suggest_iterate
        # UserPromptSubmit hook is plugin-owned (registered in
        # plugins/shipwright-iterate/hooks/hooks.json). Retired
        # 2026-05-05 per iterate-20260505-plugin-hook-registration.
    ]
    if write_sync:
        writes.append(ProposedWrite("shipwright_sync_config.json", "create", "empty file_to_fr_map"))
    if crawl_succeeded:
        writes.append(ProposedWrite("e2e/flows/adopted-baseline.spec.ts", "create", "Playwright regression guard"))
        writes.append(ProposedWrite(".shipwright/adopt/routes.json", "create", "crawler output"))
        writes.append(ProposedWrite(".shipwright/adopt/screenshots/", "create", "per-route screenshots"))
    writes.append(ProposedWrite(".shipwright/adopt/snapshot.json", "create", "Layer-1 detector output"))
    writes.append(ProposedWrite(".shipwright/adopt/enrichment.json", "create", "Layer-2 Claude-inline output"))
    writes.append(ProposedWrite(".shipwright/adopt/review.md", "create", "Layer-3 llm_review output or skip-reason"))
    commit_message = """chore(shipwright): adopt repository into Shipwright SDLC

Adopted via /shipwright-adopt. See .shipwright/agent_docs/decision_log.md
for the adoption ADR (id is the next-free 3-digit number; ADR-001 on a
greenfield log)."""
    return DryRunReport(
        writes=writes,
        excluded_paths=nested_excluded,
        commit_message=commit_message,
        crawl_enabled=crawl_succeeded,
    )
