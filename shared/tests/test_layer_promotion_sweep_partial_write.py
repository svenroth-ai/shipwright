"""Partial-write hardening tests for ``lib.layer_promotion_sweep`` — split out
of ``test_layer_promotion_sweep_rollback.py`` purely to keep that file under
the file-size guideline (same fixtures, same real-git invocation style).
Pins the guarantee that ``promote_required_layers.py`` writing real files to
the worktree's filesystem — before timing out, failing its commit, or
producing something unusable — never leaves that write behind for a later,
unrelated commit to sweep up onto the iterate's own branch."""

from __future__ import annotations

import json
import subprocess

import pytest

from lib.layer_promotion_sweep import run_layer_promotion_sweep


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    (root / "spec.md").write_text("placeholder\n", encoding="utf-8")
    ledger_dir = root / ".shipwright" / "compliance"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "layer_promotion_ledger.json").write_text('{"decisions": []}\n', encoding="utf-8")
    _git(["add", "spec.md", ".shipwright"], root)
    _git(["commit", "-m", "init"], root)
    return root


_REAL_RUN = subprocess.run


def _stub_run(*, promote_returncode=0, promote_stdout="{}", promote_stderr=""):
    """Intercept only the promote-tool invocation — the sweep's own ``git
    add``/``diff``/``commit`` route through :mod:`lib.git_base`'s own
    ``Popen``, never through ``subprocess.run``, so they always hit the real
    git binary regardless of this stub."""
    def _fake(cmd, *args, **kwargs):
        if len(cmd) >= 2 and str(cmd[1]).endswith("promote_required_layers.py"):
            return subprocess.CompletedProcess(cmd, promote_returncode, promote_stdout, promote_stderr)
        return _REAL_RUN(cmd, *args, **kwargs)
    return _fake


def test_partial_write_before_timeout_is_cleaned_up(monkeypatch, repo):
    """External review, PR #725 round 6: the promote-tool subprocess can
    write a brand-new spec file to the worktree's filesystem before it times
    out — ``pre_sha`` is now captured BEFORE the subprocess ever runs so this
    path can still roll the partial write back, and ``git clean -fd`` (not
    just ``reset --hard``) is what removes a file that was never staged."""
    def _fake(cmd, *args, **kwargs):
        if len(cmd) >= 2 and str(cmd[1]).endswith("promote_required_layers.py"):
            (repo / "new_fr_spec.md").write_text("partial\n", encoding="utf-8")
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=120.0)
        return _REAL_RUN(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake)
    result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "skipped"
    assert "timed out" in result.reason
    assert not (repo / "new_fr_spec.md").exists()
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert porcelain.strip() == ""


def test_partial_write_before_malformed_stdout_is_cleaned_up(monkeypatch, repo):
    """Same partial-write hazard as above, but on the non-JSON-stdout path —
    a subprocess can write real files to disk and still produce unusable
    stdout (a crash mid-print, say)."""
    def _fake(cmd, *args, **kwargs):
        if len(cmd) >= 2 and str(cmd[1]).endswith("promote_required_layers.py"):
            (repo / "new_fr_spec.md").write_text("partial\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, "not json", "")
        return _REAL_RUN(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake)
    result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "error"
    assert "non-JSON" in result.reason
    assert not (repo / "new_fr_spec.md").exists()
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert porcelain.strip() == ""


def test_commit_failure_rolls_back_staged_residue(repo):
    """A failed commit must not leave staged residue behind for a later,
    unrelated commit to sweep up — forced via a real failing pre-commit
    hook rather than a stub, since add/diff/commit route through the real
    git binary regardless of ``subprocess.run`` monkeypatching."""
    report = {
        "promoted": [{"fr": "FR-01.01", "action": "promote"}],
        "written_spec_paths": ["spec.md"], "skipped": [], "escalated": [],
    }
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
        (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")
        result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "error"
    assert "commit_failed" in result.reason
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert porcelain.strip() == ""  # rolled back to pre_sha, nothing left dirty or staged
