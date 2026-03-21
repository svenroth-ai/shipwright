"""Tests for rollback module (argument validation only, API calls mocked)."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "lib" / "rollback.py")


def test_git_strategy_requires_target_ref():
    """Git strategy without --target-ref should fail."""
    result = subprocess.run(
        [sys.executable, SCRIPT,
         "--env-name", "test-env",
         "--strategy", "git"],
        capture_output=True, text=True, encoding="utf-8",
    )
    output = json.loads(result.stdout)
    assert output["success"] is False
    assert "target-ref" in output["error"]


def test_clone_strategy_requires_clone_name():
    """Clone strategy without --clone-name should fail."""
    result = subprocess.run(
        [sys.executable, SCRIPT,
         "--env-name", "test-env",
         "--strategy", "clone"],
        capture_output=True, text=True, encoding="utf-8",
    )
    output = json.loads(result.stdout)
    assert output["success"] is False
    assert "clone-name" in output["error"]
