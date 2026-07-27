"""End-to-end CLI verification for the liveness check (F0.5 surface runner).

Runs ``shared/scripts/smoke_test.py`` as a subprocess from an unrelated working
directory against a real local HTTP server. Besides the polling behaviour this
proves the bare ``deploy_profile`` import resolves from a normal invocation —
something no in-process unit test can establish.
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SMOKE = str(REPO_ROOT / "shared" / "scripts" / "smoke_test.py")
JELASTIC_PROFILE = str(REPO_ROOT / "shared" / "profiles" / "deploy" / "jelastic.json")

DEAD_URL = "http://127.0.0.1:19999"


class _AliveApp(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *args):
        pass


@pytest.fixture
def live_app():
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _AliveApp)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _run(args, cwd):
    completed = subprocess.run(
        [sys.executable, SMOKE, *args],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ}, cwd=str(cwd),
    )
    return completed, json.loads(completed.stdout)


# --------------------------------------------------------------------------
# AC5 / AC7 / AC8 — the liveness CLI honours the target's deadline
# --------------------------------------------------------------------------

def test_the_liveness_cli_reads_the_whole_policy_from_the_target_profile(live_app, tmp_path):
    """AC7 — no flags at all: every value comes from the target's own profile."""
    completed, result = _run(["--url", live_app, "--profile", JELASTIC_PROFILE], tmp_path)

    assert result["success"] is True
    assert result["deadline_seconds"] == 60
    assert set(result["policy_source"].values()) == {"profile:jelastic"}
    assert completed.returncode == 0


def test_the_liveness_cli_keeps_asking_until_the_deadline(tmp_path):
    """AC5 / AC7 — it polls, and an explicit flag overrides only its own field."""
    completed, result = _run(
        ["--url", DEAD_URL, "--profile", JELASTIC_PROFILE,
         "--timeout", "1", "--poll-interval", "1", "--max-wait", "5"],
        tmp_path,
    )

    assert result["success"] is False
    assert result["deadline_seconds"] == 5
    assert result["policy_source"]["max_wait"] == "cli"
    assert result["policy_source"]["health_path"] == "profile:jelastic"
    assert result["attempts"] >= 2
    assert completed.returncode == 1


def test_the_liveness_cli_without_a_deadline_asks_once(tmp_path):
    """AC8 — the /shipwright-test call site keeps its single fast attempt."""
    started = time.monotonic()
    _, result = _run(["--url", DEAD_URL, "--timeout", "2"], tmp_path)
    elapsed = time.monotonic() - started

    assert result["attempts"] == 1
    assert result["deadline_seconds"] is None
    assert elapsed < 15


def test_an_unreadable_profile_is_a_usage_error_not_a_silent_default(tmp_path):
    completed, result = _run(
        ["--url", DEAD_URL, "--profile", str(tmp_path / "nope.json")], tmp_path)

    assert result["success"] is False
    assert "not found" in result["error"]
    assert completed.returncode == 2
