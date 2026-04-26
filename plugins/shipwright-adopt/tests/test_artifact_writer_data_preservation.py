"""Verify artifact_writer never silently destroys load-bearing user files
(sub-iterate C).

This is the core fix: an adoption run lost a 16 KB CLAUDE.md and 137 KB
decision_log.md to the thin scaffold without warning. After this iterate,
load-bearing CLAUDE.md is preserved and the suggested adopt content goes
to a side file; decision_log.md is auto-merged to keep historical ADRs.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.artifact_writer import write_agent_docs, write_claude_md


_BIG_CLAUDE = "# My App\n\n" + ("This is load-bearing prose. " * 200)
_RICH_DECISION_LOG = (
    "# Decision Log — original\n\n"
    "## ADR-0001: Use Postgres\n\n"
    "- Status: accepted\n- Date: 2026-01-01\n\n"
    "Long-standing core decision.\n\n---\n\n"
    "## ADR-0007: Sentry for errors\n\n"
    "- Status: accepted\n- Date: 2026-02-15\n\nDecision body.\n\n---\n\n"
    "## ADR-0042: Migrate jobs to NATS\n\n"
    "- Status: accepted\n- Date: 2026-04-01\n\nMigration plan.\n\n---\n"
)


def test_write_claude_md_preserves_loadbearing_existing(tmp_path: Path) -> None:
    """If CLAUDE.md > threshold, do NOT overwrite — write to side-file
    `.shipwright/adopt/CLAUDE.md.adopt-suggested` instead."""
    existing = tmp_path / "CLAUDE.md"
    existing.write_text(_BIG_CLAUDE, encoding="utf-8")
    write_claude_md(
        tmp_path,
        project_name="Demo",
        profile="vite-hono",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        commands={"build": "npm run build", "test": "vitest", "dev": "npm run dev"},
        product_description="adopt-generated description",
    )
    # Existing CLAUDE.md untouched
    assert existing.read_text(encoding="utf-8") == _BIG_CLAUDE
    # Backup written
    backup = tmp_path / ".shipwright" / "adopt" / "backups" / "CLAUDE.md.preserved"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == _BIG_CLAUDE
    # Suggested side-file written
    suggested = tmp_path / ".shipwright" / "adopt" / "CLAUDE.md.adopt-suggested"
    assert suggested.exists()
    assert "adopt-generated description" in suggested.read_text(encoding="utf-8")


def test_write_claude_md_overwrites_thin_existing(tmp_path: Path) -> None:
    """A tiny CLAUDE.md (e.g. previous adopt scaffold) is treated as
    non-load-bearing and overwritten — but a backup is still made."""
    existing = tmp_path / "CLAUDE.md"
    existing.write_text("# placeholder\n", encoding="utf-8")
    write_claude_md(
        tmp_path,
        project_name="Demo",
        profile="vite-hono",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        commands={"build": "x", "test": "x", "dev": "x"},
        product_description="new content",
    )
    body = existing.read_text(encoding="utf-8")
    assert "new content" in body
    backup = tmp_path / ".shipwright" / "adopt" / "backups" / "CLAUDE.md.preserved"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "# placeholder\n"


def test_write_claude_md_no_backup_when_absent(tmp_path: Path) -> None:
    """First-time adopt — no existing file, no backup needed, writes fresh."""
    write_claude_md(
        tmp_path,
        project_name="Demo", profile="vite-hono",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        commands={"build": "x", "test": "x", "dev": "x"},
        product_description="fresh",
    )
    assert (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / ".shipwright" / "adopt" / "backups" / "CLAUDE.md.preserved").exists()


def test_write_agent_docs_preserves_existing_decision_log_with_merge(tmp_path: Path) -> None:
    """Existing rich decision_log.md must be merged, not overwritten.
    All historical ADRs preserved verbatim."""
    agent_docs = tmp_path / "agent_docs"
    agent_docs.mkdir()
    (agent_docs / "decision_log.md").write_text(_RICH_DECISION_LOG, encoding="utf-8")

    write_agent_docs(
        tmp_path,
        project_name="Demo", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```\n(diag)\n```",
        data_flow_description="flow",
        conventions={"linter": "eslint", "formatter": "prettier"},
        conventions_prose="conventions prose",
        features_count=5, commits_total=200, contributors_total=3,
        nested_excluded=[], commit_sha="abc",
        retroactive_adrs=[],
    )
    merged = (agent_docs / "decision_log.md").read_text(encoding="utf-8")
    # All three historical ADR titles must appear
    assert "Use Postgres" in merged
    assert "Sentry for errors" in merged
    assert "Migrate jobs to NATS" in merged
    # New adoption ADR also present
    assert "Adopt this repository" in merged
    # Backup of original written
    backup = tmp_path / ".shipwright" / "adopt" / "backups" / "agent_docs" / "decision_log.md.preserved"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == _RICH_DECISION_LOG


def test_write_agent_docs_preserves_then_overwrites_other_docs(tmp_path: Path) -> None:
    """architecture.md / conventions.md are backed up but overwritten —
    less load-bearing, easy to recover from .preserved."""
    agent_docs = tmp_path / "agent_docs"
    agent_docs.mkdir()
    (agent_docs / "architecture.md").write_text("OLD ARCH", encoding="utf-8")
    (agent_docs / "conventions.md").write_text("OLD CONV", encoding="utf-8")
    write_agent_docs(
        tmp_path,
        project_name="Demo", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[{"name": "presentation", "paths": ["src/app"]}],
        loc_by_layer={"presentation": 1000},
        architecture_diagram="```\n(diag)\n```",
        data_flow_description="flow",
        conventions={"linter": "eslint", "formatter": "prettier"},
        conventions_prose="new conv prose",
        features_count=3, commits_total=50, contributors_total=2,
        nested_excluded=[], commit_sha="abc",
        retroactive_adrs=[],
    )
    arch_body = (agent_docs / "architecture.md").read_text(encoding="utf-8")
    conv_body = (agent_docs / "conventions.md").read_text(encoding="utf-8")
    assert "OLD ARCH" not in arch_body
    assert "OLD CONV" not in conv_body
    assert "presentation" in arch_body  # new content present
    # Backups
    arch_backup = tmp_path / ".shipwright" / "adopt" / "backups" / "agent_docs" / "architecture.md.preserved"
    conv_backup = tmp_path / ".shipwright" / "adopt" / "backups" / "agent_docs" / "conventions.md.preserved"
    assert arch_backup.read_text(encoding="utf-8") == "OLD ARCH"
    assert conv_backup.read_text(encoding="utf-8") == "OLD CONV"


def test_write_agent_docs_preservation_log_records_actions(tmp_path: Path) -> None:
    """A machine-readable summary lands in
    `.shipwright/adopt/preservation_log.json` so the handoff and validator
    can surface what happened."""
    agent_docs = tmp_path / "agent_docs"
    agent_docs.mkdir()
    (agent_docs / "decision_log.md").write_text(_RICH_DECISION_LOG, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(_BIG_CLAUDE, encoding="utf-8")

    write_claude_md(
        tmp_path,
        project_name="Demo", profile="vite-hono",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        commands={"build": "x", "test": "x", "dev": "x"},
        product_description="new",
    )
    write_agent_docs(
        tmp_path,
        project_name="Demo", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```\n```", data_flow_description="",
        conventions={}, conventions_prose="",
        features_count=0, commits_total=200, contributors_total=1,
        nested_excluded=[], commit_sha=None, retroactive_adrs=[],
    )
    log_path = tmp_path / ".shipwright" / "adopt" / "preservation_log.json"
    assert log_path.exists()
    log = json.loads(log_path.read_text(encoding="utf-8"))
    by_file = {e["file"]: e for e in log["entries"]}
    assert by_file["CLAUDE.md"]["action"] == "skipped_loadbearing"
    assert by_file["agent_docs/decision_log.md"]["action"] == "merged"
