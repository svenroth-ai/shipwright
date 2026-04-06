"""Test fixtures for shipwright-security."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_aikido_response() -> list[dict]:
    """Load sample Aikido API response."""
    return json.loads((FIXTURES_DIR / "sample_aikido_response.json").read_text())


@pytest.fixture
def sample_fixable_findings() -> dict:
    """Load sample findings with expected classifications."""
    return json.loads((FIXTURES_DIR / "sample_fixable_findings.json").read_text())


@pytest.fixture
def sample_semgrep_output() -> dict:
    """Load sample Semgrep JSON output."""
    return json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())


@pytest.fixture
def sample_trivy_output() -> dict:
    """Load sample Trivy JSON output."""
    return json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())


@pytest.fixture
def sample_gitleaks_output() -> list:
    """Load sample Gitleaks JSON output."""
    return json.loads((FIXTURES_DIR / "sample_gitleaks_output.json").read_text())
