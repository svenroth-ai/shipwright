"""Suite-wide isolation for the source-state environment transport."""

import os

import pytest


# ``finalize_iterate.run`` and ``resolve_churn_conflicts`` both capture into the
# real process environment. Tests reuse run ids across fixture repositories, so
# isolation belongs to the suite rather than to each importing module.
_SOURCE_STATE_CAPTURE_ENV = (
    "SHIPWRIGHT_SOURCE_DIRTY",
    "SHIPWRIGHT_SOURCE_DIRTY_RUN",
    "SHIPWRIGHT_SOURCE_DIRTY_ROOT",
)
_SOURCE_STATE_CAPTURE_SLOT_PREFIX = "SHIPWRIGHT_SOURCE_DIRTY_SLOT_"


@pytest.fixture(autouse=True)
def isolate_source_state_capture(monkeypatch):
    """Restore all capture names after every test, including keyed slots."""
    # setenv-before-delenv is load-bearing: it registers absent fixed names for
    # restoration if production code creates them during the test.
    for name in _SOURCE_STATE_CAPTURE_ENV:
        monkeypatch.setenv(name, "conftest-sentinel")
        monkeypatch.delenv(name, raising=False)
    for name in tuple(os.environ):
        if name.startswith(_SOURCE_STATE_CAPTURE_SLOT_PREFIX):
            monkeypatch.delenv(name, raising=False)
    yield
    # Keyed names are created after setup and therefore have no prior value in
    # monkeypatch. Remove test-created slots explicitly; host values removed
    # above are restored by monkeypatch after this fixture tears down.
    for name in tuple(os.environ):
        if name.startswith(_SOURCE_STATE_CAPTURE_SLOT_PREFIX):
            os.environ.pop(name, None)
