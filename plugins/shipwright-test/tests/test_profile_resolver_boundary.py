"""Boundary probe: this test root can import the stack-profile resolver (D2/D4/S1 item 17).

Zero internal imports: stdlib plus the resolver reached through the monorepo
layout, exactly as the root's own conftest wires it. Also proves the autouse
user-profiles isolation fixture is active (the variable points into a tmp dir).
Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py for the FR note).
"""

import os
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "shared" / "scripts"


@pytest.mark.covers("FR-01.06")
def test_resolver_importable_and_user_profiles_isolated(tmp_path):
    before = list(sys.path)
    if str(_SCRIPTS) not in sys.path:
        sys.path.append(str(_SCRIPTS))
    try:
        import profile_resolver
    finally:
        sys.path[:] = before  # shared/scripts has a `tools` package: leave sys.path exactly as found

    res = profile_resolver.resolve_profile("vite-hono", tmp_path)
    assert res.source == "bundled" and not res.custom
    assert profile_resolver.resolve_profile("generic", tmp_path).source == "builtin"
    # Read from the environment, NOT by requesting the fixture by name: a by-name request
    # would keep this green after `autouse=True` is removed. KeyError here = not active.
    user = os.environ["SHIPWRIGHT_USER_PROFILES_DIR"]
    assert Path(user).is_dir() and not list(Path(user).iterdir())  # an empty, fresh tmp dir
    assert not Path(user).resolve().is_relative_to((Path.home() / ".shipwright").resolve())
    assert profile_resolver.user_dir() == user
