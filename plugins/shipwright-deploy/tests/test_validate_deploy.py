"""Tests for validate-deploy.py."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "checks" / "validate-deploy.py")


def run_validate(env: dict = None) -> dict:
    """Run validate-deploy.py with optional env overrides."""
    import os
    test_env = os.environ.copy()
    if env:
        test_env.update(env)

    result = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True, text=True, encoding="utf-8",
        env=test_env,
    )
    return json.loads(result.stdout)


def test_validate_with_token(monkeypatch):
    monkeypatch.setenv("JELASTIC_TOKEN", "test-token")
    output = run_validate({"JELASTIC_TOKEN": "test-token"})
    assert output["success"] is True
    assert output["jelastic_token"] is True


def test_validate_without_token(monkeypatch):
    monkeypatch.delenv("JELASTIC_TOKEN", raising=False)
    import os
    env = os.environ.copy()
    env.pop("JELASTIC_TOKEN", None)

    result = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True, text=True, encoding="utf-8",
        env=env,
    )
    output = json.loads(result.stdout)
    assert output["success"] is False
    assert output["jelastic_token"] is False
    assert any("JELASTIC_TOKEN" in w for w in output["warnings"])


def test_validate_result_structure(monkeypatch):
    monkeypatch.setenv("JELASTIC_TOKEN", "test")
    output = run_validate({"JELASTIC_TOKEN": "test"})
    assert "success" in output
    assert "jelastic_token" in output
    assert "supabase_token" in output
    assert "git_remote" in output
    assert "warnings" in output
