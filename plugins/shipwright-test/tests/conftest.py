"""Shared test fixtures for shipwright-test."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

# Also add shared scripts to path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

# Iterate B8: tools under scripts/ now import ``from shared.contracts ...``
# directly. Add the repo root so the ``shared`` namespace package resolves
# inside the plugin-local venv (which doesn't ship the monorepo's top-level
# packages by default).
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def plugin_root():
    return Path(__file__).resolve().parent.parent
