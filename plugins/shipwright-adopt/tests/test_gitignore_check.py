"""Verify gitignore_check classifies adopt's output paths against .gitignore."""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.gitignore_check import check_paths_against_gitignore


_AGENT_DOCS_PREFIX = ".shipwright/agent_docs"


def _git_init(root: Path, gitignore: str = "") -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    if gitignore:
        (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "init", "-q"], cwd=root, check=True)


def test_no_gitignore_returns_empty_gitignored(tmp_path: Path) -> None:
    _git_init(tmp_path)
    result = check_paths_against_gitignore(tmp_path, [
        "CLAUDE.md", f"{_AGENT_DOCS_PREFIX}/decision_log.md", "shipwright_run_config.json",
    ])
    assert result["total"] == 3
    assert result["gitignored"] == []


def test_gitignored_paths_are_flagged(tmp_path: Path) -> None:
    _git_init(tmp_path, ".shipwright/\nshipwright_*.json\n")
    result = check_paths_against_gitignore(tmp_path, [
        "CLAUDE.md",
        f"{_AGENT_DOCS_PREFIX}/decision_log.md",
        f"{_AGENT_DOCS_PREFIX}/architecture.md",
        "shipwright_run_config.json",
    ])
    assert result["total"] == 4
    assert f"{_AGENT_DOCS_PREFIX}/decision_log.md" in result["gitignored"]
    assert f"{_AGENT_DOCS_PREFIX}/architecture.md" in result["gitignored"]
    assert "shipwright_run_config.json" in result["gitignored"]
    assert "CLAUDE.md" not in result["gitignored"]


def test_majority_gitignored_flag(tmp_path: Path) -> None:
    """If 50%+ of outputs are gitignored, the result carries a `majority_gitignored` flag."""
    _git_init(tmp_path, ".shipwright/\nshipwright_*.json\n")
    result = check_paths_against_gitignore(tmp_path, [
        "CLAUDE.md",
        f"{_AGENT_DOCS_PREFIX}/decision_log.md",
        f"{_AGENT_DOCS_PREFIX}/architecture.md",
        f"{_AGENT_DOCS_PREFIX}/conventions.md",
        "shipwright_run_config.json",
        "shipwright_project_config.json",
        ".shipwright/planning/01-adopted/spec.md",
    ])
    assert result["total"] == 7
    assert len(result["gitignored"]) >= 4  # 6/7 actually
    assert result["majority_gitignored"] is True


def test_minority_gitignored_no_flag(tmp_path: Path) -> None:
    _git_init(tmp_path, "shipwright_*.json\n")
    result = check_paths_against_gitignore(tmp_path, [
        "CLAUDE.md",
        f"{_AGENT_DOCS_PREFIX}/decision_log.md",
        f"{_AGENT_DOCS_PREFIX}/architecture.md",
        f"{_AGENT_DOCS_PREFIX}/conventions.md",
        f"{_AGENT_DOCS_PREFIX}/build_dashboard.md",
        "shipwright_run_config.json",
    ])
    assert result["majority_gitignored"] is False
