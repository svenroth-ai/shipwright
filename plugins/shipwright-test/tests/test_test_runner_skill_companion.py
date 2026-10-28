"""The test runner drives the bundled `skill-companion-app` profile (campaign e2e-run-findings, E2)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.test_runner import get_test_command

pytestmark = pytest.mark.covers("FR-01.06")


def test_skill_companion_unit_is_pytest_and_e2e_is_playwright():
    assert get_test_command("skill-companion-app", "unit") == "uv run pytest"
    assert get_test_command("skill-companion-app", "e2e") == "npx playwright test"
