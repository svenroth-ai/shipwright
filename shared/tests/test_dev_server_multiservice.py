"""Tests for the multi-service dev_server.py refactor (iterate-20260425).

Covers AC1-AC10, AC13. Profile-loading tests for AC11 (vite-hono) live
near the bottom. Tests for AC12 (signature merge) and AC14 (adopt
SKILL.md prose) live in the shipwright-adopt plugin tests.

All tests use mocks; no real subprocess is launched.
"""

from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dev_server  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# AC1 / AC8 — schema loading + legacy compatibility
# ---------------------------------------------------------------------------

def _write_profile(tmp_path: Path, name: str, body: dict) -> Path:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir(exist_ok=True)
    p = profiles_dir / f"{name}.json"
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


def test_get_services_legacy_dev_server_block(tmp_path):
    services, warnings = dev_server._get_services_for_test(
        profile_data={"dev_server": {"command": "npm run dev", "port": 3000, "ready_path": "/"}},
        cwd=tmp_path,
    )
    assert len(services) == 1
    assert services[0]["name"] == "primary"
    assert services[0]["primary"] is True
    assert services[0]["host"] == "localhost"
    assert services[0]["scheme"] == "http"
    assert warnings == []


def test_get_services_array_shape(tmp_path):
    services, warnings = dev_server._get_services_for_test(
        profile_data={
            "services": [
                {"name": "a", "command": "cmd-a", "port": 3000, "ready_path": "/"},
                {"name": "b", "command": "cmd-b", "port": 3001},
            ]
        },
        cwd=tmp_path,
    )
    assert [s["name"] for s in services] == ["a", "b"]
    # First-declared default-primary
    assert services[0]["primary"] is True
    assert services[1].get("primary") in (False, None)
    assert warnings == []


def test_get_services_both_blocks_prefers_array_with_warning(tmp_path):
    services, warnings = dev_server._get_services_for_test(
        profile_data={
            "dev_server": {"command": "legacy-cmd", "port": 9999, "ready_path": "/"},
            "services": [{"name": "winner", "command": "new-cmd", "port": 3000}],
        },
        cwd=tmp_path,
    )
    assert len(services) == 1
    assert services[0]["name"] == "winner"
    assert any("services" in w and "dev_server" in w for w in warnings)


def test_get_services_explicit_primary(tmp_path):
    services, _ = dev_server._get_services_for_test(
        profile_data={
            "services": [
                {"name": "a", "command": "x", "port": 3000},
                {"name": "b", "command": "y", "port": 3001, "primary": True},
            ]
        },
        cwd=tmp_path,
    )
    primary = dev_server._pick_primary(services)
    assert primary["name"] == "b"


def test_get_services_two_primaries_errors(tmp_path):
    with pytest.raises(ValueError, match="multiple"):
        dev_server._get_services_for_test(
            profile_data={
                "services": [
                    {"name": "a", "command": "x", "port": 3000, "primary": True},
                    {"name": "b", "command": "y", "port": 3001, "primary": True},
                ]
            },
            cwd=tmp_path,
        )


