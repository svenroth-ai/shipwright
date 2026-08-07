"""P2.41a: the read LEG, not just the content classes, must be in lockstep.

``config_io._read_parse_shape`` reads via ``durable_read_text``, which retries
for ``READ_RETRY_BUDGET_SECONDS`` past the delete-pending ``PermissionError`` a
concurrent ``os.replace`` causes on Windows. ``gate_policy.read_run_config_mode``
used a plain ``Path.read_text`` and answered ``INERT_MODE`` on the very first
one — so a config being rewritten underneath them could make the orchestrator
loop and the phase-gate mechanism disagree about whether a run is driven.
``read_run_config_mode``'s own retry behavior (in isolation) is pinned in
``shared/tests/test_gate_policy_read_retry.py``; this file is the direct
cross-tree parity check the two readers agree under an IDENTICAL race, which
needs ``orchestrator_pkg`` — unavailable to ``shared/tests`` (ADR-044).

Two separate module instances are involved on purpose, not by accident: the
plugin bridges to ``shared/scripts/lib/atomic_write.py`` as a top-level
``atomic_write`` import (``run_config_store.py``), while ``shared/`` code
imports the very same file as ``lib.atomic_write`` (``gate_policy.py``,
mirroring ``lib.adr_index``). Both must be forced into the Windows branch for
this simulation to exercise either retry path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
# `lib.gate_policy` / `lib.atomic_write` need `shared/scripts` on sys.path too —
# stated explicitly rather than relied on as a side effect of `import orchestrator`
# below, so this keeps working regardless of import order in the pytest session.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import orchestrator  # noqa: E402,F401 — installs the ``orchestrator`` shim namespace
from orchestrator_pkg import config_io  # noqa: E402
from orchestrator_pkg.constants import CONFIG_NAME  # noqa: E402

import atomic_write as plugin_aw  # noqa: E402  (config_io's read leg — see module docstring)
import lib.atomic_write as shared_aw  # noqa: E402  (gate_policy's read leg)
from lib.gate_policy import SINGLE_SESSION, read_run_config_mode  # noqa: E402


def _sharing_violation(winerror: int = 5) -> PermissionError:
    exc = PermissionError(13, "Access is denied")
    exc.winerror = winerror
    return exc


def _write_single_session(tmp_path: Path) -> Path:
    cfg = tmp_path / CONFIG_NAME
    cfg.write_text(json.dumps({"schemaVersion": 2, "mode": "single_session"}), encoding="utf-8")
    return cfg


# Captured once, at import time, before either test monkeypatches ``Path.read_text``
# — a call-time capture would (on the second invocation below) close over the FIRST
# flaky wrapper instead of the genuine original, since ``monkeypatch`` never restores
# between two ``setattr`` calls inside the same test.
_REAL_READ_TEXT = Path.read_text


def _flaky_read_text(flips: int):
    """A ``Path.read_text`` stand-in scoped to the config file: raises a
    sharing violation ``flips`` times for THAT path, then delegates to the
    real read. Any other read passes straight through."""

    def _read(self, *a, **k):
        if self.name != CONFIG_NAME:
            return _REAL_READ_TEXT(self, *a, **k)
        _read.count += 1
        if _read.count <= flips:
            raise _sharing_violation()
        return _REAL_READ_TEXT(self, *a, **k)

    _read.count = 0
    return _read


@pytest.fixture
def force_windows_retry(monkeypatch):
    """Both atomic_write instances think they're on Windows; ``time`` is the
    same global module either way, so patching it once covers both."""
    monkeypatch.setattr(plugin_aw, "_is_windows", lambda: True)
    monkeypatch.setattr(shared_aw, "_is_windows", lambda: True)
    monkeypatch.setattr(plugin_aw.time, "sleep", lambda _s: None)


def test_the_two_readers_agree_under_the_identical_flaky_read(
    tmp_path, monkeypatch, force_windows_retry,
):
    """Direct parity: the orchestrator loop and the gate mechanism must reach
    the same verdict about the same in-flight rewrite, not just the same
    verdict about already-settled content."""
    _write_single_session(tmp_path)

    monkeypatch.setattr(Path, "read_text", _flaky_read_text(flips=2))
    config, present = config_io.read_run_config(tmp_path)
    assert present is True and config_io.is_single_session(config) is True

    # Replay the identical race (fresh attempt counter) for the gate reader.
    monkeypatch.setattr(Path, "read_text", _flaky_read_text(flips=2))
    assert read_run_config_mode(tmp_path) == SINGLE_SESSION
