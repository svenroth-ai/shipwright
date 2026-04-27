"""Shared fixtures for shipwright-compliance tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a realistic project root with all sample configs and artifacts."""
    root = tmp_path / "my-project"
    root.mkdir()

    # Copy config files to project root
    for config_name in [
        "sample_run_config.json",
        "sample_project_config.json",
        "sample_plan_config.json",
        "sample_build_config.json",
    ]:
        src = FIXTURES_DIR / config_name
        # Map sample_X_config.json -> shipwright_X_config.json
        dest_name = config_name.replace("sample_", "shipwright_")
        shutil.copy(src, root / dest_name)

    # Create .shipwright/agent_docs with decision log
    agent_docs = root / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "sample_decision_log.md", agent_docs / "decision_log.md")

    # Copy package.json
    shutil.copy(FIXTURES_DIR / "sample_package.json", root / "package.json")

    # Create compliance output directory
    (root / "compliance").mkdir()

    return root


@pytest.fixture
def empty_project_root(tmp_path: Path) -> Path:
    """Create an empty project root with no configs (edge case testing)."""
    root = tmp_path / "empty-project"
    root.mkdir()
    return root


@pytest.fixture
def partial_project_root(tmp_path: Path) -> Path:
    """Create a project root with only project config (mid-pipeline)."""
    root = tmp_path / "partial-project"
    root.mkdir()

    src = FIXTURES_DIR / "sample_project_config.json"
    shutil.copy(src, root / "shipwright_project_config.json")

    return root


@pytest.fixture
def sample_build_config() -> dict:
    """Return parsed sample build config."""
    return json.loads((FIXTURES_DIR / "sample_build_config.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_project_config() -> dict:
    """Return parsed sample project config."""
    return json.loads((FIXTURES_DIR / "sample_project_config.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_decision_log_text() -> str:
    """Return raw text of sample decision log."""
    return (FIXTURES_DIR / "sample_decision_log.md").read_text(encoding="utf-8")


@pytest.fixture
def sample_package_json() -> dict:
    """Return parsed sample package.json."""
    return json.loads((FIXTURES_DIR / "sample_package.json").read_text(encoding="utf-8"))
