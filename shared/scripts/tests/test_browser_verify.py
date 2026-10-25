"""Tests for browser_verify.py."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from browser_verify import run_browser_verify


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

    with patch("browser_verify.subprocess.run") as mock_run:
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
    with patch("browser_verify.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 60)):
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

    with patch("browser_verify.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="{}", stderr="", returncode=1)
        result_file.write_text(json.dumps(result_data))

        result = run_browser_verify(tmp_path)

    assert result["success"] is False
    assert len(result["console_errors"]) == 1


@pytest.mark.covers("FR-01.05")
def test_resolves_npx_via_resolver(tmp_path, monkeypatch):
    """Windows-style npx.cmd: argv[0] is the resolved path, no shell."""
    import browser_verify

    e2e = tmp_path / "e2e"
    e2e.mkdir()
    (e2e / "browser-verify.ts").write_text("// dummy")
    monkeypatch.setattr(browser_verify, "resolve_executable", lambda name: f"C:/node/{name}.cmd")
    with patch("browser_verify.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_browser_verify(tmp_path, url="http://127.0.0.1:3900")
    argv = mock_run.call_args.args[0]
    assert argv[0] == "C:/node/npx.cmd"
    assert argv[1] == "tsx"
    assert "http://127.0.0.1:3900" in argv
    assert not mock_run.call_args.kwargs.get("shell")


@pytest.mark.covers("FR-01.05")
def test_module_adds_its_own_dir_to_sys_path_when_missing(monkeypatch):
    import importlib.util

    import browser_verify

    here = str(Path(browser_verify.__file__).resolve().parent)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != here])
    spec = importlib.util.spec_from_file_location("_browser_verify_fresh", browser_verify.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert sys.path[0] == here
    assert callable(module.resolve_executable)
