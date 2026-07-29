"""`tools.main_health` — the assembly and its exit-code contract.

@FR-01.19

The pure core is tested elsewhere. What this file pins is the shell's behaviour
around it, and one property above all: **a host call that fails must never
produce exit 0.** The tool is consulted at iterate start and again before a
merge is armed; a `gh` that is absent, rate-limited or unauthenticated has to
say so, because the only thing worse than no health check is one that answers
"green" when it means "I could not look".

The second property is cost. The green path must stay ONE API call — that is
what makes it affordable at both hooks, and a regression there would be
invisible until somebody's rate limit ran out.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools import main_health as tool  # noqa: E402
from tools import main_health_gh as gh  # noqa: E402

TIP = "a" * 40
OLD = "b" * 40


def _run(sha=TIP, conclusion="success", status="completed", workflow="CI", db_id=1):
    return {
        "databaseId": db_id, "workflowName": workflow, "headSha": sha,
        "headBranch": "main", "event": "push", "status": status,
        "conclusion": conclusion, "createdAt": "2026-07-28T10:00:00Z",
        "url": f"https://x/{db_id}",
    }


@pytest.fixture
def host(monkeypatch):
    """A fake host. Every call is counted so cost can be asserted."""
    calls: list[str] = []

    def _series(cwd, ref, window):
        calls.append("git log")
        return [{"sha": TIP, "subject": "tip (#2)"}, {"sha": OLD, "subject": "old (#1)"}]

    monkeypatch.setattr(gh, "commit_series", _series)
    monkeypatch.setattr(gh, "workflow_files", lambda cwd: [
        "ci.yml", "security.yml", "codeql.yml", "bloat-check.yml"])
    monkeypatch.setattr(gh, "list_runs", lambda cwd, b, limit: (
        calls.append("gh run list") or [_run()]))
    return calls


def _exit(argv=None):
    return tool.main(argv or ["--project-root", str(REPO_ROOT)])


# --------------------------------------------------------------------------
# the green path
# --------------------------------------------------------------------------

def test_green_exits_zero(host, capsys):
    assert _exit() == 0
    assert '"status": "green"' in capsys.readouterr().out


def test_the_green_path_costs_exactly_one_api_call(host, capsys):
    _exit()
    capsys.readouterr()
    assert host.count("gh run list") == 1
    assert [c for c in host if c.startswith("gh")] == ["gh run list"]


# --------------------------------------------------------------------------
# failing honestly — the property the whole tool rests on
# --------------------------------------------------------------------------

def test_a_gh_failure_is_unknown_not_green(host, monkeypatch, capsys):
    def _boom(cwd, branch, limit):
        raise gh.ShellError("gh: command not found")

    monkeypatch.setattr(gh, "list_runs", _boom)
    assert _exit() == 4
    out = capsys.readouterr().out
    assert '"status": "unknown"' in out
    assert "gh: command not found" in out


def test_a_git_failure_is_unknown_and_names_git(host, monkeypatch, capsys):
    def _boom(cwd, ref, window):
        raise gh.ShellError("not a git repository")

    monkeypatch.setattr(gh, "commit_series", _boom)
    assert _exit() == 4
    assert '"source": "git"' in capsys.readouterr().out


def test_no_runs_at_all_is_unknown(host, monkeypatch, capsys):
    monkeypatch.setattr(gh, "list_runs", lambda cwd, b, limit: [])
    assert _exit() == 4
    assert '"status": "unknown"' in capsys.readouterr().out


def test_a_still_running_tip_exits_three(host, monkeypatch, capsys):
    monkeypatch.setattr(gh, "list_runs", lambda cwd, b, limit: [
        _run(status="in_progress", conclusion=None)])
    assert _exit() == 3
    capsys.readouterr()


# --------------------------------------------------------------------------
# the red path
# --------------------------------------------------------------------------

@pytest.fixture
def red_host(host, monkeypatch):
    monkeypatch.setattr(gh, "list_runs", lambda cwd, b, limit: [
        _run(sha=TIP, conclusion="failure", db_id=2),
        _run(sha=OLD, conclusion="success", db_id=1),
    ])
    monkeypatch.setattr(gh, "repo_slug", lambda cwd: ("svenroth-ai", "shipwright"))
    monkeypatch.setattr(gh, "failed_steps", lambda cwd, rid, fc: [
        {"job": "Python (lint + test)", "step": "Run shared tests"}])
    monkeypatch.setattr(gh, "failed_log", lambda cwd, rid:
                        "job\tstep\t2026 E   assert 6 == 5\n")
    monkeypatch.setattr(gh, "pr_for_commit",
                        lambda cwd, o, n, sha, subj: ("c" * 40, 2, None))
    monkeypatch.setattr(gh, "commits_between", lambda cwd, base, bad: [
        {"sha": "d" * 40, "subject": "the partner"}])
    monkeypatch.setattr(gh, "list_prs", lambda cwd: [])
    monkeypatch.setattr(gh, "list_branch_refs", lambda cwd, o, n: [])
    return host


def test_red_exits_two_and_names_the_first_bad_commit(red_host, capsys):
    assert _exit() == 2
    out = capsys.readouterr().out
    assert '"status": "red"' in out
    assert TIP in out


def test_the_red_path_carries_the_failing_step_and_an_untrusted_excerpt(
    red_host, capsys
):
    _exit()
    out = capsys.readouterr().out
    assert "Run shared tests" in out
    assert "assert 6 == 5" in out
    assert '"untrusted": true' in out


def test_the_red_path_carries_the_partners_it_was_never_tested_against(
    red_host, capsys
):
    _exit()
    assert "the partner" in capsys.readouterr().out


def test_a_broken_diagnosis_call_degrades_without_losing_the_verdict(
    red_host, monkeypatch, capsys
):
    """A diagnostic that crashes must not cost the answer it was meant to
    explain — the red verdict still stands, and the gap is named."""
    def _boom(cwd):
        raise gh.ShellError("HTTP 403")

    monkeypatch.setattr(gh, "repo_slug", _boom)
    assert _exit() == 2
    out = capsys.readouterr().out
    assert '"status": "red"' in out
    assert "HTTP 403" in out


def test_a_missing_log_does_not_hide_the_failing_step(red_host, monkeypatch, capsys):
    def _boom(cwd, rid):
        raise gh.ShellError("log expired")

    monkeypatch.setattr(gh, "failed_log", _boom)
    assert _exit() == 2
    out = capsys.readouterr().out
    assert "Run shared tests" in out
    assert "log_unavailable" in out
