"""Unit tests for ci_detector.detect_ci."""

from pathlib import Path

from lib.ci_detector import detect_ci


def test_github_actions_detected(nextjs_repo: Path) -> None:
    ci = detect_ci(nextjs_repo)
    assert ci["provider"] == "github-actions"
    assert ".github/workflows/ci.yml" in ci["workflows"]


def test_no_ci(python_cli: Path) -> None:
    ci = detect_ci(python_cli)
    assert ci["provider"] is None
    assert ci["workflows"] == []


def test_empty_project(tmp_path: Path) -> None:
    assert detect_ci(tmp_path) == {"provider": None, "workflows": []}
