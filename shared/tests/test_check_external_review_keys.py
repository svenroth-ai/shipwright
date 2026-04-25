"""Tests for shared/scripts/checks/check-external-review-keys.py."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "checks"
    / "check-external-review-keys.py"
)


def run_check(env_overrides: dict, cwd: str) -> dict:
    env = os.environ.copy()
    for k, v in env_overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    result = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=cwd,
    )
    return json.loads(result.stdout)


_CLEAN = {
    "OPENROUTER_API_KEY": None,
    "GEMINI_API_KEY": None,
    "GOOGLE_API_KEY": None,
    "OPENAI_API_KEY": None,
}


def test_check_reports_missing_when_no_keys(tmp_path):
    out = run_check(_CLEAN, cwd=str(tmp_path))
    assert out["available"] is False
    assert out["status"] == "missing_keys"
    assert out["providers"]["openrouter"] is False
    assert out["providers"]["gemini"] is False
    assert out["providers"]["openai"] is False


def test_check_reports_available_with_openrouter(tmp_path):
    out = run_check({**_CLEAN, "OPENROUTER_API_KEY": "sk-or-test-123"}, cwd=str(tmp_path))
    assert out["available"] is True
    assert out["status"] == "available"
    assert out["providers"]["openrouter"] is True


def test_check_reports_available_with_gemini_direct(tmp_path):
    out = run_check({**_CLEAN, "GEMINI_API_KEY": "AI-test-123"}, cwd=str(tmp_path))
    assert out["available"] is True
    assert out["status"] == "available"
    assert out["providers"]["gemini"] is True


def test_check_reports_available_with_openai_direct(tmp_path):
    out = run_check({**_CLEAN, "OPENAI_API_KEY": "sk-openai-test-123"}, cwd=str(tmp_path))
    assert out["available"] is True
    assert out["status"] == "available"
    assert out["providers"]["openai"] is True
