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
    # rollback.py's --invocation is required with no default (Tier-3 PR
    # review round 7) — default it to "auto" here for tests that aren't
    # specifically exercising the flag, same as this file's own
    # --project-root convention.
    if script == ROLLBACK and "--invocation" not in args:
        args = [*args, "--invocation", "auto"]
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

@pytest.mark.covers("FR-01.08/AC06")
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

@pytest.mark.covers("FR-01.08/AC07")
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


@pytest.mark.covers("FR-01.08/AC07")
@pytest.mark.covers("FR-01.08/AC15")
def test_acknowledging_the_drift_proceeds(host, app_repo, tmp_path):
    """Spec FR-01.08/AC15: once the rollback *completes*, the running code
    came back but `data_drift.drifted` is still reported True — the code
    path never silently marks the data as reverted too. This binds the AC's
    own testable clause precisely: "so nobody assumes the data went back
    too" is a claim about what the tool *reports*, not a claim this module
    could make about a live database it never talks to (`rollback.py`
    imports only `data_drift`, `rollback_report`, `deploy_profile` — no
    database/migration-execution client exists in this code path at all, so
    there is no runtime call to spy on for "did it touch the data"; the
    guarantee is architectural, not decision-based, and a git-checkout of
    the CODE tree back to `v1` legitimately also reverts the migration
    *file* in the working tree — that is not the "data" this AC means, and
    asserting the file is unchanged would conflate code rollback with data
    mutation)."""
    base_url, stub = host
    (app_repo / "supabase" / "migrations" / "0002_add_column.sql").write_text("alter table t;")
    _git(app_repo, "add", "-A")
    _git(app_repo, "commit", "-qm", "second")

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo), "--ack-data-drift",
         "--override-reason", "operator accepted the data-tier gap for this incident"],
        base_url, cwd=tmp_path,
    )

    assert [e for e, _ in stub.calls]
    assert result["success"] is True
    assert result["data_drift"]["drifted"] is True
    assert result["override_reason"] == "operator accepted the data-tier gap for this incident"
    assert completed.returncode == 0


# --------------------------------------------------------------------------
# AC9 / AC12 — a way back that fails names the state and stops
# --------------------------------------------------------------------------

@pytest.mark.covers("FR-01.08/AC13")
@pytest.mark.covers("FR-01.08/AC14")
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


@pytest.mark.covers("FR-01.08/AC14")
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


@pytest.mark.covers("FR-01.08/AC14")
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


@pytest.mark.covers("FR-01.08/AC10")
def test_a_stop_only_clone_rollback_says_so(host, tmp_path):
    """AC10 — the CLI must report stopping as stopping, never as restoring."""
    base_url, _ = host

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "prod-demo", "--strategy", "clone",
         "--clone-name", "prod-demo-backup", "--project-root", str(tmp_path)],
        base_url, cwd=tmp_path,
    )

    assert result["success"] is True
    assert result["restored"] is False
    assert completed.returncode == 0


# --------------------------------------------------------------------------
# Ledger FR-01.08 #5 / #7 — overriding the stored-data offer needs a written
# reason, and every invocation is recorded (rollback-history.jsonl).
# --------------------------------------------------------------------------

def _read_history(project_root: Path) -> list[dict]:
    path = project_root / ".shipwright" / "deploy" / "rollback-history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_ack_without_a_reason_is_refused(host, app_repo, tmp_path):
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

    assert stub.calls == []
    assert result["success"] is False
    assert "override needs a written reason" in result["error"]
    assert completed.returncode == 1


def test_every_invocation_is_recorded_to_the_rollback_history(host, app_repo, tmp_path):
    base_url, stub = host

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo), "--profile", JELASTIC_PROFILE,
         "--invocation", "manual"],
        base_url, cwd=tmp_path,
    )
    assert completed.returncode == 0

    history = _read_history(app_repo)
    assert len(history) == 1
    entry = history[0]
    assert entry["invocation"] == "manual"
    assert entry["success"] is True
    assert entry["env_name"] == "dev-demo"
    assert entry["target_ref"] == "v1"
    assert "recorded_at" in entry


def test_a_refused_invocation_is_also_recorded(host, app_repo, tmp_path):
    base_url, _ = host

    completed, _ = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1; touch pwned",
         "--project-root", str(app_repo)],
        base_url, cwd=tmp_path,
    )
    assert completed.returncode == 1

    history = _read_history(app_repo)
    assert len(history) == 1
    assert history[0]["success"] is False
    assert history[0]["invocation"] == "auto"  # this test's own --invocation auto (helper default)


def test_an_unreadable_profile_is_still_recorded(host, app_repo, tmp_path):
    """External review (round 1): a --profile load failure used to `return`
    before reaching `rollback_audit.record()` — a pre-flight refusal that
    reopened the exact "every invocation is recorded" gap #7 closes. main()
    now routes it through the same `result` -> `record()` -> `exit_code()`
    path as every other branch.
    """
    base_url, stub = host
    missing_profile = str(tmp_path / "does-not-exist.json")

    completed, result = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo), "--profile", missing_profile],
        base_url, cwd=tmp_path,
    )

    assert stub.calls == []
    assert result["success"] is False
    assert completed.returncode == 1

    history = _read_history(app_repo)
    assert len(history) == 1
    assert history[0]["success"] is False
    assert history[0]["env_name"] == "dev-demo"


def test_the_real_rollback_and_smoke_producers_satisfy_the_real_consumer_check(
    host, app_repo, tmp_path
):
    """ADR-024 round-trip probe for FR-01.08 #8's proves-alive half: every
    other test on ``deploy_checks.check_manual_rollback_proves_alive``
    hand-writes both a rollback-history entry and a smoke-test-result
    fixture. This one runs the real ``rollback.py --invocation manual`` CLI
    AND the real ``smoke_test.py --output`` CLI against the same project
    root, then calls the real consumer function — proving all three
    independently-maintained pieces (two producers, one plugin-local, one
    shared, and a shared consumer) actually agree on the file paths and
    field names, AND that a liveness check reporting the app genuinely alive
    is what makes the check pass — not merely a check having run
    (self-review, e4-checks-deploy-changelog).
    """
    base_url, _ = host

    completed, _ = _run(
        ROLLBACK,
        ["--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
         "--project-root", str(app_repo), "--profile", JELASTIC_PROFILE,
         "--invocation", "manual"],
        base_url, cwd=tmp_path,
    )
    assert completed.returncode == 0

    alive = http.server.HTTPServer(("127.0.0.1", 0), _AliveApp)
    threading.Thread(target=alive.serve_forever, daemon=True).start()
    try:
        smoke_out = app_repo / ".shipwright" / "deploy" / "smoke-test-result.json"
        smoke = subprocess.run(
            [sys.executable, str(REPO_ROOT / "shared" / "scripts" / "smoke_test.py"),
             "--url", f"http://127.0.0.1:{alive.server_address[1]}",
             "--timeout", "1", "--output", str(smoke_out)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(tmp_path),
        )
    finally:
        alive.shutdown()
        alive.server_close()
    assert smoke.returncode == 0
    assert smoke_out.exists()

    sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
    from tools.verifiers.deploy_checks import check_manual_rollback_proves_alive

    result = check_manual_rollback_proves_alive(app_repo)
    assert result.ok is True


class _AliveApp(http.server.BaseHTTPRequestHandler):
    """Minimal GET-only health endpoint — ``smoke_test.py`` issues a GET,
    which ``_JelasticStub`` above (POST-only) does not answer."""

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, *args):
        pass
