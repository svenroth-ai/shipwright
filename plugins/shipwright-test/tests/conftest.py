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
