"""Tests for the shared smoke_test module.

Item (3) of the hosting-rollback work: the liveness check used to ask once with
a ten-second limit, so an application taking fifteen seconds to start was
reported as a failed release and triggered an unnecessary rollback. The polling
tests below run against a **real** local HTTP server that starts answering late
— a mocked clock would not have caught the deadline-overshoot cases.
"""

import http.server
import threading
import time

import pytest
from smoke_test import MIN_ATTEMPT_SECONDS, run_smoke_test


class _LateStarter(http.server.BaseHTTPRequestHandler):
    """Answers 503 until ``ready_at``, then 200 — a slow-booting application."""

    ready_at = 0.0
    hits = 0
    health_delay = 0.0

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        type(self).hits += 1
        if self.path.startswith("/api/health") and type(self).health_delay:
            time.sleep(type(self).health_delay)
        code = 200 if time.monotonic() >= type(self).ready_at else 503
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *args):  # keep the test output clean
        pass


@pytest.fixture
def late_server():
    """Start a server that becomes healthy ``after`` seconds from now."""
    servers = []

    def _start(after: float, health_delay: float = 0.0):
        _LateStarter.ready_at = time.monotonic() + after
        _LateStarter.hits = 0
        _LateStarter.health_delay = health_delay
        httpd = http.server.HTTPServer(("127.0.0.1", 0), _LateStarter)
        servers.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    yield _start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


# --------------------------------------------------------------------------
# Behaviour preserved from before polling existed
# --------------------------------------------------------------------------

def test_smoke_test_unreachable():
    """Test against unreachable URL — should fail gracefully."""
    result = run_smoke_test("http://localhost:19999", timeout=2)
    assert result["success"] is False
    assert result["error"] is not None
    assert result["url"] == "http://localhost:19999"


def test_smoke_test_invalid_url():
    """Invalid URL — should fail gracefully."""
    result = run_smoke_test("not-a-url", timeout=2)
    assert result["success"] is False
    assert result["error"] is not None


def test_smoke_test_result_structure():
    """Verify result has all expected fields."""
    result = run_smoke_test("http://localhost:19999", timeout=1)
    for key in ("success", "url", "status_code", "response_time_ms",
                "health_check", "error", "attempts", "waited_ms", "deadline_seconds"):
        assert key in result


# --------------------------------------------------------------------------
# AC8 — callers with no deadline keep today's single attempt
# --------------------------------------------------------------------------

def test_without_a_deadline_exactly_one_request_is_made(late_server):
    """The /shipwright-test call site passes no deadline and must not slow down."""
    url = late_server(after=30)  # would never become healthy in this test's lifetime

    started = time.monotonic()
    result = run_smoke_test(url, timeout=2)
    elapsed = time.monotonic() - started

    assert result["success"] is False
    assert result["attempts"] == 1
    assert _LateStarter.hits == 1
    assert result["deadline_seconds"] is None
    assert elapsed < 5


# --------------------------------------------------------------------------
# AC5 / AC6 — poll to the deadline, then fail with evidence
# --------------------------------------------------------------------------

def test_a_slow_start_is_waited_out_rather_than_called_a_failed_release(late_server):
    """AC5 — the fifteen-second start-up that used to trigger a rollback."""
    url = late_server(after=2)

    result = run_smoke_test(url, timeout=2, poll_interval=1, max_wait=20)

    assert result["success"] is True
    assert result["attempts"] > 1
    assert result["status_code"] == 200
    assert result["deadline_seconds"] == 20


def test_an_exhausted_deadline_fails_and_records_the_evidence(late_server):
    """AC6 — a real failure still fails, and says how hard it tried."""
    url = late_server(after=60)

    result = run_smoke_test(url, timeout=1, poll_interval=1, max_wait=3)

    assert result["success"] is False
    assert result["attempts"] >= 2
    assert result["deadline_seconds"] == 3
    assert result["waited_ms"] >= 0
    assert result["error"]


# --------------------------------------------------------------------------
# AC14 — the deadline is never overshot
# --------------------------------------------------------------------------

def test_the_deadline_is_not_overshot_by_a_long_request_timeout():
    """A 30s per-request timeout must never bound a 2s deadline."""
    started = time.monotonic()
    result = run_smoke_test("http://10.255.255.1:19999", timeout=30,
                            poll_interval=1, max_wait=2)
    elapsed = time.monotonic() - started

    assert result["success"] is False
    assert elapsed < 4, f"overshot the 2s deadline by too much ({elapsed:.1f}s)"
    assert result["waited_ms"] <= 2 * 1000 + 500


def test_a_deadline_shorter_than_one_request_still_asks_exactly_once():
    """Only the FIRST attempt may straddle the deadline, and by at most 1s.

    A check that never asks at all would be worse than a short overrun, so
    `max_wait=0` still makes one request — bounded by MIN_ATTEMPT_SECONDS, not
    by the 30-second request timeout.
    """
    started = time.monotonic()
    result = run_smoke_test("http://10.255.255.1:19999", timeout=30,
                            poll_interval=1, max_wait=0)
    elapsed = time.monotonic() - started

    assert result["attempts"] == 1
    assert elapsed <= MIN_ATTEMPT_SECONDS + 1.5, f"ran for {elapsed:.1f}s"


def test_the_health_probe_counts_against_the_same_deadline(late_server):
    """A slow /api/health must not extend the wait past the target's deadline."""
    url = late_server(after=0, health_delay=10)

    started = time.monotonic()
    result = run_smoke_test(url, timeout=30, health_path="/api/health",
                            poll_interval=1, max_wait=2)
    elapsed = time.monotonic() - started

    assert result["success"] is True          # liveness answered immediately
    assert elapsed < 6, f"the health probe ran on the 30s timeout ({elapsed:.1f}s)"


@pytest.mark.parametrize("kwargs", [
    {"timeout": -1},
    {"poll_interval": 0, "max_wait": 5},
    {"poll_interval": -2, "max_wait": 5},
    {"max_wait": -5},
])
def test_nonsensical_durations_are_rejected(kwargs):
    with pytest.raises(ValueError):
        run_smoke_test("http://localhost:19999", **kwargs)
