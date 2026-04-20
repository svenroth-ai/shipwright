"""Unit tests for convention_detector.detect_conventions."""

from pathlib import Path

from lib.convention_detector import detect_conventions


def test_nextjs_conventions(nextjs_repo: Path) -> None:
    conv = detect_conventions(nextjs_repo)
    assert conv["linter"] == "eslint-legacy"
    assert conv["formatter"] == "prettier"
    assert conv["tsconfig_strict"] is True
    assert conv["typescript"] is True


def test_python_cli_ruff(python_cli: Path) -> None:
    conv = detect_conventions(python_cli)
    assert conv["python_style"] == "ruff"
    assert conv["linter"] == "ruff"


def test_empty_project(tmp_path: Path) -> None:
    conv = detect_conventions(tmp_path)
    assert conv["linter"] is None
    assert conv["formatter"] is None
    assert conv["tsconfig_strict"] is False
