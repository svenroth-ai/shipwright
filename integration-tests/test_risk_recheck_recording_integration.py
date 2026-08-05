"""Integration coverage for the risk-recheck recording-integrity F11 gate
(iterate-2026-08-05-risk-recheck-recording-integrity).

The unit `test_risk_recheck_recording.py` and the plugin's own
`test_diff_risk_recheck_persistence.py` each prove their own half correct in
isolation — the real defect this change closes lived BETWEEN them: nothing
wired the CLI's persisted artifact to the F5c-recorded complexity at all. So
this drives the REAL `diff_risk_recheck.py` CLI as a subprocess against a REAL
git repository, writes a REAL (deliberately under-recorded) F5c entry, and
calls the REAL `run_all_checks` registry — proving the pieces compose, not
just that each one is individually correct.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "lib" / "diff_risk_recheck.py"

RUN_ID = "iterate-2026-08-05-integration-example"


def _git(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8"
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo with one committed baseline commit."""
    repo = tmp_path / "project"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(repo.parent, "init", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo


def _write_f5c_entry(project_root: Path, run_id: str, complexity: str) -> Path:
    entries_dir = project_root / ".shipwright" / "agent_docs" / "iterates"
    entries_dir.mkdir(parents=True, exist_ok=True)
    path = entries_dir / f"{run_id}.json"
    path.write_text(json.dumps({
        "run_id": run_id,
        "date": "2026-08-05T00:00:00Z",
        "type": "change",
        "complexity": complexity,
        "branch": f"iterate/{run_id}",
        "tests_passed": True,
    }), encoding="utf-8")
    return path


def _run_recheck_cli(repo: Path, run_id: str, stage1: str = "small") -> tuple[int, dict]:
    proc = subprocess.run(
        [
            sys.executable, str(CLI),
            "--project-root", str(repo),
            "--base-ref", "HEAD",
            "--stage1-complexity", stage1,
            "--run-id", run_id,
        ],
        capture_output=True, encoding="utf-8",
    )
    return proc.returncode, json.loads(proc.stdout)


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_cli_persists_artifact_the_verifier_can_read(repo: Path):
    """End-to-end producer -> consumer: the CLI's own written bytes are what
    the F11 verifier reads back, not a hand-crafted fixture shaped like them."""
    hooks = repo / "plugins" / "shipwright-iterate" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")
    _git(repo, "add", "-A")  # staged, deliberately NOT committed (matches Step 3.4 timing)

    code, out = _run_recheck_cli(repo, RUN_ID, stage1="small")
    assert code == 0, f"cross-component alone must not escalate: {out}"
    assert out["effective_complexity"] == "medium"

    artifact = repo / ".shipwright" / "planning" / "iterate" / RUN_ID / "risk_recheck.json"
    assert artifact.is_file()
    body = json.loads(artifact.read_text(encoding="utf-8"))
    assert body["run_id"] == RUN_ID
    assert body["risk_recheck"]["effective_complexity"] == "medium"


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_underrecorded_f5c_fails_the_real_registered_check(repo: Path):
    """The composition proof: real CLI artifact + real under-recorded F5c entry
    + the REAL `run_all_checks` registry (not the bare check function) must
    together report the failure — proving registration, not just logic."""
    sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
    from tools.verifiers.iterate_checks import run_all_checks

    hooks = repo / "plugins" / "shipwright-iterate" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")
    _git(repo, "add", "-A")

    code, out = _run_recheck_cli(repo, RUN_ID, stage1="small")
    assert code == 0
    assert out["effective_complexity"] == "medium"

    # Deliberately under-record: the runner should have written "medium" per the
    # contract, but writes the stale Stage-1 estimate instead.
    _write_f5c_entry(repo, RUN_ID, "small")

    results = run_all_checks(repo, RUN_ID)
    matches = [r for r in results if r.name == "risk re-check recording integrity"]
    assert len(matches) == 1, "check must be registered exactly once in run_all_checks"
    assert matches[0].ok is False
    assert "medium" in matches[0].detail
    assert "small" in matches[0].detail


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_correctly_recorded_f5c_passes_the_real_registered_check(repo: Path):
    """The inverse composition proof — a compliant runner must not be
    penalized by the same real registry call."""
    sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
    from tools.verifiers.iterate_checks import run_all_checks

    hooks = repo / "plugins" / "shipwright-iterate" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")
    _git(repo, "add", "-A")

    code, out = _run_recheck_cli(repo, RUN_ID, stage1="small")
    assert code == 0
    _write_f5c_entry(repo, RUN_ID, out["effective_complexity"])

    results = run_all_checks(repo, RUN_ID)
    matches = [r for r in results if r.name == "risk re-check recording integrity"]
    assert len(matches) == 1
    assert matches[0].ok is True


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_ci_escalation_path_also_persists_for_the_verifier(repo: Path):
    """The exit-3 CI-escalation path must ALSO leave a readable artifact — a
    runner that gets escalated still leaves evidence of what was computed."""
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("on: push\n", encoding="utf-8")
    _git(repo, "add", "-A")

    code, out = _run_recheck_cli(repo, RUN_ID, stage1="small")
    assert code == 3
    assert out["escalate"]["required"] is True

    artifact = repo / ".shipwright" / "planning" / "iterate" / RUN_ID / "risk_recheck.json"
    assert artifact.is_file()
    body = json.loads(artifact.read_text(encoding="utf-8"))
    assert body["risk_recheck"]["escalate"]["required"] is True


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_standalone_iterate_without_artifact_is_unaffected(repo: Path):
    """Campaign-only, by absence: a standalone iterate never runs Step 3.4, so
    the F5c entry it writes must not be judged by a gate that requires an
    artifact only campaign mode ever produces."""
    sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
    from tools.verifiers.iterate_checks import run_all_checks

    _write_f5c_entry(repo, RUN_ID, "trivial")  # no Step 3.4 ever ran

    results = run_all_checks(repo, RUN_ID)
    matches = [r for r in results if r.name == "risk re-check recording integrity"]
    assert len(matches) == 1
    assert matches[0].is_skipped
