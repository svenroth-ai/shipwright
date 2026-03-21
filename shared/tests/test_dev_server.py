"""Tests for dev_server.py."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dev_server import (
    STATE_FILE,
    _get_config,
    _is_port_in_use,
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
    state = {"pid": 12345, "port": 3000}
    _save_state(tmp_path, state)
    loaded = _load_state(tmp_path)
    assert loaded == state


def test_load_state_no_file(tmp_path):
    assert _load_state(tmp_path) is None


def test_clear_state(tmp_path):
    _save_state(tmp_path, {"pid": 1})
    _clear_state(tmp_path)
    assert _load_state(tmp_path) is None


@patch("dev_server._is_port_in_use", return_value=True)
def test_start_already_running(mock_port, tmp_path):
    result = cmd_start(tmp_path, "supabase-nextjs")
    assert result["running"] is True
    assert result["started_by_us"] is False
    assert "already running" in result["message"]


@patch("dev_server._is_port_in_use", return_value=False)
@patch("dev_server._wait_for_ready", return_value=True)
@patch("dev_server.subprocess.Popen")
def test_start_new_server(mock_popen, mock_ready, mock_port, tmp_path):
    mock_proc = MagicMock()
    mock_proc.pid = 99999
    mock_popen.return_value = mock_proc

    result = cmd_start(tmp_path, "supabase-nextjs")
    assert result["running"] is True
    assert result["pid"] == 99999
    assert result["started_by_us"] is True
    assert result["url"] == "http://localhost:3000"


def test_stop_no_state(tmp_path):
    result = cmd_stop(tmp_path)
    assert result["running"] is False
    assert "No dev server state" in result["message"]


@patch("dev_server._is_pid_running", return_value=False)
def test_stop_stale_pid(mock_pid, tmp_path):
    _save_state(tmp_path, {"pid": 12345, "port": 3000})
    result = cmd_stop(tmp_path)
    assert result["running"] is False
    assert _load_state(tmp_path) is None  # State cleaned up


def test_status_no_state(tmp_path):
    result = cmd_status(tmp_path)
    assert result["running"] is False


@patch("dev_server._is_pid_running", return_value=True)
@patch("dev_server._is_port_in_use", return_value=True)
def test_status_running(mock_port, mock_pid, tmp_path):
    _save_state(tmp_path, {"pid": 12345, "port": 3000})
    result = cmd_status(tmp_path)
    assert result["running"] is True
    assert result["pid"] == 12345
    assert result["url"] == "http://localhost:3000"


@patch("dev_server._is_pid_running", return_value=False)
@patch("dev_server._is_port_in_use", return_value=False)
def test_status_stale_cleans_up(mock_port, mock_pid, tmp_path):
    _save_state(tmp_path, {"pid": 12345, "port": 3000})
    result = cmd_status(tmp_path)
    assert result["running"] is False
    assert _load_state(tmp_path) is None  # Cleaned up
