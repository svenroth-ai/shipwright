"""Shared test fixtures for shipwright-design."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))


@pytest.fixture
def plugin_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_project(tmp_path):
    """Project with specs from shipwright-project."""
    project = tmp_path / "my-app"
    project.mkdir()

    # Create project config
    (project / "shipwright_project_config.json").write_text(json.dumps({
        "profile": "supabase-nextjs",
        "scope": "full_app",
        "splits": [{"name": "01-auth", "status": "complete"}],
    }), encoding="utf-8")

    # Create planning with spec
    planning = project / ".shipwright" / "planning"
    (planning / "01-auth").mkdir(parents=True)
    (planning / "01-auth" / "spec.md").write_text(
        "# Authentication\n\n"
        "## 2. Functional Requirements\n\n"
        "| ID | Requirement | Priority |\n"
        "|----|-------------|----------|\n"
        "| FR-01.01 | The system SHALL allow login via email/password | Must |\n"
        "| FR-01.02 | The system SHALL display a dashboard after login | Must |\n"
        "| FR-01.03 | The system SHOULD provide user settings | Should |\n",
        encoding="utf-8",
    )

    return project


@pytest.fixture
def tmp_project_with_designs(tmp_project):
    """Project with existing designs."""
    designs = tmp_project / "designs"
    (designs / "screens").mkdir(parents=True)
    (designs / "flows").mkdir()
    (designs / "uploads").mkdir()

    (designs / "screens" / "01-login.html").write_text("<html><body>Login</body></html>")
    (designs / "screens" / "02-dashboard.html").write_text("<html><body>Dashboard</body></html>")
    (designs / "flows" / "auth-flow.html").write_text("<html><body>Auth Flow</body></html>")

    return tmp_project
