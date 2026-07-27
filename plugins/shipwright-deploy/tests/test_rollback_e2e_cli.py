"""End-to-end CLI verification for the hosting way back (F0.5 surface runner).

Deliberately unmocked. A stub speaks the Jelastic REST wire format over real
HTTP, ``JELASTIC_API_URL`` points at it, and the CLIs run as subprocesses from
an unrelated working directory. That is the only way to prove across a process
boundary that the requested version was actually *sent* — and it simultaneously
proves the shared-module import resolves from a normal invocation, which an
in-process unit test cannot.
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
ROLLBACK = str(PLUGIN_ROOT / "scripts" / "lib" / "rollback.py")
JELASTIC_PROFILE = str(REPO_ROOT / "shared" / "profiles" / "deploy" / "jelastic.json")

TOKEN = "test-token-must-never-be-echoed"


class _JelasticStub(http.server.BaseHTTPRequestHandler):
    """Minimal stand-in for the hosting API that records what it was asked.

    State lives on the SERVER instance, never on this class: a handler class is
    shared by every server in the process, so class attributes would make two
    concurrently-running tests overwrite each other's recorded calls the moment
    the suite is run under xdist.
    """

    def do_POST(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
        params = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
        endpoint = self.path.strip("/")
        self.server.calls.append((endpoint, params))

        if endpoint in self.server.fail:
            body = {"result": 4, "error": f"{endpoint} refused by the stub"}
        elif endpoint.endswith("getprojects"):
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
    """Start the stub; yields (base_url, the server carrying the recorded calls)."""
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _JelasticStub)
    httpd.calls = []
    httpd.fail = set()
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


def _run(script, args, base_url=None, cwd=None):
    env = {**os.environ, "JELASTIC_TOKEN": TOKEN}
    if base_url:
        env["JELASTIC_API_URL"] = base_url
    completed = subprocess.run(
        [sys.executable, script, *args],
        capture_output=True, text=True, encoding="utf-8", env=env,
        cwd=str(cwd) if cwd else None,
    )
    return completed, json.loads(completed.stdout)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   capture_output=True, text=True, check=True)


@pytest.fixture
def app_repo(tmp_path):
    """A project whose migrations are level with tag `v1`."""
    root = tmp_path / "app"
    (root / "supabase" / "migrations").mkdir(parents=True)
    _git(tmp_path, "init", "-q", "app")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    (root / "supabase" / "migrations" / "0001_init.sql").write_text("create table t();")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "first")
    _git(root, "tag", "v1")
    return root


# --------------------------------------------------------------------------
# AC1 / AC11 — the requested version really is sent, over the wire
# --------------------------------------------------------------------------

def test_the_cli_sends_the_requested_version_to_the_host(host, app_repo, tmp_path):
    base_url, stub = host

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo), "--profile", JELASTIC_PROFILE],
        base_url, cwd=tmp_path,  # unrelated cwd: proves the shared import resolves
    )

    endpoints = [e.rsplit("/", 1)[-1] for e, _ in stub.calls]
    assert endpoints == ["getprojects", "editproject", "update", "getprojects"]

    edit = next(params for endpoint, params in stub.calls if endpoint.endswith("editproject"))
    assert edit["branch"] == "v1"
    assert edit["url"] == "https://example.invalid/app.git"  # AC11: config survived
    assert edit["login"] == "shipwright-bot"

    assert result["success"] is True
    assert result["ref_verified"] == "confirmed"
    assert result["previous_ref"] == "main"
    assert completed.returncode == 0


def test_the_token_never_reaches_stdout(host, app_repo, tmp_path):
    base_url, _ = host

    completed, _ = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo)],
        base_url, cwd=tmp_path,
    )

    assert TOKEN not in completed.stdout
    assert TOKEN not in completed.stderr


# --------------------------------------------------------------------------
# AC4 / AC9 — stored data that moved on refuses, and touches nothing
# --------------------------------------------------------------------------

def test_drifted_data_refuses_without_contacting_the_host(host, app_repo, tmp_path):
    base_url, stub = host
    (app_repo / "supabase" / "migrations" / "0002_add_column.sql").write_text("alter table t;")
    _git(app_repo, "add", "-A")
    _git(app_repo, "commit", "-qm", "second")

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo), "--profile", JELASTIC_PROFILE],
        base_url, cwd=tmp_path,
    )

    assert stub.calls == []
    assert result["success"] is False
    assert result["mutated"] is False
    assert result["halt"] is False
    assert result["data_drift"]["status"] == "drifted"
    assert "0002_add_column.sql" in result["error"]
    assert "down-migration" in result["error"]  # the target's declared strategy
    assert "nothing on the hosting target was changed" in result["operator_message"].lower()
    assert completed.returncode == 1


def test_acknowledging_the_drift_proceeds(host, app_repo, tmp_path):
    base_url, stub = host
    (app_repo / "supabase" / "migrations" / "0002_add_column.sql").write_text("alter table t;")
    _git(app_repo, "add", "-A")
    _git(app_repo, "commit", "-qm", "second")

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo), "--ack-data-drift"],
        base_url, cwd=tmp_path,
    )

    assert [e for e, _ in stub.calls]
    assert result["success"] is True
    assert result["data_drift"]["drifted"] is True
    assert completed.returncode == 0


# --------------------------------------------------------------------------
# AC9 / AC12 — a way back that fails names the state and stops
# --------------------------------------------------------------------------

def test_a_failed_update_halts_with_a_distinct_exit_code(host, app_repo, tmp_path):
    base_url, stub = host
    stub.fail = {"environment/vcs/rest/update"}

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo)],
        base_url, cwd=tmp_path,
    )

    assert completed.returncode == 3
    assert result["success"] is False
    assert result["halt"] is True
    assert result["mutated"] is True
    assert result["previous_ref"] == "main"
    assert "STOP" in result["operator_message"]
    assert "not verify which version is running" in result["operator_message"]


def test_a_failed_pin_never_issues_the_update(host, app_repo, tmp_path):
    base_url, stub = host
    stub.fail = {"environment/vcs/rest/editproject"}

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo)],
        base_url, cwd=tmp_path,
    )

    assert not any(e.endswith("update") for e, _ in stub.calls)
    assert completed.returncode == 3
    assert result["halt"] is True


def test_an_invalid_ref_is_rejected_before_anything_is_contacted(host, app_repo, tmp_path):
    base_url, stub = host

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1; touch pwned",
         "--project-root", str(app_repo)],
        base_url, cwd=tmp_path,
    )

    assert stub.calls == []
    assert completed.returncode == 1
    assert result["mutated"] is False
    assert not (app_repo / "pwned").exists()


def test_a_stop_only_clone_rollback_says_so(host, tmp_path):
    """AC10 — the CLI must report stopping as stopping, never as restoring."""
    base_url, _ = host

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "prod-demo", "--strategy", "clone",
         "--clone-name", "prod-demo-backup"],
        base_url, cwd=tmp_path,
    )

    assert result["success"] is True
    assert result["restored"] is False
    assert completed.returncode == 0
