"""WP2 (audit 2026-06-10): atomic + path-coordinated run-config persistence.

Unit tests for ``run_config_store`` — the single home for the atomic writer
(F11/F12) and the advisory lock that all three run-config writer families
coordinate on by path.
"""
import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from run_config_store import (  # noqa: E402
    LOCK_NAME,
    LockTimeout,
    atomic_write_json,
    lock_path,
    run_config_lock,
)


def test_lock_path_is_canonical(tmp_path):
    """Every writer family must target this exact lock file to coordinate."""
    assert lock_path(tmp_path).name == "shipwright_run_config.json.lock"
    assert lock_path(tmp_path).name == LOCK_NAME


def test_atomic_write_json_roundtrip(tmp_path):
    target = tmp_path / "shipwright_run_config.json"
    payload = {"a": 1, "nested": {"b": [1, 2, 3]}}
    atomic_write_json(target, payload)
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_atomic_write_json_leaves_no_tmp(tmp_path):
    target = tmp_path / "shipwright_run_config.json"
    atomic_write_json(target, {"x": 1})
    leftovers = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".tmp")
    assert leftovers == []


def test_atomic_write_json_overwrite_is_complete(tmp_path):
    """os.replace overwrites wholesale — a shorter second write leaves no
    stale tail bytes from the longer first write."""
    target = tmp_path / "shipwright_run_config.json"
    atomic_write_json(target, {"v": "first", "padding": "x" * 500})
    atomic_write_json(target, {"v": "second"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": "second"}


def test_run_config_lock_is_mutually_exclusive(tmp_path):
    """A second acquirer cannot enter while the first holds the lock."""
    with run_config_lock(tmp_path, timeout_seconds=2.0):
        with pytest.raises(LockTimeout):
            with run_config_lock(tmp_path, timeout_seconds=0.2):
                pass


def test_run_config_lock_released_after_context(tmp_path):
    """Releasing lets the next acquirer in immediately (no leaked hold)."""
    with run_config_lock(tmp_path, timeout_seconds=2.0):
        pass
    with run_config_lock(tmp_path, timeout_seconds=2.0):
        pass


def test_run_config_lock_coordinates_with_phase_tasks_lock(tmp_path):
    """The orchestrator's lock and phase_task_lifecycle's _PhaseTasksLock are
    different implementations but target the same lock file, so they mutually
    exclude (audit WP2/F11 — coordination is by path, not by shared code)."""
    from phase_task_lifecycle import _PhaseTasksLock

    with _PhaseTasksLock(tmp_path):
        with pytest.raises(LockTimeout):
            with run_config_lock(tmp_path, timeout_seconds=0.2):
                pass
