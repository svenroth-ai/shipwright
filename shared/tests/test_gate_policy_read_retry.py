"""P2.41a: ``read_run_config_mode``'s own Windows read-retry behavior.

Companion to ``test_atomic_write_windows_read_retry.py`` (the primitive) and
``test_gate_policy.py`` (everything else about the reporter); split out so
neither host file grows past its line budget. The cross-tree parity test
(comparing this reporter against ``config_io``'s strict reader under the
identical race) lives in
``plugins/shipwright-run/tests/test_runconfig_read_retry_parity.py`` — it
needs ``orchestrator_pkg``, which ``shared/tests`` cannot import (ADR-044).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.atomic_write as aw  # noqa: E402
from lib.gate_policy import INERT_MODE, SINGLE_SESSION, read_run_config_mode  # noqa: E402

_CONFIG_NAME = "shipwright_run_config.json"


def _sharing_violation(winerror: int = 5) -> PermissionError:
    exc = PermissionError(13, "Access is denied")
    exc.winerror = winerror
    return exc


def _write_single_session(tmp_path: Path) -> Path:
    cfg = tmp_path / _CONFIG_NAME
    cfg.write_text(json.dumps({"schemaVersion": 2, "mode": "single_session"}), encoding="utf-8")
    return cfg


def _flaky_read_text(flips: int):
    """A ``Path.read_text`` stand-in scoped to the config file: raises a
    sharing violation ``flips`` times for THAT path, then delegates to the
    real read. Any other read passes straight through, untouched and
    uncounted."""
    real_read_text = Path.read_text
    attempts: list[int] = []

    def _read(self, *a, **k):
        if self.name != _CONFIG_NAME:
            return real_read_text(self, *a, **k)
        attempts.append(1)
        if len(attempts) <= flips:
            raise _sharing_violation()
        return real_read_text(self, *a, **k)

    return _read, attempts


@pytest.fixture
def force_windows_retry(monkeypatch):
    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw.time, "sleep", lambda _s: None)


def test_read_run_config_mode_survives_a_windows_delete_pending_read(
    tmp_path, monkeypatch, force_windows_retry,
):
    """Before the fix this answered INERT_MODE on the very first violation."""
    _write_single_session(tmp_path)
    flaky, attempts = _flaky_read_text(flips=2)
    monkeypatch.setattr(Path, "read_text", flaky)

    assert read_run_config_mode(tmp_path) == SINGLE_SESSION
    assert len(attempts) == 3, "the reporter must retry, not give up on the first violation"


def test_read_run_config_mode_still_fails_safe_past_the_retry_budget(
    tmp_path, monkeypatch,
):
    """Direction stays fail-safe: a genuinely stuck holder (past the budget)
    must still degrade to INERT_MODE, never crash the caller."""
    _write_single_session(tmp_path)
    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw, "READ_RETRY_BUDGET_SECONDS", 0.02)
    flaky, _ = _flaky_read_text(flips=10**6)  # never succeeds within the budget
    monkeypatch.setattr(Path, "read_text", flaky)

    assert read_run_config_mode(tmp_path) == INERT_MODE
