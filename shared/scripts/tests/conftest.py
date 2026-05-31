"""Shared fixtures for ``shared/scripts/tests``.

This directory had no conftest until ``shared/scripts/tests`` became
CI-covered (iterate-2026-05-31-ci-gate-guard), which surfaced two
non-hermetic ``test_validate_env.py`` tests.
"""

import pytest

# Profile-defined env vars that ``validate_env`` reads. ``validate()`` merges
# ``os.environ`` over the parsed ``.env.local`` (env wins by design — CI/deploy
# inject real secrets), so a developer host that exports any of these (even
# empty) would clobber the file values the file-based tests write and make
# ``found`` collapse to empty. Cleared here so the dir's tests are hermetic;
# tests that need a var PRESENT set it via ``monkeypatch.setenv`` in the body
# (which runs after this autouse fixture).
_PROFILE_ENV_VARS = (
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "JELASTIC_TOKEN",
    "SUPABASE_ACCESS_TOKEN",
)


@pytest.fixture(autouse=True)
def _isolate_profile_env(monkeypatch):
    for var in _PROFILE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
