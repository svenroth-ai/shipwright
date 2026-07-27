"""Test fixtures for shipwright-security."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PLUGIN_ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _no_source_tree_pollution():
    """Fail any test that writes ``.shipwright/`` into the plugin source tree.

    Several entry points take a ``--project-root`` that DEFAULTS to ``"."`` and
    then write under it — ``generate_security_report.main()`` mirrors findings
    into ``<project_root>/.shipwright/triage.jsonl``. The plugin's own pytest
    session runs with the CWD set to the plugin directory, so a test that omits
    the flag silently writes into the repository instead of a tmp_path. That is
    how ``plugins/shipwright-security/.shipwright/triage.jsonl`` kept
    reappearing as an untracked file.

    The guard fails loudly rather than cleaning up quietly: a test that pollutes
    the source tree is also a test that is not asserting against the state it
    thinks it is. It restores the tree either way so one offender cannot cascade
    into the next test.
    """
    marker = PLUGIN_ROOT / ".shipwright"
    existed = marker.exists()
    yield
    if marker.exists() and not existed:
        leaked = sorted(str(p.relative_to(PLUGIN_ROOT)) for p in marker.rglob("*")
                        if p.is_file())
        shutil.rmtree(marker, ignore_errors=True)
        pytest.fail(
            "this test wrote into the plugin source tree: "
            f"{', '.join(leaked) or '.shipwright/'}. An entry point whose "
            "--project-root defaults to '.' was invoked without one, so it "
            "targeted the CWD (the plugin dir) instead of a tmp_path. Pass "
            "--project-root str(tmp_path).",
            pytrace=False,
        )


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
