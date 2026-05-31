"""Tests for playwright_runner.py."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
from playwright_runner import parse_playwright_json, run_playwright


@pytest.fixture
def sample_results(tmp_path):
    """Create a sample Playwright JSON results file."""
    data = {
        "suites": [
            {
                "title": "auth.spec.ts",
                "file": "e2e/auth.spec.ts",
                "specs": [
                    {
                        "title": "should login",
                        "file": "e2e/auth.spec.ts",
                        "tests": [
                            {"results": [{"status": "passed"}]}
                        ],
                    },
                    {
                        "title": "should logout",
                        "file": "e2e/auth.spec.ts",
                        "tests": [
                            {"results": [{"status": "passed"}]}
                        ],
                    },
                ],
                "suites": [],
            }
        ],
        "stats": {"duration": 5000},
    }
    path = tmp_path / "e2e-results.json"
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def failing_results(tmp_path):
    """Create results with a failure."""
    data = {
        "suites": [
            {
                "title": "dashboard.spec.ts",
                "file": "e2e/dashboard.spec.ts",
                "specs": [
                    {
                        "title": "should show charts",
                        "file": "e2e/dashboard.spec.ts",
                        "tests": [
                            {
                                "results": [
                                    {
                                        "status": "failed",
                                        "error": {"message": "Element not found: .chart-container"},
                                    }
                                ]
                            }
                        ],
                    },
                ],
                "suites": [],
            }
        ],
        "stats": {"duration": 3000},
    }
    path = tmp_path / "e2e-results.json"
    path.write_text(json.dumps(data))
    return path


def test_parse_all_passed(sample_results):
    result = parse_playwright_json(sample_results)
    assert result["parsed"] is True
    assert result["passed"] == 2
    assert result["failed"] == 0
    assert result["total"] == 2


def test_parse_with_failure(failing_results):
    result = parse_playwright_json(failing_results)
    assert result["parsed"] is True
    assert result["failed"] == 1
    assert len(result["failures"]) == 1
    assert "chart-container" in result["failures"][0]["error"]


def test_parse_missing_file(tmp_path):
    result = parse_playwright_json(tmp_path / "nonexistent.json")
    assert result["parsed"] is False


def test_run_playwright_timeout(tmp_path):
    import subprocess
    with patch("playwright_runner.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 300)):
        result = run_playwright(tmp_path)
    assert result["success"] is False
    assert "timed out" in result["error"]


@patch("playwright_runner.subprocess.run")
def test_run_playwright_success(mock_run, tmp_path):
    # Create results file directly in tmp_path (simulating Playwright output)
    data = {
        "suites": [{"title": "test", "file": "e2e/test.spec.ts", "specs": [
            {"title": "works", "file": "e2e/test.spec.ts", "tests": [
                {"results": [{"status": "passed"}]}
            ]}
        ], "suites": []}],
        "stats": {"duration": 1000},
    }
    # run_playwright deletes old results first, so we write after the mock call
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    # Patch to write results after subprocess.run is called
    def write_results_then_return(*args, **kwargs):
        (tmp_path / "e2e-results.json").write_text(json.dumps(data))
        return MagicMock(returncode=0, stdout="", stderr="")
    mock_run.side_effect = write_results_then_return

    result = run_playwright(tmp_path)
    assert result["success"] is True
    assert result["passed"] == 1
