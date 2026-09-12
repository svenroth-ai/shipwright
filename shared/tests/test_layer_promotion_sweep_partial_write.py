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


def test_preexisting_untracked_file_survives_rollback_after_timeout(monkeypatch, repo):
    """External review, PR #725 round 7: a blanket ``git clean -fd`` would
    delete untracked content that predates this sweep entirely, not just
    residue the promotion tool itself created. The untracked baseline is
    now captured before the subprocess ever runs so a later rollback's
    cleanup only ever removes what's NEW."""
    (repo / "pre_existing_scratch.md").write_text("do not delete me\n", encoding="utf-8")

    def _fake(cmd, *args, **kwargs):
        if len(cmd) >= 2 and str(cmd[1]).endswith("promote_required_layers.py"):
            (repo / "new_fr_spec.md").write_text("partial\n", encoding="utf-8")
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=120.0)
        return _REAL_RUN(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake)
    result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "skipped"
    assert (repo / "pre_existing_scratch.md").read_text(encoding="utf-8") == "do not delete me\n"
    assert not (repo / "new_fr_spec.md").exists()  # the genuine partial write IS still cleaned


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


def test_untracked_status_failure_reports_rollback_failed_not_a_clean_skip(monkeypatch, repo):
    """External review, PR #725 round 9: when ``git status`` itself fails (so
    the untracked baseline can't be established, before or after), rollback
    must not silently report an ordinary terminal status — the caller needs
    the loud ``rollback_failed`` escalation, since a partial untracked write
    from the promotion tool may still be sitting in the worktree unremoved
    and nothing else would ever say so."""
    import lib.layer_promotion_rollback as rollback_mod

    real_run_git_soft = rollback_mod.run_git_soft

    def _fake_run_git_soft(args, *a, **kw):
        if args and args[0] == "status":
            return subprocess.CompletedProcess(["git", *args], 1, "", "status failed")
        return real_run_git_soft(args, *a, **kw)

    monkeypatch.setattr(rollback_mod, "run_git_soft", _fake_run_git_soft)

    def _fake_subprocess_run(cmd, *args, **kwargs):
        if len(cmd) >= 2 and str(cmd[1]).endswith("promote_required_layers.py"):
            (repo / "new_fr_spec.md").write_text("partial\n", encoding="utf-8")
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=120.0)
        return _REAL_RUN(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_subprocess_run)
    result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "rollback_failed"


def test_report_naming_a_pathspec_magic_path_cannot_be_delivered(monkeypatch, repo):
    """External review, PR #725 round 12: ``:(glob)**/spec.md`` passes every
    prior check in ``validate_written_paths`` — ``Path(...).name`` is still
    ``"spec.md"``, no ``..``/absolute component exists — but handed
    unescaped to ``git add`` it IS a pathspec: the leading ``:`` triggers
    Git's pathspec magic and matches every ``spec.md`` in the repo, not the
    one file the report claimed to write. A second, unrelated ``spec.md``
    elsewhere in the repo must never be staged or committed by it."""
    other_spec = repo / "unrelated_component" / "spec.md"
    other_spec.parent.mkdir(parents=True)
    other_spec.write_text("do not publish me\n", encoding="utf-8")
    _git(["add", "unrelated_component/spec.md"], repo)
    _git(["commit", "-m", "unrelated component's own spec"], repo)
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")
    other_spec.write_text("do not publish me\nmodified too\n", encoding="utf-8")

    report = {
        "promoted": [{"fr": "FR-01.01", "action": "promote"}],
        "written_spec_paths": [":(glob)**/spec.md"], "skipped": [], "escalated": [],
    }
    monkeypatch.setattr(subprocess, "run", _stub_run(promote_stdout=json.dumps(report)))
    result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "error"
    assert "unsafe report path" in result.reason
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=repo, capture_output=True, text=True,
    ).stdout
    assert "unrelated_component/spec.md" not in staged
    # The bail path's `git reset --hard` legitimately reverts EVERY uncommitted
    # tracked-file change repo-wide, not just ones this sweep touched — so
    # other_spec's own uncommitted edit is expected to revert to its last
    # committed content, same as it would for any other rollback.
    assert other_spec.read_text(encoding="utf-8") == "do not publish me\n"


def test_untracked_cleanup_does_not_glob_match_a_sibling_file(monkeypatch, repo):
    """External review, PR #725 round 13: ``new_paths`` in ``rollback_staged``
    are filesystem-derived names (from ``git status --porcelain``), never
    validated the way ``written_spec_paths`` is — a newly created file whose
    NAME itself contains pathspec-glob syntax (here, a bracket character
    class) would, without ``--literal-pathspecs``, let ``git clean`` match
    and remove an unrelated, PRE-EXISTING untracked sibling file too, not
    just the one path this cleanup means to remove."""
    sibling = repo / "filea.md"
    sibling.write_text("do not delete me\n", encoding="utf-8")  # untracked BEFORE the sweep runs

    def _fake(cmd, *args, **kwargs):
        if len(cmd) >= 2 and str(cmd[1]).endswith("promote_required_layers.py"):
            # A literal filename containing bracket-glob syntax — matches
            # "filea.md" too under NON-literal pathspec matching.
            (repo / "file[a-z].md").write_text("partial\n", encoding="utf-8")
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=120.0)
        return _REAL_RUN(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake)
    result = run_layer_promotion_sweep(repo, "iterate-x")

    assert result.status == "skipped"
    assert not (repo / "file[a-z].md").exists()  # the genuine partial write IS still cleaned
    assert sibling.read_text(encoding="utf-8") == "do not delete me\n"  # the sibling survives


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
