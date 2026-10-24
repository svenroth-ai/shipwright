"""Shared pytest fixture: keep the REAL ``~/.shipwright/profiles`` out of tests.

Stack-profile resolution reads a user-level directory. A developer's own
profiles there would leak into any test that resolves a profile name, so every
test root that touches profiles imports this autouse fixture (the repo-root
``conftest.py`` does not load for plugin roots).

Wire-up, in the root's ``tests/conftest.py``::

    sys.path.append(<repo>/shared/scripts)
    from profile_test_isolation import isolate_user_profiles_dir  # noqa: F401,E402

``shared/tests`` registers it through ``pytest_plugins`` instead. The
environment variable is inherited by subprocesses.
"""

from __future__ import annotations

import pytest

USER_DIR_ENV = "SHIPWRIGHT_USER_PROFILES_DIR"


@pytest.fixture(autouse=True)
def isolate_user_profiles_dir(tmp_path_factory, monkeypatch):
    empty = tmp_path_factory.mktemp("user-profiles-isolated")
    monkeypatch.setenv(USER_DIR_ENV, str(empty))
    return empty
