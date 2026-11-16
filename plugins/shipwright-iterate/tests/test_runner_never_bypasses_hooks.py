"""The sub-iterate runner contract forbids bypassing git hooks, in plain words."""

from pathlib import Path

import pytest

_RUNNER = Path(__file__).resolve().parents[1] / "agents" / "sub-iterate-runner.md"


@pytest.mark.covers("FR-01.01/AC38")
def test_runner_contract_forbids_every_hook_bypass():
    text = _RUNNER.read_text(encoding="utf-8")
    assert "Never bypass git hooks" in text
    for needle in ("--no-verify", "core.hooksPath", "environment variable that disables them", "HUSKY=0", "GIT_CONFIG_"):
        assert needle in text, needle
