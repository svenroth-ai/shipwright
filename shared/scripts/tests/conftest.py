"""Test-isolation fixtures for ``shared/scripts/tests``.

Hermetic-env guard
==================

``test_validate_env.py::TestValidateBuild`` / ``TestValidateDeploy`` assert on
values that ``validate()`` reads from the *tmp* ``.env.local`` under test (and
on the *absence* of optional vars). Those assertions must NOT be at the mercy
of the ambient shell.

The trap, caught empirically on iterate-2026-05-31-ci-shared-tests: a Shipwright
dev session loads the repo's own scaffolded ``.env.local`` into ``os.environ``
(``NEXT_PUBLIC_SUPABASE_URL=...`` — a literal placeholder). ``validate()``
correctly lets ``os.environ`` take precedence over ``.env.local`` (it mirrors
``shared/scripts/lib/env.load_shipwright_env``, whose contract is "vars already
present in os.environ are never overwritten"), and ``...`` is a
``_PLACEHOLDER_PATTERNS`` value — so the file-based tests reported a real value
as "missing". Clean CI is unaffected (the vars are absent there), so this only
bit local runs — a textbook non-hermetic test. This autouse fixture removes the
profile vars before each test; tests that want them set them via ``monkeypatch``
*after* this fixture runs — the autouse fixture body executes before the test
body, and both share the one function-scoped ``MonkeyPatch``, so the later
``setenv`` wins deterministically.
"""

from __future__ import annotations

import pytest

# Profile vars the validate_env tests assert presence/absence of. Cleared so
# the tmp ``.env.local`` (or an explicit ``monkeypatch.setenv``) is the only
# source — never the ambient session environment.
_ISOLATED_ENV_VARS = (
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "JELASTIC_TOKEN",
    "SUPABASE_ACCESS_TOKEN",
)


@pytest.fixture(autouse=True)
def _isolate_ambient_env(monkeypatch):
    for name in _ISOLATED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
