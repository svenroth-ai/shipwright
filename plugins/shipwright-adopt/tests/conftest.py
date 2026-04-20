from pathlib import Path
import sys

import pytest

# Make plugin's `scripts/` importable as a package root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def nextjs_repo(fixtures_dir: Path) -> Path:
    return fixtures_dir / "nextjs-repo"


@pytest.fixture
def python_cli(fixtures_dir: Path) -> Path:
    return fixtures_dir / "python-cli"


@pytest.fixture
def nested_shipwright(fixtures_dir: Path) -> Path:
    return fixtures_dir / "nested-shipwright"


@pytest.fixture
def polyglot_monorepo(fixtures_dir: Path) -> Path:
    return fixtures_dir / "polyglot-monorepo"
