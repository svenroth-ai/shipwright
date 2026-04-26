"""Tests for `shared/scripts/tools/print_next_migration_prompt.py`.

The helper inspects ``ARTIFACT_MIGRATIONS`` and prints a kickoff prompt
for the next pending/in_progress artifact, OR a "all done" message.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "shared" / "scripts" / "tools" / "print_next_migration_prompt.py"


def _import_tool():
    spec = importlib.util.spec_from_file_location(
        "print_next_migration_prompt_under_test", TOOL_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tool():
    return _import_tool()


def _fake_migration(name: str, status: str) -> dict:
    return {
        "name": name,
        "canonical": f".shipwright/{name}",
        "legacy_dirname": name,
        "old_path_patterns": [],
        "ast_check_string": name,
        "status": status,
        "started": "2026-04-27",
    }


class TestRenderPrompt:
    def test_pending_after_one_migrated_emits_next_prompt(self, tool):
        manifest = [
            _fake_migration("planning", "migrated"),
            _fake_migration("agent_docs", "pending"),
            _fake_migration("compliance", "pending"),
        ]
        out = tool.render_prompt(manifest)
        assert "agent_docs" in out
        assert ".shipwright/agent_docs" in out
        assert "planning" in out  # mentions just-completed
        # mentions queue tail
        assert "compliance" in out

    def test_in_progress_takes_precedence(self, tool):
        """If an in_progress migration exists, it's the next-up one."""
        manifest = [
            _fake_migration("planning", "migrated"),
            _fake_migration("agent_docs", "in_progress"),
            _fake_migration("compliance", "pending"),
        ]
        out = tool.render_prompt(manifest)
        assert "agent_docs" in out
        assert "in progress" in out.lower() or "in_progress" in out.lower()

    def test_all_migrated_says_done(self, tool):
        manifest = [
            _fake_migration("planning", "migrated"),
            _fake_migration("agent_docs", "migrated"),
        ]
        out = tool.render_prompt(manifest)
        assert "complete" in out.lower() or "done" in out.lower() or "nothing" in out.lower()
        assert "next" not in out.lower() or "no" in out.lower()

    def test_only_pending_no_migrated_yet(self, tool):
        manifest = [
            _fake_migration("planning", "pending"),
            _fake_migration("agent_docs", "pending"),
        ]
        out = tool.render_prompt(manifest)
        assert "planning" in out
        # No "just completed" line because nothing has been migrated yet
        # (the helper should still produce a sensible prompt)
        assert ".shipwright/planning" in out


class TestCli:
    def test_cli_with_real_manifest_runs(self, tool, capsys):
        """Smoke test: invoking main() with the real manifest must not crash."""
        rc = tool.main([])
        captured = capsys.readouterr()
        assert rc == 0
        # We're mid-migration so there's content
        assert captured.out.strip() != ""
