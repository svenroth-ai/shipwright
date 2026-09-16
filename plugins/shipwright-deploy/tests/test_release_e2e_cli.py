"""End-to-end CLI verification for the coded release entry point
(F0.5 surface runner).

Deliberately unmocked, mirroring ``test_rollback_e2e_cli.py`` /
``test_smoke_e2e_cli.py``'s own pattern: a stub speaks the Jelastic REST wire
format over real HTTP, and ``release.py`` runs as a subprocess from an
unrelated working directory — the only way to prove across a process
boundary that a refusal never sends a request, and that an auto-rollback
really reaches the host.
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PLUGIN_ROOT.parent.parent
RELEASE = str(PLUGIN_ROOT / "scripts" / "lib" / "release.py")

TOKEN = "test-token-must-never-be-echoed"
DEAD_URL = "http://127.0.0.1:19999"


class _JelasticStub(http.server.BaseHTTPRequestHandler):
    """Minimal stand-in for the hosting API — records what it was asked."""

    def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
        params = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
        endpoint = self.path.strip("/")
        self.server.calls.append((endpoint, params))

        if endpoint.endswith("getprojects"):
            body = {"result": 0, "array": [dict(self.server.project)]}
        elif endpoint.endswith("editproject"):
            self.server.project = {**self.server.project, "branch": params.get("branch")}
            body = {"result": 0}
        else:
            body = {"result": 0}

        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def host():
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _JelasticStub)
    httpd.calls = []
    httpd.project = {
        "context": "ROOT", "type": "git", "branch": "main",
        "url": "https://example.invalid/app.git", "login": "shipwright-bot",
    }
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", httpd
    finally:
        httpd.shutdown()
        httpd.server_close()


def _run(args, base_url, cwd):
    env = {**os.environ, "JELASTIC_TOKEN": TOKEN, "JELASTIC_API_URL": base_url}
    completed = subprocess.run(
        [sys.executable, RELEASE, *args],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(cwd),
    )
    return completed, json.loads(completed.stdout)


def _write_test_results(project_root, *, unit_status):
    (project_root / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": unit_status}, "e2e": {"status": "passed"}}),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# AC02 — refuse a release on failing tests until a person confirms
# --------------------------------------------------------------------------

def test_the_cli_refuses_before_contacting_the_host_when_tests_are_failing(host, tmp_path):
    base_url, stub = host
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_test_results(project_root, unit_status="failed")

    completed, result = _run(
        ["--env-name", "dev-demo", "--repo-url", "https://example.invalid/app.git",
         "--branch", "main", "--project-root", str(project_root), "--target", "dev"],
        base_url, cwd=tmp_path,
    )

    assert stub.calls == []
    assert result["refused"] is True
    assert result["test_gate"] == "failing-unconfirmed"
    assert completed.returncode == 2


def test_the_cli_proceeds_once_a_person_confirms(host, tmp_path):
    base_url, stub = host
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_test_results(project_root, unit_status="failed")

    completed, result = _run(
        ["--env-name", "dev-demo", "--repo-url", "https://example.invalid/app.git",
         "--branch", "main", "--project-root", str(project_root), "--target", "dev",
         "--confirm-failing-tests"],
        base_url, cwd=tmp_path,
    )

    assert result["released"] is True
    assert any(e.endswith("update") for e, _ in stub.calls)
    assert completed.returncode == 0
    assert TOKEN not in completed.stdout
    assert TOKEN not in completed.stderr


# --------------------------------------------------------------------------
# AC05 — auto-rollback on smoke-test failure
# --------------------------------------------------------------------------

def test_the_cli_automatically_rolls_back_when_the_smoke_check_fails(host, tmp_path):
    base_url, stub = host
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_test_results(project_root, unit_status="passed")

    completed, result = _run(
        ["--env-name", "dev-demo", "--repo-url", "https://example.invalid/app.git",
         "--branch", "feature-branch", "--project-root", str(project_root), "--target", "dev",
         "--smoke-url", DEAD_URL, "--smoke-timeout", "1", "--smoke-max-wait", "1"],
        base_url, cwd=tmp_path,
    )

    assert result["released"] is False
    assert result["smoke_checked"] is True
    assert result["rollback_triggered"] is True
    assert result["rollback"]["target_ref"] == "main"
    assert completed.returncode == 1

    edits = [params for endpoint, params in stub.calls if endpoint.endswith("editproject")]
    assert edits[-1]["branch"] == "main"

    history_path = project_root / ".shipwright" / "deploy" / "rollback-history.jsonl"
    entry = json.loads(history_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry["invocation"] == "auto"
    assert TOKEN not in completed.stdout
    assert TOKEN not in completed.stderr


def test_the_cli_skips_smoke_verification_when_no_url_given(host, tmp_path):
    base_url, stub = host
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_test_results(project_root, unit_status="passed")

    completed, result = _run(
        ["--env-name", "dev-demo", "--repo-url", "https://example.invalid/app.git",
         "--branch", "main", "--project-root", str(project_root), "--target", "dev"],
        base_url, cwd=tmp_path,
    )

    assert result["released"] is True
    assert result["smoke_checked"] is False
    assert completed.returncode == 0
    assert not (project_root / ".shipwright" / "deploy" / "rollback-history.jsonl").exists()
