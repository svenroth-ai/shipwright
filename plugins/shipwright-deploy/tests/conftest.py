"""Shared test fixtures for shipwright-deploy."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

# Shared scripts
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))


@pytest.fixture
def plugin_root():
    return Path(__file__).resolve().parent.parent
