"""Tests for legacy/single-service dev_server.py behavior.

These tests cover the back-compat surface used by build/test/preview/
iterate/adopt callers: `start --profile X --cwd Y`, top-level `pid`/`url`
in JSON output, single-service stop semantics. Multi-service behavior is
covered in test_dev_server_multiservice.py.

Internal helper API was refactored in iterate-20260425 (multi-service):
- `_load_state` now returns a v2-normalized dict even for legacy v1 files.
- Port probing function renamed `_is_port_in_use` → `_is_port_in_use_for_host`
  (the legacy name still exists as a dual-stack convenience wrapper).
- `cmd_start` no longer treats "port in use without a state file" as
  "already running" (Round-1 BLOCKER fix: never claim ownership of
  unowned processes).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dev_server import (
    _get_config,
    _load_state,
    _save_state,
    _clear_state,
    cmd_start,
    cmd_status,
    cmd_stop,
)


def test_get_config_known_profile():
    config = _get_config("supabase-nextjs")
    assert config["command"] == "npm run dev"
    assert config["port"] == 3000


def test_get_config_unknown_profile():
    config = _get_config("unknown-profile")
    assert config["port"] == 3000  # Uses default


def test_get_config_none_profile():
    config = _get_config(None)
    assert config["port"] == 3000


def test_save_and_load_state(tmp_path):
    """v1 state on disk is read back as v2-normalized (single-service)."""
    state = {"pid": 12345, "port": 3000}
    _save_state(tmp_path, state)
    loaded = _load_state(tmp_path)
    # v1 → v2 in-memory normalization
    assert loaded is not None
    assert loaded.get("version") == 2
    assert len(loaded["services"]) == 1
    assert loaded["services"][0]["pid"] == 12345
    assert loaded["services"][0]["port"] == 3000
    assert loaded["services"][0]["name"] == "primary"


def test_load_state_no_file(tmp_path):
    assert _load_state(tmp_path) is None


def test_clear_state(tmp_path):
    _save_state(tmp_path, {"pid": 1})
    _clear_state(tmp_path)
    assert _load_state(tmp_path) is None


@patch("dev_server._is_pid_running", return_value=True)
@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_start_already_running(mock_port, mock_pid, tmp_path):
    """Port in use AND state file with matching live PID → already-running."""
    # Pre-seed a v2 state file matching the supabase-nextjs single-service shape
    state = {
        "version": 2,
        "profile": "supabase-nextjs",
        "services": [{
            "name": "primary",
            "pid": 12345,
            "port": 3000,
            "host": "localhost",
            "scheme": "http",
            "command": "npm run dev",
            "url": "http://localhost:3000",
            "ready_path": "/",
            "ready_timeout_seconds": 60,
            "primary": True,
        }],
    }
    _save_state(tmp_path, state)
    result = cmd_start(tmp_path, "supabase-nextjs")
    assert result["running"] is True
    assert result["started_by_us"] is False
    assert "already running" in result.get("message", "").lower()


@patch("dev_server._is_port_in_use_for_host", return_value=False)
@patch("dev_server._wait_for_service", return_value=(True, ""))
@patch("dev_server.subprocess.Popen")
def test_start_new_server(mock_popen, mock_wait, mock_port, tmp_path):
    mock_proc = MagicMock()
    mock_proc.pid = 99999
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc

    result = cmd_start(tmp_path, "supabase-nextjs")
    assert result["running"] is True
    assert result["pid"] == 99999
    assert result["started_by_us"] is True
    assert result["url"] == "http://localhost:3000"


def test_stop_no_state(tmp_path):
    result = cmd_stop(tmp_path)
    assert result["running"] is False
    assert "no dev server state" in result.get("message", "").lower()


@patch("dev_server._is_pid_running", return_value=False)
def test_stop_stale_pid(mock_pid, tmp_path):
    """Stale PID is non-fatal; state still cleared."""
    _save_state(tmp_path, {"pid": 12345, "port": 3000})
    result = cmd_stop(tmp_path)
    assert result["running"] is False
    assert _load_state(tmp_path) is None  # State cleaned up


def test_status_no_state(tmp_path):
    result = cmd_status(tmp_path)
    assert result["running"] is False


@patch("dev_server._is_pid_running", return_value=True)
@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_status_running(mock_port, mock_pid, tmp_path):
    _save_state(tmp_path, {"pid": 12345, "port": 3000})
    result = cmd_status(tmp_path)
    assert result["running"] is True
    assert result["pid"] == 12345
    assert result["url"] == "http://localhost:3000"


@patch("dev_server._is_pid_running", return_value=False)
@patch("dev_server._is_port_in_use_for_host", return_value=False)
def test_status_stale_cleans_up(mock_port, mock_pid, tmp_path):
    _save_state(tmp_path, {"pid": 12345, "port": 3000})
    result = cmd_status(tmp_path)
    assert result["running"] is False
    assert _load_state(tmp_path) is None  # Cleaned up
