"""Suite-wide isolation for the Codex reviewer-model session-override env vars.

Registered as a `pytest_plugins` entry (not added inline to `conftest.py`,
which already sits at its ADR-101 exception cap) — mirrors
`source_state_capture_isolation.py`'s own shape and reason: a developer's own
shell may export `SHIPWRIGHT_CODEX_REVIEW_MODEL` /
`SHIPWRIGHT_CODEX_PLAN_REVIEW_MODEL` (the documented session-override
mechanism, iterate-2026-09-19-codex-reviewer-session-override), and several
tests assert the hardcoded-default / project-config resolution paths on the
assumption that neither is set.
"""

import pytest

_CODEX_REVIEW_MODEL_ENV = (
    "SHIPWRIGHT_CODEX_REVIEW_MODEL",
    "SHIPWRIGHT_CODEX_PLAN_REVIEW_MODEL",
)


@pytest.fixture(autouse=True)
def isolate_codex_review_model_env(monkeypatch):
    # No setenv-sentinel-then-delenv trick here (unlike the sibling fixture
    # above): nothing under test ever writes these two names to os.environ
    # directly, only reads them via os.environ.get() in
    # codex_review_model_resolution.py, so there is no write this fixture
    # would need to catch on monkeypatch's undo stack (doubt-reviewer finding,
    # iterate-2026-09-19-codex-reviewer-session-override).
    for name in _CODEX_REVIEW_MODEL_ENV:
        monkeypatch.delenv(name, raising=False)
