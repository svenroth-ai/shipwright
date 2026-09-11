"""Rollback/error-hardening tests for ``lib.layer_promotion_sweep`` — split out
of ``test_layer_promotion_sweep.py`` purely to keep that file under the
file-size guideline (same fixtures, same real-git invocation style). Pins
every path that must roll back a partial ``git add``/staged/commit before
reporting ``error``, and every malformed-but-syntactically-valid
``promote_required_layers.py`` report shape that must degrade to a reported
error rather than raise past the sweep's own never-raises boundary."""

from __future__ import annotations

import json
import subprocess

import pytest

import lib.layer_promotion_rollback as rollback_mod
import lib.layer_promotion_sweep as sweep_mod
from lib.layer_promotion_sweep import run_layer_promotion_sweep
from lib.layer_promotion_sweep_result import sweep_warnings


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


@pytest.mark.parametrize(
    "bad_stdout",
    [
        pytest.param("null", id="json-null"),
        pytest.param("[]", id="json-list"),
        pytest.param('{"promoted": "not-a-list"}', id="promoted-not-a-list"),
        pytest.param('{"promoted": ["FR-01.01"]}', id="promoted-entry-not-an-object"),
        pytest.param('{"promoted": [{"fr": "FR-01.01"}], "escalated": "not-a-list"}', id="escalated-not-a-list"),
        pytest.param(
            '{"promoted": [{"fr": "FR-01.01"}], "written_spec_paths": [1]}',
            id="written_spec_paths-not-strings",
        ),
        pytest.param('{"promoted": [{"fr": 1}]}', id="fr-not-a-string"),
    ],
)
def test_syntactically_valid_but_malformed_report_is_a_reported_error(monkeypatch, repo, bad_stdout):
    """External review, PR #725: syntactically valid JSON with the wrong
    shape (a list/null document, or a malformed field) must degrade to a
    reported error rather than raising past run_layer_promotion_sweep's own
    never-raises boundary via an unguarded .get()."""
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=bad_stdout))
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "error"
    assert "malformed report" in result.reason


def test_diff_cached_real_git_error_rolls_back_instead_of_committing(monkeypatch, repo):
    """External review, PR #725: `git diff --cached --quiet` uses exit 1 for
    'a real staged delta exists' — any OTHER nonzero (e.g. 128, a genuine git
    error) must roll back and report an error, never fall through to commit
    whatever happened to be staged."""
    report = {
        "promoted": [{"fr": "FR-01.01", "action": "promote"}],
        "written_spec_paths": ["spec.md"], "skipped": [], "escalated": [],
    }
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")

    real_run_git_soft = sweep_mod.run_git_soft

    def _fake_run_git_soft(args, *a, **kw):
        if args[:2] == ["diff", "--cached"]:
            return subprocess.CompletedProcess(["git", *args], 128, "", "fatal: bad object")
        return real_run_git_soft(args, *a, **kw)

    monkeypatch.setattr(sweep_mod, "run_git_soft", _fake_run_git_soft)
    result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "error"
    assert "diff_cached_failed" in result.reason
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert porcelain.strip() == ""  # rolled back — never committed on a bogus diff result


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


def test_empty_pre_sha_stdout_bails_before_staging(monkeypatch, repo):
    """PR #725 external review comment: a `rev-parse HEAD` that exits 0 with
    empty stdout (malformed but not itself an error) must still be treated
    as an unusable rollback target and bail before staging, same as an
    actual rev-parse failure."""
    report = {
        "promoted": [{"fr": "FR-01.01", "action": "promote"}],
        "written_spec_paths": ["spec.md"], "skipped": [], "escalated": [],
    }
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")

    real_run_git_soft = sweep_mod.run_git_soft

    def _fake_run_git_soft(args, *a, **kw):
        if args[:2] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(["git", *args], 0, "", "")
        return real_run_git_soft(args, *a, **kw)

    monkeypatch.setattr(sweep_mod, "run_git_soft", _fake_run_git_soft)
    result = run_layer_promotion_sweep(repo, "iterate-x")
    assert result.status == "error"
    assert "pre_sha_rev_parse_failed" in result.reason

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert staged.strip() == ""  # git add never ran


def test_add_failure_rolls_back_partially_staged_residue(monkeypatch, repo):
    """PR #725 external review: ``git add -- a b`` can stage ``a`` before
    failing on ``b`` (e.g. a bad pathspec) — the add-failure path must roll
    back exactly like the commit-failure path does, never leave the
    partial stage for a later, unrelated commit to sweep up."""
    report = {
        "promoted": [{"fr": "FR-01.01", "action": "promote"}],
        "written_spec_paths": ["spec.md"], "skipped": [], "escalated": [],
    }
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")

    real_run_git_soft = sweep_mod.run_git_soft

    def _fake_run_git_soft(args, *a, **kw):
        if args[:1] == ["add"]:
            # Actually stage spec.md (the partial success), then report the
            # whole invocation as failed — mirrors a real `git add` that
            # stages some pathspecs before erroring on another.
            real_run_git_soft(["add", "--", "spec.md"], *a, **kw)
            return subprocess.CompletedProcess(
                ["git", *args], 128, "", "fatal: pathspec did not match any files"
            )
        return real_run_git_soft(args, *a, **kw)

    monkeypatch.setattr(sweep_mod, "run_git_soft", _fake_run_git_soft)
    result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "error"
    assert "add_failed" in result.reason
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert porcelain.strip() == ""  # rolled back — spec.md's partial stage did not survive


def test_add_failure_with_a_failing_rollback_reports_rollback_failed(monkeypatch, repo):
    """External review, PR #725: ``_rollback_staged`` discarded the reset's
    own returncode, so a rollback that ITSELF failed after ``add_failed``
    still reported an ordinary ``error`` — implying a clean rollback that
    never happened. Must escalate to the loud ``rollback_failed`` instead,
    exactly like the delivery-side reset check already does."""
    report = {
        "promoted": [{"fr": "FR-01.01", "action": "promote"}],
        "written_spec_paths": ["spec.md"], "skipped": [], "escalated": [],
    }
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")

    real_sweep_run_git_soft = sweep_mod.run_git_soft
    real_rollback_run_git_soft = rollback_mod.run_git_soft

    def _fake_sweep_run_git_soft(args, *a, **kw):
        if args[:1] == ["add"]:
            return subprocess.CompletedProcess(["git", *args], 128, "", "fatal: pathspec did not match any files")
        return real_sweep_run_git_soft(args, *a, **kw)

    def _fake_rollback_run_git_soft(args, *a, **kw):
        if args[:2] == ["reset", "--hard"]:
            return subprocess.CompletedProcess(["git", *args], 128, "", "fatal: reset failed")
        return real_rollback_run_git_soft(args, *a, **kw)

    monkeypatch.setattr(sweep_mod, "run_git_soft", _fake_sweep_run_git_soft)
    monkeypatch.setattr(rollback_mod, "run_git_soft", _fake_rollback_run_git_soft)
    result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "rollback_failed"
    assert "add_failed" in result.reason
    assert any("CRITICAL" in w for w in sweep_warnings(result))