def test_get_services_duplicate_names_errors(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        dev_server._get_services_for_test(
            profile_data={
                "services": [
                    {"name": "dupe", "command": "x", "port": 3000},
                    {"name": "dupe", "command": "y", "port": 3001},
                ]
            },
            cwd=tmp_path,
        )


def test_get_services_missing_depends_on_target_errors(tmp_path):
    with pytest.raises(ValueError, match="depends_on"):
        dev_server._get_services_for_test(
            profile_data={
                "services": [
                    {"name": "a", "command": "x", "port": 3000, "depends_on": ["nonexistent"]},
                ]
            },
            cwd=tmp_path,
        )


def test_get_services_self_dependency_errors(tmp_path):
    with pytest.raises(ValueError, match="self"):
        dev_server._get_services_for_test(
            profile_data={
                "services": [
                    {"name": "a", "command": "x", "port": 3000, "depends_on": ["a"]},
                ]
            },
            cwd=tmp_path,
        )


def test_get_services_dependency_cycle_errors(tmp_path):
    with pytest.raises(ValueError, match="cycle"):
        dev_server._get_services_for_test(
            profile_data={
                "services": [
                    {"name": "a", "command": "x", "port": 3000, "depends_on": ["b"]},
                    {"name": "b", "command": "y", "port": 3001, "depends_on": ["a"]},
                ]
            },
            cwd=tmp_path,
        )


def test_get_services_malformed_entry_errors(tmp_path):
    # Missing port
    with pytest.raises(ValueError):
        dev_server._get_services_for_test(
            profile_data={"services": [{"name": "a", "command": "x"}]},
            cwd=tmp_path,
        )
    # Empty name
    with pytest.raises(ValueError):
        dev_server._get_services_for_test(
            profile_data={"services": [{"name": "", "command": "x", "port": 3000}]},
            cwd=tmp_path,
        )
    # Non-int port
    with pytest.raises(ValueError):
        dev_server._get_services_for_test(
            profile_data={"services": [{"name": "a", "command": "x", "port": "three-thousand"}]},
            cwd=tmp_path,
        )


def test_get_services_size_one_backend_only(tmp_path):
    services, _ = dev_server._get_services_for_test(
        profile_data={
            "services": [{"name": "api", "command": "node server.js", "port": 4000}]
        },
        cwd=tmp_path,
    )
    assert len(services) == 1
    assert services[0]["ready_path"] is None or "ready_path" not in services[0] or services[0]["ready_path"] == ""


def test_get_services_dev_url_preserves_host_scheme(tmp_path):
    build_config = tmp_path / "shipwright_build_config.json"
    build_config.write_text(
        json.dumps({"dev_url": "https://127.0.0.1:4443/"}), encoding="utf-8"
    )
    # No profile match, no profile_data -> falls back to dev_url
    services, _ = dev_server._get_services_for_test(profile_data=None, cwd=tmp_path)
    assert len(services) == 1
    s = services[0]
    assert s["host"] == "127.0.0.1"
    assert s["scheme"] == "https"
    assert s["port"] == 4443


def test_get_services_non_loopback_host_errors(tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        dev_server._get_services_for_test(
            profile_data={
                "services": [
                    {"name": "a", "command": "x", "port": 3000, "host": "192.168.1.5"}
                ]
            },
            cwd=tmp_path,
        )


def test_get_services_dev_url_non_loopback_host_rejected_at_start(tmp_path):
    """build_config dev_url with non-loopback host → cmd_start rejects."""
    build_config = tmp_path / "shipwright_build_config.json"
    build_config.write_text(
        json.dumps({"dev_url": "http://my-dev-machine.local:3000/"}),
        encoding="utf-8",
    )
    result = dev_server.cmd_start(tmp_path, profile=None)
    assert result["running"] is False
    assert "loopback" in result.get("error", "").lower()


def test_get_services_depends_on_non_string_errors(tmp_path):
    with pytest.raises(ValueError, match="depends_on"):
        dev_server._get_services_for_test(
            profile_data={
                "services": [
                    {"name": "a", "command": "x", "port": 3000},
                    {"name": "b", "command": "y", "port": 3001, "depends_on": [42]},
                ]
            },
            cwd=tmp_path,
        )


def test_get_services_ready_timeout_non_int_errors(tmp_path):
    with pytest.raises(ValueError, match="ready_timeout_seconds"):
        dev_server._get_services_for_test(
            profile_data={
                "services": [
                    {"name": "a", "command": "x", "port": 3000,
                     "ready_timeout_seconds": "thirty"}
                ]
            },
            cwd=tmp_path,
        )


# ---------------------------------------------------------------------------
# AC3 — Topo ordering / parallel start
# ---------------------------------------------------------------------------

def test_topo_sort_independent_services_one_layer():
    services = [
        {"name": "a", "command": "x", "port": 3000},
        {"name": "b", "command": "y", "port": 3001},
        {"name": "c", "command": "z", "port": 3002},
    ]
    layers = dev_server._topo_sort(services)
    assert len(layers) == 1
    assert [s["name"] for s in layers[0]] == ["a", "b", "c"]


def test_topo_sort_dependency_two_layers():
    services = [
        {"name": "a", "command": "x", "port": 3000},
        {"name": "b", "command": "y", "port": 3001, "depends_on": ["a"]},
    ]
    layers = dev_server._topo_sort(services)
    assert len(layers) == 2
    assert [s["name"] for s in layers[0]] == ["a"]
    assert [s["name"] for s in layers[1]] == ["b"]


def test_topo_sort_mixed_dag_stable_declaration_order():
    services = [
        {"name": "a", "command": "x", "port": 3000},
        {"name": "b", "command": "x", "port": 3001},
        {"name": "c", "command": "x", "port": 3002, "depends_on": ["a"]},
        {"name": "d", "command": "x", "port": 3003, "depends_on": ["a"]},
        {"name": "e", "command": "x", "port": 3004, "depends_on": ["c", "d"]},
    ]
    layers = dev_server._topo_sort(services)
    assert len(layers) == 3
    assert [s["name"] for s in layers[0]] == ["a", "b"]
    assert [s["name"] for s in layers[1]] == ["c", "d"]
    assert [s["name"] for s in layers[2]] == ["e"]


# ---------------------------------------------------------------------------
# AC1 / AC3 — shlex command parsing
# ---------------------------------------------------------------------------

@patch("dev_server.subprocess.Popen")
def test_start_command_with_quoted_args_via_shlex(mock_popen, tmp_path):
    mock_proc = MagicMock()
    mock_proc.pid = 42
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc

    service = {
        "name": "fe",
        "command": 'npm run dev -- --port 5173 --host "0.0.0.0"',
        "port": 5173,
        "host": "localhost",
        "scheme": "http",
    }
    proc, _record = dev_server._start_one(service, tmp_path)
    args = mock_popen.call_args[0][0]
    # Argv must include the literal '0.0.0.0' as a single token (quotes stripped)
    assert "0.0.0.0" in args
    # The double quotes themselves must NOT appear as part of any arg
    assert all('"' not in a for a in args)


# ---------------------------------------------------------------------------
# AC3 — _wait_for_service health checks
# ---------------------------------------------------------------------------

class _FakeProc:
    """Minimal Popen-like double for wait tests."""
    def __init__(self, exit_after: float | None = None):
        self.pid = 12345
        self._dead_at = (time.time() + exit_after) if exit_after is not None else None

    def poll(self):
        if self._dead_at is None:
            return None
        return 1 if time.time() >= self._dead_at else None


@patch("dev_server._http_probe", return_value=False)
@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_wait_for_service_port_open_only(mock_port, mock_http, tmp_path):
    svc = {"name": "a", "host": "localhost", "scheme": "http", "port": 3000}
    proc = _FakeProc()
    deadline = time.time() + 2
    ok, reason = dev_server._wait_for_service(svc, proc, deadline)
    assert ok is True
    assert reason == ""


def test_wait_for_service_child_died_fails_fast(tmp_path):
    svc = {"name": "a", "host": "localhost", "scheme": "http", "port": 3000}
    proc = _FakeProc(exit_after=0.0)  # dead immediately
    deadline = time.time() + 30  # generous deadline
    start = time.time()
    ok, reason = dev_server._wait_for_service(svc, proc, deadline)
    elapsed = time.time() - start
    assert ok is False
    assert reason == "process_exited"
    assert elapsed < 5  # NOT the full 30s


@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_wait_for_service_port_held_by_external_process_no_pid(mock_port, tmp_path):
    """Port open BEFORE we Popened — but our PID never started.

    `_already_running_owned` covers this at start-time. The lower-level
    `_wait_for_service` doesn't get called in that path, so this case is
    proven via cmd_start (see test_start_port_busy_no_state_errors_no_kill).
    Marking as covered-elsewhere; nothing to assert at this level.
    """
    pass


@patch("dev_server._http_probe")
@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_wait_for_service_ready_path_2xx(mock_port, mock_http, tmp_path):
    mock_http.return_value = True  # 200 OK
    svc = {"name": "a", "host": "localhost", "scheme": "http", "port": 3000, "ready_path": "/health"}
    proc = _FakeProc()
    ok, _ = dev_server._wait_for_service(svc, proc, time.time() + 2)
    assert ok is True


@patch("dev_server._http_probe")
@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_wait_for_service_ready_path_3xx(mock_port, mock_http, tmp_path):
    # http_probe should accept 3xx; we model it returning True
    mock_http.return_value = True
    svc = {"name": "a", "host": "localhost", "scheme": "http", "port": 3000, "ready_path": "/"}
    proc = _FakeProc()
    ok, _ = dev_server._wait_for_service(svc, proc, time.time() + 2)
    assert ok is True


@patch("dev_server._http_probe")
@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_wait_for_service_ready_path_5xx_retries_until_deadline(mock_port, mock_http, tmp_path):
    # First two calls 5xx (False), then 200 (True)
    mock_http.side_effect = [False, False, True]
    svc = {"name": "a", "host": "localhost", "scheme": "http", "port": 3000, "ready_path": "/"}
    proc = _FakeProc()
    ok, _ = dev_server._wait_for_service(svc, proc, time.time() + 10)
    assert ok is True
    assert mock_http.call_count >= 3


@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_wait_for_service_bounded_elapsed_time_under_short_deadline(mock_port, tmp_path):
    """All HTTP probes fail; elapsed time MUST stay under the deadline."""
    svc = {"name": "a", "host": "localhost", "scheme": "http", "port": 3000, "ready_path": "/"}
    proc = _FakeProc()
    deadline = time.time() + 3  # 3 seconds total
    start = time.time()
    with patch("dev_server._http_probe", return_value=False):
        ok, reason = dev_server._wait_for_service(svc, proc, deadline)
    elapsed = time.time() - start
    assert ok is False
    assert reason == "timeout"
    # Hard upper bound: must respect deadline + a tiny tolerance for the final
    # sleep iteration (1.0s between HTTP retries).
    assert elapsed < 5, f"elapsed {elapsed}s overran deadline+tolerance"


def test_wait_for_service_ipv6_only_bind(tmp_path):
    """host=localhost: probe falls through IPv4 to IPv6 and succeeds on ::1."""
    calls = []

    def fake_port(host, port):
        calls.append(host)
        return host == "::1"

    svc = {"name": "a", "host": "localhost", "scheme": "http", "port": 3000}
    proc = _FakeProc()
    with patch("dev_server._is_port_in_use_for_host", side_effect=fake_port), \
         patch("dev_server._http_probe", return_value=False):
        ok, _ = dev_server._wait_for_service(svc, proc, time.time() + 2)
    assert ok is True
    assert "::1" in calls


def test_wait_for_service_explicit_ipv4_host_no_ipv6_probe(tmp_path):
    calls = []

    def fake_port(host, port):
        calls.append(host)
        return host == "127.0.0.1"

    svc = {"name": "a", "host": "127.0.0.1", "scheme": "http", "port": 3000}
    proc = _FakeProc()
    with patch("dev_server._is_port_in_use_for_host", side_effect=fake_port), \
         patch("dev_server._http_probe", return_value=False):
        ok, _ = dev_server._wait_for_service(svc, proc, time.time() + 2)
    assert ok is True
    assert "::1" not in calls


def test_wait_for_service_explicit_ipv6_host_no_ipv4_probe(tmp_path):
    calls = []

    def fake_port(host, port):
        calls.append(host)
        return host == "::1"

    svc = {"name": "a", "host": "::1", "scheme": "http", "port": 3000}
    proc = _FakeProc()
    with patch("dev_server._is_port_in_use_for_host", side_effect=fake_port), \
         patch("dev_server._http_probe", return_value=False):
        ok, _ = dev_server._wait_for_service(svc, proc, time.time() + 2)
    assert ok is True
    assert "127.0.0.1" not in calls


def test_wait_for_service_http_uses_declared_host(tmp_path):
    """IPv6 host must produce bracketed URL: http://[::1]:3000/health"""
    captured_urls = []

    def fake_http(url, timeout):
        captured_urls.append(url)
        return True

    svc = {"name": "a", "host": "::1", "scheme": "http", "port": 3000, "ready_path": "/health"}
    proc = _FakeProc()
    with patch("dev_server._is_port_in_use_for_host", return_value=True), \
         patch("dev_server._http_probe", side_effect=fake_http):
        ok, _ = dev_server._wait_for_service(svc, proc, time.time() + 2)
    assert ok is True
    assert any("[::1]" in u for u in captured_urls), captured_urls


# ---------------------------------------------------------------------------
# AC5 / AC4 — already-running detection (never kill foreign)
# ---------------------------------------------------------------------------

@patch("dev_server._is_pid_running", return_value=True)
@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_start_already_running_only_when_pid_owned(mock_port, mock_pid, tmp_path):
    services = [{"name": "primary", "command": "x", "port": 3000, "host": "localhost", "scheme": "http"}]
    state = {
        "version": 2,
        "services": [{"name": "primary", "pid": 99, "port": 3000, "host": "localhost",
                      "scheme": "http", "command": "x", "url": "http://localhost:3000",
                      "ready_path": None, "ready_timeout_seconds": 60, "primary": True}],
    }
    dev_server._save_state(tmp_path, state)
    result = dev_server.cmd_start(tmp_path, "supabase-nextjs")
    assert result["running"] is True
    assert result.get("started_by_us") is False


@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_start_port_busy_no_state_errors_no_kill(mock_port, tmp_path):
    """Port in use but no state file → error, do NOT kill anything."""
    with patch("dev_server._kill_one") as kill_mock:
        # Run cmd_start with default profile (matches existing single-service test)
        result = dev_server.cmd_start(tmp_path, "supabase-nextjs")
    assert result["running"] is False
    assert "in use" in result.get("error", "").lower() or "occupied" in result.get("error", "").lower()
    kill_mock.assert_not_called()


@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_start_port_busy_state_file_mismatch_errors_no_kill(mock_port, tmp_path):
    # State references a different service set
    state = {
        "version": 2,
        "services": [{"name": "other", "pid": 99, "port": 3001, "host": "localhost",
                      "scheme": "http", "command": "y", "url": "http://localhost:3001",
                      "ready_path": None, "ready_timeout_seconds": 60, "primary": True}],
    }
    dev_server._save_state(tmp_path, state)
    with patch("dev_server._kill_one") as kill_mock, \
         patch("dev_server._is_pid_running", return_value=False):
        result = dev_server.cmd_start(tmp_path, "supabase-nextjs")
    assert result["running"] is False
    kill_mock.assert_not_called()


@patch("dev_server._is_port_in_use_for_host", return_value=False)
@patch("dev_server._is_pid_running", return_value=True)
def test_start_stale_state_different_service_set_with_live_pids_refuses(
    mock_pid, mock_port, tmp_path
):
    """State references services {a, b} with live PIDs; new request targets
    {primary} (different set) → refuse to act, no overwrite."""
    state = {
        "version": 2,
        "services": [
            {"name": "a", "pid": 100, "port": 4001, "host": "localhost",
             "scheme": "http", "command": "x", "url": "http://localhost:4001",
             "ready_path": None, "ready_timeout_seconds": 60, "primary": True},
            {"name": "b", "pid": 101, "port": 4002, "host": "localhost",
             "scheme": "http", "command": "y", "url": "http://localhost:4002",
             "ready_path": None, "ready_timeout_seconds": 60, "primary": False},
        ],
    }
    dev_server._save_state(tmp_path, state)
    with patch("dev_server._kill_one") as kill_mock, \
         patch("dev_server.subprocess.Popen") as popen_mock:
        result = dev_server.cmd_start(tmp_path, "supabase-nextjs")
    assert result["running"] is False
    assert "stale" in result.get("error", "").lower()
    kill_mock.assert_not_called()
    popen_mock.assert_not_called()
    # State file untouched
    assert (tmp_path / dev_server.STATE_FILE).exists()


# ---------------------------------------------------------------------------
# AC5 — Atomic state writes / partial-failure rollback
# ---------------------------------------------------------------------------

@patch("dev_server._is_port_in_use_for_host", return_value=False)
@patch("dev_server.subprocess.Popen")
def test_start_state_file_only_after_all_healthy(mock_popen, mock_port, tmp_path):
    # Two services. Service B fails health check.
    procs = [MagicMock(pid=100), MagicMock(pid=101)]
    for p in procs:
        p.poll.return_value = None
    mock_popen.side_effect = procs

    services = [
        {"name": "a", "command": "x", "port": 3000, "host": "localhost", "scheme": "http"},
        {"name": "b", "command": "y", "port": 3001, "host": "localhost", "scheme": "http"},
    ]

    def fake_wait(svc, proc, deadline):
        return (True, "") if svc["name"] == "a" else (False, "timeout")

    with patch("dev_server._wait_for_service", side_effect=fake_wait), \
         patch("dev_server._kill_one") as kill_mock:
        result = dev_server.cmd_start_with_services(tmp_path, services, profile=None)
    assert result["running"] is False
    # State file should NOT exist
    assert not (tmp_path / dev_server.STATE_FILE).exists()
    # A's kill was attempted (rollback)
    assert kill_mock.called


@patch("dev_server._is_port_in_use_for_host", return_value=False)
@patch("dev_server.subprocess.Popen")
def test_start_partial_failure_kills_started_in_reverse_no_state(mock_popen, mock_port, tmp_path):
    procs = [MagicMock(pid=100), MagicMock(pid=101), MagicMock(pid=102)]
    for p in procs:
        p.poll.return_value = None
    mock_popen.side_effect = procs

    # Three independent services start in one parallel layer. Popen runs for
    # all three; then health checks run sequentially. c fails. Rollback kills
    # all started procs in reverse (c, b, a) — Popen has already been called
    # on c, so its process MUST be reaped.
    services = [
        {"name": "a", "command": "x", "port": 3000, "host": "localhost", "scheme": "http"},
        {"name": "b", "command": "y", "port": 3001, "host": "localhost", "scheme": "http"},
        {"name": "c", "command": "z", "port": 3002, "host": "localhost", "scheme": "http"},
    ]

    def fake_wait(svc, proc, deadline):
        # a + b succeed; c fails.
        return (True, "") if svc["name"] in {"a", "b"} else (False, "timeout")

    kill_calls = []

    def fake_kill(record):
        kill_calls.append(record["name"])
        return {"name": record["name"], "pid": record["pid"], "killed": True}

    with patch("dev_server._wait_for_service", side_effect=fake_wait), \
         patch("dev_server._kill_one", side_effect=fake_kill):
        result = dev_server.cmd_start_with_services(tmp_path, services, profile=None)
    assert result["running"] is False
    # All Popened procs killed in reverse start order
    assert kill_calls == ["c", "b", "a"]
    assert not (tmp_path / dev_server.STATE_FILE).exists()


@patch("dev_server._is_port_in_use_for_host", return_value=False)
@patch("dev_server.subprocess.Popen")
def test_start_partial_failure_kill_exception_still_clears_state(mock_popen, mock_port, tmp_path):
    procs = [MagicMock(pid=100), MagicMock(pid=101)]
    for p in procs:
        p.poll.return_value = None
    mock_popen.side_effect = procs

    services = [
        {"name": "a", "command": "x", "port": 3000, "host": "localhost", "scheme": "http"},
        {"name": "b", "command": "y", "port": 3001, "host": "localhost", "scheme": "http"},
    ]

    def fake_wait(svc, proc, deadline):
        return (True, "") if svc["name"] == "a" else (False, "timeout")

    def boom(record):
        raise OSError("kill exploded")

    with patch("dev_server._wait_for_service", side_effect=fake_wait), \
         patch("dev_server._kill_one", side_effect=boom):
        result = dev_server.cmd_start_with_services(tmp_path, services, profile=None)
    assert result["running"] is False
    # No state file even though kill raised
    assert not (tmp_path / dev_server.STATE_FILE).exists()


@patch("dev_server._is_port_in_use_for_host", return_value=False)
@patch("dev_server.subprocess.Popen")
def test_save_state_atomic_replace_failure_no_orphan_tmp(mock_popen, mock_port, tmp_path, monkeypatch):
    procs = [MagicMock(pid=100)]
    for p in procs:
        p.poll.return_value = None
    mock_popen.side_effect = procs

    services = [
        {"name": "a", "command": "x", "port": 3000, "host": "localhost", "scheme": "http"},
    ]

    real_replace = dev_server.os.replace

    def boom_replace(src, dst):
        raise OSError("replace failed")

    with patch("dev_server._wait_for_service", return_value=(True, "")), \
         patch("dev_server._kill_one", return_value={"name": "a", "killed": True}), \
         patch("dev_server.os.replace", side_effect=boom_replace):
        result = dev_server.cmd_start_with_services(tmp_path, services, profile=None)
    assert result["running"] is False
    assert "error" in result
    # No final state file
    assert not (tmp_path / dev_server.STATE_FILE).exists()
    # No orphan .tmp
    tmps = list(tmp_path.glob(f"{dev_server.STATE_FILE}*"))
    assert tmps == []


# ---------------------------------------------------------------------------
# AC4 — cmd_stop semantics
# ---------------------------------------------------------------------------

def test_stop_kills_all_pids_in_reverse_order(tmp_path):
    state = {
        "version": 2,
        "profile": None,
        "services": [
            {"name": "a", "pid": 100, "port": 3000, "host": "localhost", "scheme": "http",
             "command": "x", "url": "http://localhost:3000", "ready_path": None,
             "ready_timeout_seconds": 60, "primary": True},
            {"name": "b", "pid": 101, "port": 3001, "host": "localhost", "scheme": "http",
             "command": "y", "url": "http://localhost:3001", "ready_path": None,
             "ready_timeout_seconds": 60, "primary": False},
        ],
    }
    dev_server._save_state(tmp_path, state)

    kill_calls = []
    def fake_kill(record):
        kill_calls.append(record["name"])
        return {"name": record["name"], "pid": record["pid"], "killed": True}

    with patch("dev_server._kill_one", side_effect=fake_kill):
        result = dev_server.cmd_stop(tmp_path)
    assert kill_calls == ["b", "a"]
    assert not (tmp_path / dev_server.STATE_FILE).exists()


def test_stop_mixed_stale_and_live_pids(tmp_path):
    state = {
        "version": 2,
        "services": [
            {"name": "a", "pid": 100, "port": 3000, "host": "localhost", "scheme": "http",
             "command": "x", "url": "http://localhost:3000", "ready_path": None,
             "ready_timeout_seconds": 60, "primary": True},
            {"name": "b", "pid": 101, "port": 3001, "host": "localhost", "scheme": "http",
             "command": "y", "url": "http://localhost:3001", "ready_path": None,
             "ready_timeout_seconds": 60, "primary": False},
        ],
    }
    dev_server._save_state(tmp_path, state)

    def fake_kill(record):
        # 'a' is stale (already dead), 'b' is live
        if record["name"] == "a":
            return {"name": "a", "pid": 100, "killed": False, "reason": "not_running"}
        return {"name": "b", "pid": 101, "killed": True}

    with patch("dev_server._kill_one", side_effect=fake_kill):
        result = dev_server.cmd_stop(tmp_path)
    assert not (tmp_path / dev_server.STATE_FILE).exists()
    # Both attempted
    assert len(result.get("services", [])) == 2


def test_stop_kill_raises_state_still_cleared(tmp_path):
    state = {
        "version": 2,
        "services": [
            {"name": "a", "pid": 100, "port": 3000, "host": "localhost", "scheme": "http",
             "command": "x", "url": "http://localhost:3000", "ready_path": None,
             "ready_timeout_seconds": 60, "primary": True},
            {"name": "b", "pid": 101, "port": 3001, "host": "localhost", "scheme": "http",
             "command": "y", "url": "http://localhost:3001", "ready_path": None,
             "ready_timeout_seconds": 60, "primary": False},
        ],
    }
    dev_server._save_state(tmp_path, state)

    def boom(record):
        if record["name"] == "b":
            raise RuntimeError("kill bug")
        return {"name": record["name"], "killed": True}

    with patch("dev_server._kill_one", side_effect=boom):
        # Must not raise out of cmd_stop; state must still be cleared.
        dev_server.cmd_stop(tmp_path)
    assert not (tmp_path / dev_server.STATE_FILE).exists()


# Windows taskkill specifics

def test_stop_windows_taskkill_not_found_treated_nonfatal(tmp_path, monkeypatch):
    monkeypatch.setattr(dev_server.os, "name", "nt")
    state = {
        "version": 2,
        "services": [
            {"name": "a", "pid": 100, "port": 3000, "host": "localhost", "scheme": "http",
             "command": "x", "url": "http://localhost:3000", "ready_path": None,
             "ready_timeout_seconds": 60, "primary": True},
        ],
    }
    dev_server._save_state(tmp_path, state)
    # Mock subprocess.run for taskkill returning non-zero (not found)
    completed = MagicMock(returncode=128, stdout="", stderr="not found")
    with patch("dev_server.subprocess.run", return_value=completed):
        # Should not raise
        result = dev_server.cmd_stop(tmp_path)
    assert not (tmp_path / dev_server.STATE_FILE).exists()


def test_stop_windows_taskkill_timeout_treated_nonfatal(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(dev_server.os, "name", "nt")
    state = {
        "version": 2,
        "services": [
            {"name": "a", "pid": 100, "port": 3000, "host": "localhost", "scheme": "http",
             "command": "x", "url": "http://localhost:3000", "ready_path": None,
             "ready_timeout_seconds": 60, "primary": True},
        ],
    }
    dev_server._save_state(tmp_path, state)
    with patch("dev_server.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="taskkill", timeout=10)):
        result = dev_server.cmd_stop(tmp_path)
    assert not (tmp_path / dev_server.STATE_FILE).exists()


# ---------------------------------------------------------------------------
# AC6 — state-file v1 read compat
# ---------------------------------------------------------------------------

def test_state_v1_read_compat(tmp_path):
    """Legacy v1 file (top-level pid/port, no version) → in-memory v2."""
    legacy = {"pid": 12345, "port": 3000, "command": "npm run dev", "profile": "supabase-nextjs"}
    (tmp_path / dev_server.STATE_FILE).write_text(json.dumps(legacy), encoding="utf-8")
    state = dev_server._load_state(tmp_path)
    assert state is not None
    assert state.get("version") == 2 or "services" in state
    services = state.get("services", [])
    assert len(services) == 1
    assert services[0]["pid"] == 12345
    assert services[0]["port"] == 3000
    assert services[0]["primary"] is True
    assert services[0]["name"] == "primary"


def test_state_v1_not_rewritten_on_read(tmp_path):
    legacy = {"pid": 12345, "port": 3000, "command": "npm run dev"}
    state_path = tmp_path / dev_server.STATE_FILE
    state_path.write_text(json.dumps(legacy), encoding="utf-8")
    dev_server._load_state(tmp_path)
    # File on disk is unchanged
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert "version" not in on_disk
    assert on_disk.get("pid") == 12345


def test_state_v2_round_trip(tmp_path):
    state = {
        "version": 2,
        "profile": "vite-hono",
        "services": [
            {"name": "backend", "pid": 100, "port": 3847, "host": "localhost",
             "scheme": "http", "command": "x", "url": "http://localhost:3847",
             "ready_path": "/api/diagnostics", "ready_timeout_seconds": 60,
             "primary": False},
            {"name": "frontend", "pid": 101, "port": 5173, "host": "localhost",
             "scheme": "http", "command": "y", "url": "http://localhost:5173",
             "ready_path": "/", "ready_timeout_seconds": 60, "primary": True},
        ],
    }
    dev_server._save_state(tmp_path, state)
    loaded = dev_server._load_state(tmp_path)
    assert loaded["version"] == 2
    assert len(loaded["services"]) == 2
    assert loaded["services"][1]["url"] == "http://localhost:5173"


# ---------------------------------------------------------------------------
# AC6 — Status output: top-level pid/url from primary
# ---------------------------------------------------------------------------

@patch("dev_server._is_pid_running", return_value=True)
@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_status_v1_state_top_level_pid_url_populated(mock_port, mock_pid, tmp_path):
    legacy = {"pid": 12345, "port": 3000, "command": "npm run dev"}
    (tmp_path / dev_server.STATE_FILE).write_text(json.dumps(legacy), encoding="utf-8")
    result = dev_server.cmd_status(tmp_path)
    assert result["running"] is True
    assert result["pid"] == 12345
    assert "url" in result and "3000" in result["url"]


def test_status_partial_alive_primary_dead_clears_top_level(tmp_path):
    """Primary dead, secondary alive → running=False AND top-level pid/url=None."""
    state = {
        "version": 2,
        "services": [
            {"name": "backend", "pid": 100, "port": 3847, "host": "localhost",
             "scheme": "http", "command": "x", "url": "http://localhost:3847",
             "ready_path": None, "ready_timeout_seconds": 60, "primary": False},
            {"name": "frontend", "pid": 101, "port": 5173, "host": "localhost",
             "scheme": "http", "command": "y", "url": "http://localhost:5173",
             "ready_path": None, "ready_timeout_seconds": 60, "primary": True},
        ],
    }
    dev_server._save_state(tmp_path, state)

    # backend alive; frontend (primary) dead
    def fake_pid_alive(pid):
        return pid == 100

    def fake_port(host, port):
        return port == 3847

    with patch("dev_server._is_pid_running", side_effect=fake_pid_alive), \
         patch("dev_server._is_port_in_use_for_host", side_effect=fake_port):
        result = dev_server.cmd_status(tmp_path)
    assert result["running"] is False
    # Critical: top-level pid/url MUST be None when primary is dead, even if
    # other services are alive (else callers see a usable URL that points to
    # nothing).
    assert result["pid"] is None
    assert result["url"] is None


@patch("dev_server._is_pid_running", return_value=True)
@patch("dev_server._is_port_in_use_for_host", return_value=True)
def test_status_v2_multi_service_top_level_from_primary(mock_port, mock_pid, tmp_path):
    state = {
        "version": 2,
        "services": [
            {"name": "backend", "pid": 100, "port": 3847, "host": "localhost",
             "scheme": "http", "command": "x", "url": "http://localhost:3847",
             "ready_path": "/api/diagnostics", "ready_timeout_seconds": 60,
             "primary": False},
            {"name": "frontend", "pid": 101, "port": 5173, "host": "localhost",
             "scheme": "http", "command": "y", "url": "http://localhost:5173",
             "ready_path": "/", "ready_timeout_seconds": 60, "primary": True},
        ],
    }
    dev_server._save_state(tmp_path, state)
    result = dev_server.cmd_status(tmp_path)
    assert result["running"] is True
    assert result["pid"] == 101  # primary's pid
    assert result["url"] == "http://localhost:5173"
    assert "services" in result
    assert len(result["services"]) == 2


# ---------------------------------------------------------------------------
# CLI compat regression guard
# ---------------------------------------------------------------------------

@patch("dev_server._is_port_in_use_for_host", return_value=False)
@patch("dev_server._wait_for_service", return_value=(True, ""))
@patch("dev_server.subprocess.Popen")
def test_cli_legacy_invocation_still_works(mock_popen, mock_wait, mock_port, tmp_path):
    """Regression guard: existing callers using `start --profile X --cwd Y`
    should produce a single-service start with legacy top-level keys."""
    proc = MagicMock(pid=99999)
    proc.poll.return_value = None
    mock_popen.return_value = proc
    result = dev_server.cmd_start(tmp_path, "supabase-nextjs")
    assert result["running"] is True
    assert "pid" in result
    assert "url" in result
    assert result.get("started_by_us") is True
    assert "services" in result  # additive, present even for single-service


# ---------------------------------------------------------------------------
# AC13 — --services-json CLI fallback
# ---------------------------------------------------------------------------

def test_cli_services_json_starts_inline_services(tmp_path, capsys):
    inline = json.dumps([
        {"name": "a", "command": "x", "port": 3000, "host": "localhost", "scheme": "http"}
    ])
    proc = MagicMock(pid=42)
    proc.poll.return_value = None
    with patch("dev_server.subprocess.Popen", return_value=proc), \
         patch("dev_server._is_port_in_use_for_host", return_value=False), \
         patch("dev_server._wait_for_service", return_value=(True, "")):
        # Drive via main()'s argv path
        rc = dev_server.main_with_args([
            "start", "--cwd", str(tmp_path), "--services-json", inline
        ])
    assert rc == 0


def test_cli_services_json_overrides_profile_with_warning(tmp_path, capsys):
    inline = json.dumps([
        {"name": "a", "command": "x", "port": 3000, "host": "localhost", "scheme": "http"}
    ])
    proc = MagicMock(pid=42)
    proc.poll.return_value = None
    with patch("dev_server.subprocess.Popen", return_value=proc), \
         patch("dev_server._is_port_in_use_for_host", return_value=False), \
         patch("dev_server._wait_for_service", return_value=(True, "")):
        rc = dev_server.main_with_args([
            "start", "--cwd", str(tmp_path),
            "--profile", "supabase-nextjs",
            "--services-json", inline,
        ])
    captured = capsys.readouterr()
    assert "overrides" in captured.err.lower() or "ignor" in captured.err.lower()


def test_cli_services_json_invalid_json_errors_cleanly(tmp_path, capsys):
    with patch("dev_server.subprocess.Popen") as mock_popen:
        rc = dev_server.main_with_args([
            "start", "--cwd", str(tmp_path),
            "--services-json", "{not valid json",
        ])
    assert rc != 0
    mock_popen.assert_not_called()


def test_cli_services_json_size_one_works(tmp_path):
    inline = json.dumps([
        {"name": "api", "command": "node server.js", "port": 4000, "host": "localhost",
         "scheme": "http"}
    ])
    proc = MagicMock(pid=42)
    proc.poll.return_value = None
    with patch("dev_server.subprocess.Popen", return_value=proc), \
         patch("dev_server._is_port_in_use_for_host", return_value=False), \
         patch("dev_server._wait_for_service", return_value=(True, "")):
        rc = dev_server.main_with_args([
            "start", "--cwd", str(tmp_path), "--services-json", inline
        ])
    assert rc == 0


def test_warning_emitted_only_once_per_invocation(tmp_path, capsys):
    """Both blocks in profile → exactly one stderr line, even if helpers re-enter."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "test-profile.json").write_text(json.dumps({
        "name": "test-profile",
        "dev_server": {"command": "old-cmd", "port": 9999, "ready_path": "/"},
        "services": [{"name": "a", "command": "x", "port": 3000, "host": "localhost", "scheme": "http"}],
    }), encoding="utf-8")
    proc = MagicMock(pid=42)
    proc.poll.return_value = None
    with patch("dev_server._profiles_dir", return_value=profiles_dir), \
         patch("dev_server.subprocess.Popen", return_value=proc), \
         patch("dev_server._is_port_in_use_for_host", return_value=False), \
         patch("dev_server._wait_for_service", return_value=(True, "")):
        dev_server.cmd_start(tmp_path, "test-profile")
    captured = capsys.readouterr()
    # Count occurrences of the warning text
    lines = [l for l in captured.err.splitlines() if "dev_server" in l and "ignor" in l.lower()]
    assert len(lines) == 1, captured.err


# ---------------------------------------------------------------------------
# AC11 — vite-hono profile loading
# ---------------------------------------------------------------------------

def test_profile_loader_reads_vite_hono_services_block():
    """Confirm shipped vite-hono.json profile has 2 services with expected shape."""
    repo = REPO  # shipwright repo root
    profile_path = repo / "profiles" / "vite-hono.json"
    if not profile_path.exists():
        # Ship-side path
        profile_path = repo.parent / "shared" / "profiles" / "vite-hono.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    services = profile["services"]
    assert len(services) == 2
    names = {s["name"] for s in services}
    assert names == {"backend", "frontend"}
    backend = next(s for s in services if s["name"] == "backend")
    frontend = next(s for s in services if s["name"] == "frontend")
    assert backend["port"] == 3847
    assert frontend["port"] == 5173
    assert frontend.get("depends_on") == ["backend"]
    assert frontend.get("primary") is True
    assert backend["ready_path"] == "/api/diagnostics"
    assert frontend["ready_path"] == "/"


def test_vite_hono_topo_order_is_backend_then_frontend():
    repo = REPO
    profile_path = repo / "profiles" / "vite-hono.json"
    if not profile_path.exists():
        profile_path = repo.parent / "shared" / "profiles" / "vite-hono.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    layers = dev_server._topo_sort(profile["services"])
    assert len(layers) == 2
    assert [s["name"] for s in layers[0]] == ["backend"]
    assert [s["name"] for s in layers[1]] == ["frontend"]
