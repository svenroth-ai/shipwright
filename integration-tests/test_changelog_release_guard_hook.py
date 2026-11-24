"""Integration coverage (cross_component): the changelog plugin's release guard composes with the release CLI and its hooks.json.

The diff touches ``plugins/shipwright-changelog/hooks/hooks.json`` and a hook script, so ``check_integration_coverage`` wants
a test that proves two pieces COMPOSE. Here: (1) the command registered in ``hooks.json`` names the script that exists, runs
``uv run --no-project`` (a PreToolUse ``Bash`` hook fires on every Bash call) and sits beside, not instead of, the Stop chain;
(2) the real ``release.py`` outputs -- the run state ``prepare`` leaves in the git directory and the record
``commit-and-tag`` writes -- are what the hook reads: blocked with the state alone, allowed once the record names HEAD, and an
ordinary push is never blocked.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "shipwright-changelog"
HOOKS_JSON = PLUGIN / "hooks" / "hooks.json"
pytestmark = pytest.mark.covers("FR-01.09/AC01")
VERSION = "2.0.0"


def _registered() -> list[str]:
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    return [h["command"] for e in data["hooks"]["PreToolUse"] if e.get("matcher") == "Bash|PowerShell" for h in e["hooks"]]


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _script_path() -> Path:
    (command,) = [c for c in _registered() if "release_guard.py" in c]
    found = re.search(r'"\$\{CLAUDE_PLUGIN_ROOT\}/([^"]+release_guard\.py)"', command)
    assert found, command
    return PLUGIN / found.group(1)


def _run(command: str, cwd: Path) -> dict | None:
    body = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}
    done = subprocess.run([sys.executable, str(_script_path())], input=json.dumps(body), capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)["hookSpecificOutput"] if done.stdout.strip() else None


def test_hooks_json_registers_the_guard_robustly_next_to_the_stop_chain():
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    (command,) = _registered()
    assert command.startswith("uv run --no-project ") and _script_path().is_file()
    assert {"SessionStart", "Stop", "PostToolUse", "PreToolUse"} <= set(data["hooks"])


@pytest.fixture
def repo(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("SHIPWRIGHT_RELEASE_GUARD", raising=False)
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "origin", "main")
    return work


def _produce(repo: Path, call: str, payload: dict) -> None:
    """Run one of the plugin's own producers in a fresh interpreter: this root's ``lib`` package is the shared one, and the plugin's
    ``lib`` cannot be imported next to it (one cached ``lib`` per process, ADR-044)."""
    code = f"import json, sys; from pathlib import Path; from lib import release_commit, release_runstate; {call}"
    done = subprocess.run([sys.executable, "-c", code, str(repo), json.dumps(payload)], cwd=PLUGIN / "scripts", capture_output=True,
                          text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr


def test_the_guard_reads_what_the_release_cli_writes(repo):
    assert _run("git push --tags origin main", repo) is None  # no release running: today's behaviour
    now = datetime.now(timezone.utc)
    _produce(repo, "release_runstate.save(Path(sys.argv[1]), json.loads(sys.argv[2]))",
             {"schema": 1, "version": VERSION, "release_date": f"{now:%Y-%m-%d}", "run_id": "r", "created_at": now.isoformat(timespec="seconds")})
    for command in ("git push --tags origin main", "git push origin HEAD", "gh pr merge", "gh release create v2.0.0"):
        out = _run(command, repo)
        assert out and out["permissionDecision"] == "deny", command
    _git(repo, "checkout", "-b", "feature")
    assert _run("git push -u origin feature", repo) is None  # an ordinary push, even mid-release
    _git(repo, "checkout", "main")
    _produce(repo, "release_commit.write_state(Path(sys.argv[1]), json.loads(sys.argv[2]))",
             {"schema": 1, "version": VERSION, "tag": f"v{VERSION}", "commit": _git(repo, "rev-parse", "HEAD"),
              "checks_passed": ["commit", "tag"], "tagged_at": now.isoformat(timespec="seconds")})
    assert _run("git push --tags origin main", repo) is None
    assert _run("gh pr merge", repo) is None
