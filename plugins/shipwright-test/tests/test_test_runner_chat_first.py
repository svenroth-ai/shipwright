"""The test runner drives the bundled `chat-first-json` profile (brief unit B4)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.test_runner import get_test_command

pytestmark = pytest.mark.covers("FR-01.06")

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lib" / "test_runner.py"


def test_chat_first_unit_is_pytest_and_e2e_is_playwright():
    assert get_test_command("chat-first-json", "unit") == "uv run pytest"
    assert get_test_command("chat-first-json", "e2e") == "npx playwright test"


def test_chat_first_undeclared_layers_are_skipped_with_a_reason(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--profile", "chat-first-json", "--layer", "pgtap",
         "--cwd", str(tmp_path)], capture_output=True, text=True, timeout=60)
    out = json.loads(proc.stdout)
    assert proc.returncode == 0 and out["skipped"] is True
    assert out["command"] == "skipped" and out["total"] == 0  # no default command ran
    assert "chat-first-json" in out["skip_reason"] and out["profile_source"] == "bundled"
