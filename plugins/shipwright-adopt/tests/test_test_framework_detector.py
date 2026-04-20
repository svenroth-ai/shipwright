"""Unit tests for test_framework_detector.detect_test_frameworks."""

from pathlib import Path

from lib.test_framework_detector import detect_test_frameworks


def test_nextjs_vitest_playwright(nextjs_repo: Path) -> None:
    fw = detect_test_frameworks(nextjs_repo)
    assert fw["unit"] is not None
    assert fw["unit"]["framework"] == "vitest"
    assert fw["e2e"] is not None
    assert fw["e2e"]["framework"] == "playwright"
    assert fw["coverage_tool"] == "vitest-coverage"


def test_python_pytest(python_cli: Path) -> None:
    fw = detect_test_frameworks(python_cli)
    assert fw["unit"] is not None
    assert fw["unit"]["framework"] == "pytest"
    assert fw["coverage_tool"] == "coverage.py"


def test_empty_project(tmp_path: Path) -> None:
    fw = detect_test_frameworks(tmp_path)
    assert fw["unit"] is None
    assert fw["e2e"] is None
