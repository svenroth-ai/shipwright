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


@pytest.fixture(autouse=True)
def _no_ambient_codextender(monkeypatch):
    """CODEXTENDER_ACTIVE now coerces the external-review driver, so an ambient value
    (a developer running pytest inside a Codextender session) would flip every
    `driver=claude` roster test. Tests that want it opt in with setenv."""
    monkeypatch.delenv("CODEXTENDER_ACTIVE", raising=False)


# Stack-profile test isolation (campaign stack-profile-resolver, D4): keeps the
# developer's real ~/.shipwright/profiles out of every test in this root.
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_isolation_dir = str(_Path(__file__).resolve().parents[3] / "shared" / "scripts")
_added = _isolation_dir not in _sys.path
if _added:
    _sys.path.append(_isolation_dir)
from profile_test_isolation import isolate_user_profiles_dir  # noqa: E402,F401

if _added:  # leave sys.path as found: shared/scripts holds a `tools` package that would shadow a plugin's
    _sys.path.remove(_isolation_dir)
