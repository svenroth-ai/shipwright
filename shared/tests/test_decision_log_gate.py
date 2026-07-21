"""Tests for the ADR / decision-log integrity checks (verifiers/decision_log_gate.py).

Split from test_verify_iterate_finalization.py
(iterate-2026-07-20-runner-finalization-integrity) so the finalization additions
do not ratchet that grandfathered file. Covers:

- (b) ``check_adr_in_iterate_history``: a run-id ADR identity passes only when the
  decision-drop actually CARRIES the ADR (parses + run_id + non-empty decision),
  not when it is an empty ``{}`` placeholder;
- (c) ``check_iterate_no_direct_decision_log``: an iterate commit that writes
  ``decision_log.md`` directly fails the F11 gate.

(The happy-path acceptance tests for check_adr_in_iterate_history — pending drop,
Run-ID-line aggregation, worktree resolution, numbered-ADR backward-compat — stay
in test_verify_iterate_finalization.py alongside the run_all_checks orchestrator.)
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tools.verifiers.iterate_checks import (
    check_adr_in_iterate_history,
    check_iterate_no_direct_decision_log,
)

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], env=_GIT_ENV,
                   capture_output=True, text=True, check=True)


def _head_sha(cwd: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "HEAD"],
        env=_GIT_ENV, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _init_repo_with_baseline(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    (repo / "a.txt").write_text("hi\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "baseline")


# ─── (b) drop-content contract ──────────────────────────────────────────────

def test_adr_check_fails_when_decision_drop_is_empty_placeholder(tmp_path):
    """(b) contract: run-id ADR identity is accepted ONLY when the drop actually
    CARRIES the ADR. A placeholder ``{}`` drop (the shape left behind when the
    per-run ADR is silently lost) must NOT pass — otherwise a run whose ADR
    vanished still reads green."""
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": "iterate-20260515-x", "adr": "iterate-20260515-x"},
        ],
    }))
    drops = proj / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True)
    (drops / "iterate-20260515-x_001.json").write_text("{}")
    (proj / ".shipwright" / "agent_docs" / "decision_log.md").write_text("# Decision Log\n")
    result = check_adr_in_iterate_history(proj, "iterate-20260515-x")
    assert result.ok is False


def test_adr_check_fails_when_drop_decision_empty(tmp_path):
    """(b) a drop that parses and matches run_id but has an EMPTY decision is
    still a lost ADR — reject it."""
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": "iterate-20260515-x", "adr": "iterate-20260515-x"},
        ],
    }))
    drops = proj / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True)
    (drops / "iterate-20260515-x_001.json").write_text(
        json.dumps({"run_id": "iterate-20260515-x", "decision": "   "})
    )
    result = check_adr_in_iterate_history(proj, "iterate-20260515-x")
    assert result.ok is False


# ─── (c) no-direct-decision_log gate ────────────────────────────────────────

def test_no_direct_decision_log_passes_when_untouched(tmp_path):
    repo = tmp_path / "proj"
    _init_repo_with_baseline(repo)
    (repo / "b.txt").write_text("bye\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-m", "feat: unrelated change")
    result = check_iterate_no_direct_decision_log(repo, "iterate-x", _head_sha(repo))
    assert result.ok is True
    assert "not modified" in result.detail


def test_no_direct_decision_log_fails_when_iterate_writes_it(tmp_path):
    repo = tmp_path / "proj"
    _init_repo_with_baseline(repo)
    log = repo / ".shipwright" / "agent_docs" / "decision_log.md"
    log.parent.mkdir(parents=True)
    log.write_text("# Decision Log\n\n### ADR-050: sneaky direct write\n")
    _git(repo, "add", str(log))
    _git(repo, "commit", "-m", "chore: append ADR directly (forbidden)")
    result = check_iterate_no_direct_decision_log(repo, "iterate-x", _head_sha(repo))
    assert result.ok is False
    assert result.severity == "error"
    assert "decision_log.md" in result.detail


def test_no_direct_decision_log_skips_without_commit(tmp_path):
    result = check_iterate_no_direct_decision_log(tmp_path, "iterate-x", "")
    assert result.ok is True
    assert result.severity == "skipped"


def test_no_direct_decision_log_ignores_unrelated_decision_log_named_files(tmp_path):
    """The gate is scoped to the tracked agent-doc path only — a differently
    located file that merely contains 'decision_log' in its name must not trip
    the gate (e.g. a test fixture or a tool script)."""
    repo = tmp_path / "proj"
    _init_repo_with_baseline(repo)
    other = repo / "shared" / "tests" / "fixtures" / "decision_log_sample.md"
    other.parent.mkdir(parents=True)
    other.write_text("not the real agent-doc\n")
    _git(repo, "add", str(other))
    _git(repo, "commit", "-m", "test: add decision_log fixture")
    result = check_iterate_no_direct_decision_log(repo, "iterate-x", _head_sha(repo))
    assert result.ok is True
