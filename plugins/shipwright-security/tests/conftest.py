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


# ---------------------------------------------------------------------------
# Leak guard — runs AFTER the whole session, not as a test
# ---------------------------------------------------------------------------

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# Written by the triage store. None is gitignored under the plugin, so a later
# `git add -A` commits them: fixture findings that read as real security
# findings, plus a `.lock` of exactly the shape that later causes merge
# conflicts. Happened twice in one session (PRs #446, #461).
_LEAK_PATHS = (
    PLUGIN_ROOT / ".shipwright" / "triage.jsonl",
    PLUGIN_ROOT / ".shipwright" / "triage.jsonl.lock",
    PLUGIN_ROOT / ".shipwright" / "triage.outbox.jsonl",
)


def pytest_sessionfinish(session, exitstatus):
    """Fail the session if any test wrote a triage store into the plugin dir.

    A HOOK, not a test, and deliberately so: the first attempt at this guard
    was an ordinary test module, which pytest ran alphabetically BEFORE the
    module that leaks — it passed while the leak was reintroduced, proving
    nothing. Only `sessionfinish` sees the end state regardless of ordering.

    Cause when it fires: a test drives a producer whose `--project-root`
    defaults to `"."`. Pass `tmp_path`; do not gitignore the symptom.
    """
    leaked = [p for p in _LEAK_PATHS if p.exists()]
    if not leaked:
        return
    names = ", ".join(str(p.relative_to(PLUGIN_ROOT)) for p in leaked)
    print(
        "\n[leak-guard] the test suite wrote a triage store into the plugin "
        f"directory: {names}\n"
        "[leak-guard] a test is driving a producer without an isolated "
        "--project-root (its default is '.'). Pass tmp_path."
    )
    session.exitstatus = 1
