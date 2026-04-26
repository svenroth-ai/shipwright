"""Verify setup_adopt's preflight reports pre-existing artifacts (3.2)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from checks.setup_adopt import run_preflight


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "init", "-q"], cwd=root, check=True)


def test_existing_artifacts_lists_all_relevant_paths(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
    (tmp_path / "agent_docs").mkdir()
    (tmp_path / "agent_docs" / "decision_log.md").write_text("# log\n", encoding="utf-8")
    (tmp_path / "agent_docs" / "architecture.md").write_text("# arch\n", encoding="utf-8")
    (tmp_path / ".shipwright" / "planning").mkdir(parents=True)
    (tmp_path / ".shipwright" / "planning" / "01-adopted").mkdir()
    (tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")

    report = run_preflight(tmp_path, [])
    artifacts = set(report.get("existing_artifacts", []))
    assert "CLAUDE.md" in artifacts
    assert "agent_docs/decision_log.md" in artifacts
    assert "agent_docs/architecture.md" in artifacts
    assert ".shipwright/planning/01-adopted/spec.md" in artifacts
    assert "shipwright_events.jsonl" in artifacts


def test_existing_artifacts_empty_for_clean_repo(tmp_path: Path) -> None:
    _git_init(tmp_path)
    report = run_preflight(tmp_path, [])
    assert report.get("existing_artifacts") == []


def test_existing_artifacts_list_does_not_break_ok_field(tmp_path: Path) -> None:
    """Pre-existing artifacts should NOT block adoption — they trigger a
    user prompt in the SKILL.md flow, not a hard-stop here."""
    _git_init(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
    report = run_preflight(tmp_path, [])
    assert report["ok"] is True
    assert report["existing_artifacts"] != []
