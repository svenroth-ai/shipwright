"""The pre-build AC tests' environment: attended, no network, nothing outside a temp dir (registered through ``conftest.pytest_plugins``)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ac_hermetic(request, monkeypatch, tmp_path_factory, tmp_path):
    """For every ``test_ac_*`` module: remove the review key and operator gateway (no test can reach a provider), point the signing key at a temp dir and run from a temp dir."""
    if not request.module.__name__.rsplit(".", 1)[-1].startswith("test_ac_"):  # the module name is shared.tests.test_ac_* here
        yield
        return
    for name in ("OPENROUTER_API_KEY", "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "SHIPWRIGHT_AC_SUGGEST", "SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID", "SHIPWRIGHT_AC_OPERATOR_CHANNEL"):
        monkeypatch.delenv(name, raising=False)
    home = tmp_path_factory.mktemp("ac_home")
    monkeypatch.setenv("SHIPWRIGHT_AC_KEY_FILE", str(home / "ac_operator.key"))
    monkeypatch.setenv("SHIPWRIGHT_AC_MODE", "ask")  # the questions are the subject of most tests; the mode tests set their own
    monkeypatch.chdir(tmp_path)  # the worktree this suite runs in looks like a campaign unit (unattended): every test runs from a temp dir
    yield
