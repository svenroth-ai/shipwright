"""Tests for browser_verify.py."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lib.browser_verify import run_browser_verify


def test_missing_verify_script(tmp_path):
    """No browser-verify.ts → error."""
    result = run_browser_verify(tmp_path)
    assert result["success"] is False
    assert "not found" in result["error"]


def test_parses_result_file(tmp_path):
    """Reads result from JSON file."""
    e2e = tmp_path / "e2e"
    e2e.mkdir()
    (e2e / "browser-verify.ts").write_text("// dummy")

    expected = {
        "success": True,
        "url": "http://localhost:3000",
        "screenshot": "e2e/screenshots/browser-verify.png",
        "console_errors": [],
        "title": "My App",
        "dom_snippet": "<html></html>",
    }
    result_file = tmp_path / "browser-verify-result.json"

    with patch("lib.browser_verify.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="{}", stderr="", returncode=0)
        # Simulate the TypeScript helper writing the result file
        result_file.write_text(json.dumps(expected))

        result = run_browser_verify(tmp_path)

    assert result["success"] is True
    assert result["title"] == "My App"
    assert result["console_errors"] == []


def test_handles_timeout(tmp_path):
    """Timeout → error result."""
    e2e = tmp_path / "e2e"
    e2e.mkdir()
    (e2e / "browser-verify.ts").write_text("// dummy")

    import subprocess
    with patch("lib.browser_verify.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 60)):
        result = run_browser_verify(tmp_path)

    assert result["success"] is False
    assert "timed out" in result["error"]


def test_parses_console_errors(tmp_path):
    """Console errors → success: false."""
    e2e = tmp_path / "e2e"
    e2e.mkdir()
    (e2e / "browser-verify.ts").write_text("// dummy")

    result_data = {
        "success": False,
        "url": "http://localhost:3000",
        "screenshot": "e2e/screenshots/browser-verify.png",
        "console_errors": ["ReferenceError: foo is not defined"],
        "title": "My App",
        "dom_snippet": "<html></html>",
    }
    result_file = tmp_path / "browser-verify-result.json"

    with patch("lib.browser_verify.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="{}", stderr="", returncode=1)
        result_file.write_text(json.dumps(result_data))

        result = run_browser_verify(tmp_path)

    assert result["success"] is False
    assert len(result["console_errors"]) == 1
