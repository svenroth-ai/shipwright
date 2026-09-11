"""Pins ``lib.layer_promotion_sweep``'s degrade-never-block contract: every
non-decisive outcome of the ``promote_required_layers.py`` subprocess call
(operational failure, timeout, missing interpreter, an explicit offline
opt-out, no evidence yet, malformed output) degrades to a reported result and
never raises or blocks. Delivery-pipeline outcomes (a found promotion's own
PR, push/create failures, the existing-PR race) are pinned separately in
``test_layer_promotion_delivery.py`` — this file stops at the boundary where
delivery would begin."""

from __future__ import annotations

import json
import subprocess

import pytest

import lib.layer_promotion_sweep as sweep_mod
from lib.layer_promotion_sweep import (
    LayerPromotionSweepResult,
    run_layer_promotion_sweep,
    sweep_warnings,
)


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


def _stub_run(*, promote_returncode=0, promote_stdout="{}", promote_stderr="", calls: list | None = None):
    """Intercept only the promote-tool invocation — the sweep's own ``git
    add``/``diff``/``commit`` route through :mod:`lib.git_base`'s own
    ``Popen``, never through ``subprocess.run``, so they always hit the real
    git binary regardless of this stub."""
    def _fake(cmd, *args, **kwargs):
        if calls is not None:
            calls.append(list(cmd))
        if len(cmd) >= 2 and str(cmd[1]).endswith("promote_required_layers.py"):
            return subprocess.CompletedProcess(cmd, promote_returncode, promote_stdout, promote_stderr)
        return _REAL_RUN(cmd, *args, **kwargs)
    return _fake


def test_operational_failure_exit_degrades_to_skipped(monkeypatch, repo):
    monkeypatch.setattr(
        subprocess, "run",
        _stub_run(promote_returncode=2, promote_stdout='{"error": "no manifest"}'),
    )
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "skipped"
    assert "no manifest" in result.reason
    assert sweep_warnings(result) == []


def test_timeout_degrades_to_skipped(monkeypatch, repo):
    def _raise(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="promote_required_layers.py", timeout=120.0)
    monkeypatch.setattr(subprocess, "run", _raise)
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "skipped"
    assert "timed out" in result.reason


def test_missing_interpreter_degrades_to_skipped(monkeypatch, repo):
    def _raise(*_args, **_kwargs):
        raise OSError("no such file")
    monkeypatch.setattr(subprocess, "run", _raise)
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "skipped"
    assert "could not start" in result.reason


def test_no_fetch_opt_out_skips_before_running_the_tool(monkeypatch, repo):
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _stub_run(calls=calls))
    monkeypatch.setenv("SHIPWRIGHT_ITERATE_NO_FETCH", "1")
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "skipped"
    assert "SHIPWRIGHT_ITERATE_NO_FETCH" in result.reason
    assert calls == []
    assert sweep_warnings(result) == []


def test_no_evidence_yet_is_no_change_not_skipped(monkeypatch, repo):
    report = {"promoted": [], "written_spec_paths": [], "skipped": [{"fr": "FR-01.01"}], "escalated": []}
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "no_change"
    assert result.promoted == []
    assert sweep_warnings(result) == []


def test_non_json_stdout_is_an_error(monkeypatch, repo):
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout="not json"))
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "error"
    assert "non-JSON" in result.reason


def test_reported_write_with_no_real_delta_is_no_change(monkeypatch, repo):
    # The tool reports a write, but the file on disk is byte-identical to
    # what's already committed (e.g. an EOL-only rewrite) — nothing staged,
    # so delivery is never even attempted.
    report = {
        "promoted": [{"fr": "FR-01.01", "action": "promote"}],
        "written_spec_paths": ["spec.md"],
        "skipped": [],
        "escalated": [],
    }
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "no_change"


def test_escalations_are_reported_even_on_no_change(monkeypatch, repo):
    report = {
        "promoted": [], "written_spec_paths": [],
        "skipped": [], "escalated": [{"fr": "FR-01.02", "reason_code": "layer_undeterminable"}],
    }
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "no_change"
    assert result.escalated == 1
    warnings = sweep_warnings(result)
    assert any("1 FR(s) escalated" in w for w in warnings)


def test_exit_3_is_still_a_normal_report(monkeypatch, repo):
    report = {
        "promoted": [], "written_spec_paths": [],
        "skipped": [], "escalated": [{"fr": "FR-01.02", "reason_code": "layer_undeterminable"}],
    }
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_returncode=3, promote_stdout=json.dumps(report)))
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "no_change"
    assert result.escalated == 1


def test_unreadable_pre_sha_bails_before_staging(monkeypatch, repo):
    """Stage-2 review: an unreadable rev-parse HEAD must bail BEFORE staging
    anything — an unknown rollback target is the one state this module must
    never create (it is what could leave a promotion commit sitting on the
    iterate's own branch)."""
    report = {
        "promoted": [{"fr": "FR-01.01", "action": "promote"}],
        "written_spec_paths": ["spec.md"], "skipped": [], "escalated": [],
    }
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")

    real_run_git_soft = sweep_mod.run_git_soft

    def _fake_run_git_soft(args, *a, **kw):
        if args[:2] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(["git", *args], 128, "", "fatal: bad revision")
        return real_run_git_soft(args, *a, **kw)

    monkeypatch.setattr(sweep_mod, "run_git_soft", _fake_run_git_soft)
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "error"
    assert "pre_sha_rev_parse_failed" in result.reason

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert staged.strip() == ""  # git add never ran


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


def test_result_to_dict_shape():
    result = LayerPromotionSweepResult(
        status="delivered", promoted=["FR-01.01"], escalated=0,
        pr_url="https://example.com/pull/1", branch="chore/layer-promotion-abc123def456",
    )
    assert result.to_dict() == {
        "status": "delivered", "reason": "", "promoted": ["FR-01.01"],
        "escalated": 0, "pr_url": "https://example.com/pull/1",
        "branch": "chore/layer-promotion-abc123def456",
    }
