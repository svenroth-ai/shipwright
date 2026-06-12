"""WP6/F17 — ``integrate_main`` commit-failure handling (merge + follow-up).

Split out of ``test_integrate_main.py`` (which keeps the AC-6/AC-7 resolve+audit
core) so neither module crosses the 300-LOC budget. This is the structured-status
family: a failed ``git commit`` must NEVER raise ``CalledProcessError`` (traceback,
no JSON, repo wedged mid-merge) — every branch returns a typed status + a precise
CLI exit code:

  - ``merge_commit_failed``                  → merge aborted cleanly         → exit 7
  - ``merge_commit_failed_abort_incomplete`` → abort double-fault (wedged)   → exit 7
  - ``followup_commit_failed``               → merge intact, snapshot staged → exit 8

Reuses the shared git/worktree helpers from ``test_integrate_main``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _DASH, _RUN_ID, _git, _set_repo_identity, _write  # noqa: E402
from tools import integrate_main  # noqa: E402


def _seed_diverged_dashboard(git_origin_repo, make_worktree, slug: str) -> Path:
    """The canonical churn setup: seed a tracked dashboard on main, branch an
    iterate worktree that edits it, then advance origin/main divergently on the
    SAME file — so the integrate merge lands a resolvable churn conflict with
    ``MERGE_HEAD`` set. Returns the iterate worktree path."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _DASH, "base dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard")
    _git(work, "push", "origin", "main")
    wt = make_worktree(work, slug)
    _write(wt, _DASH, "iterate dashboard\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes dashboard")
    _write(work, _DASH, "main dashboard\n")
    _git(work, "commit", "-am", "main changes dashboard")
    _git(work, "push", "origin", "main")
    return wt


def _staging_regen(project_root, run_id, **kw):
    """A ``regenerate_tracked_snapshots`` stub that STAGES a snapshot change, so
    ``_has_staged_changes`` is True and the separate follow-up commit is attempted."""
    _write(Path(project_root), _DASH, f"regenerated ({run_id})\n")
    _git(Path(project_root), "add", "--", _DASH)
    return {_DASH: "regenerated"}


def test_integrate_returns_json_and_aborts_when_merge_commit_blocked(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """WP6/F17 regression: when the merge commit itself fails (e.g. the pre-commit
    anti-ratchet hook blocks it), ``integrate`` must return a STRUCTURED JSON
    status and leave NO ``MERGE_HEAD`` (``git merge --abort``) — never raise
    ``CalledProcessError`` (traceback, no JSON, repo wedged mid-merge), mirroring
    every other failure path."""
    wt = _seed_diverged_dashboard(git_origin_repo, make_worktree, "churn-commit-blocked")

    # Force the merge `git commit` to fail like a pre-commit hook rejecting it.
    real_git = integrate_main._git

    def failing_git(project_root, *args, **kwargs):
        if args[:1] == ("commit",) and "--no-edit" in args:
            raise subprocess.CalledProcessError(1, ["git", *args], stderr="pre-commit hook blocked")
        return real_git(project_root, *args, **kwargs)

    monkeypatch.setattr(integrate_main, "_git", failing_git)

    called = {"regen": False}
    monkeypatch.setattr(
        integrate_main.rcc, "regenerate_tracked_snapshots",
        lambda *a, **k: called.__setitem__("regen", True) or {},
    )

    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    # Structured JSON status, never a raised exception.
    assert isinstance(result, dict)
    assert result["status"] == "merge_commit_failed", result
    assert called["regen"] is False, "regeneration must not run after a failed commit"
    # The tree is clean: merge --abort ran, no MERGE_HEAD, no unmerged paths.
    assert _git(wt, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode != 0
    assert _git(wt, "diff", "--name-only", "--diff-filter=U").stdout.strip() == ""


def test_main_cli_reports_merge_commit_failed_status(
    git_origin_repo, make_worktree, monkeypatch, capsys
) -> None:
    """The CLI surfaces the ``merge_commit_failed`` status as JSON + exit 7 (no
    traceback)."""
    wt = _seed_diverged_dashboard(git_origin_repo, make_worktree, "churn-cli-blocked")

    real_git = integrate_main._git

    def failing_git(project_root, *args, **kwargs):
        if args[:1] == ("commit",) and "--no-edit" in args:
            raise subprocess.CalledProcessError(1, ["git", *args], stderr="blocked")
        return real_git(project_root, *args, **kwargs)

    monkeypatch.setattr(integrate_main, "_git", failing_git)

    rc = integrate_main.main(["--project-root", str(wt), "--run-id", _RUN_ID, "--no-fetch"])

    assert rc == 7
    captured = capsys.readouterr()
    assert '"status": "merge_commit_failed"' in captured.out
    # No bare traceback escaped to stderr — the JSON-status contract holds.
    assert "Traceback" not in captured.err
    # The merge was aborted: MERGE_HEAD is gone after main() returns.
    assert _git(wt, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode != 0


def test_integrate_returns_followup_commit_failed_when_followup_blocked(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """WP6/F17 (a1-3 follow-up): the merge commit LANDS, but the separate
    regenerate follow-up commit is refused (e.g. a hook). ``integrate`` returns
    ``followup_commit_failed`` WITHOUT aborting — the merge is intact, nothing in
    progress — and leaves the regenerated snapshot staged for a manual retry."""
    wt = _seed_diverged_dashboard(git_origin_repo, make_worktree, "churn-followup-blocked")
    monkeypatch.setattr(integrate_main.rcc, "regenerate_tracked_snapshots", _staging_regen)

    real_git = integrate_main._git

    def failing_git(project_root, *args, **kwargs):
        # Fail ONLY the follow-up commit (`commit -m <msg>`); the merge commit
        # (`commit --no-edit`) must succeed first so HEAD advances.
        if args[:1] == ("commit",) and "-m" in args:
            raise subprocess.CalledProcessError(1, ["git", *args], stderr="hook blocked follow-up")
        return real_git(project_root, *args, **kwargs)

    monkeypatch.setattr(integrate_main, "_git", failing_git)

    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "followup_commit_failed", result
    assert "merge-committed" in result["steps"]
    assert "regenerated-followup" not in result["steps"]
    assert "intact" in result["message"]
    # Merge commit survived: no MERGE_HEAD, and HEAD is a merge commit (two parents).
    assert _git(wt, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode != 0
    parents = _git(wt, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(parents) == 3, "merge commit must remain (commit + two parents)"
    # The regenerated snapshot stays staged for the manual retry the message promises.
    assert _DASH in _git(wt, "diff", "--cached", "--name-only").stdout


def test_main_cli_reports_followup_commit_failed_exit_8(
    git_origin_repo, make_worktree, monkeypatch, capsys
) -> None:
    """The CLI surfaces ``followup_commit_failed`` as JSON + exit 8 — distinct from
    the merge-commit exit 7 — with no traceback (a1-3 follow-up)."""
    wt = _seed_diverged_dashboard(git_origin_repo, make_worktree, "churn-followup-cli")
    monkeypatch.setattr(integrate_main.rcc, "regenerate_tracked_snapshots", _staging_regen)

    real_git = integrate_main._git

    def failing_git(project_root, *args, **kwargs):
        if args[:1] == ("commit",) and "-m" in args:
            raise subprocess.CalledProcessError(1, ["git", *args], stderr="blocked")
        return real_git(project_root, *args, **kwargs)

    monkeypatch.setattr(integrate_main, "_git", failing_git)

    rc = integrate_main.main(["--project-root", str(wt), "--run-id", _RUN_ID, "--no-fetch"])

    assert rc == 8
    captured = capsys.readouterr()
    assert '"status": "followup_commit_failed"' in captured.out
    assert "Traceback" not in captured.err


def test_integrate_returns_abort_incomplete_when_merge_abort_double_faults(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """WP6/F17 abort double-fault (a1-3 follow-up): the merge commit is refused AND
    the recovering ``git merge --abort`` itself fails to clear ``MERGE_HEAD``.
    ``integrate`` must report the WEDGED state as
    ``merge_commit_failed_abort_incomplete`` (not a clean ``merge_commit_failed``)
    so the caller never gets a false 'aborted' claim."""
    wt = _seed_diverged_dashboard(git_origin_repo, make_worktree, "churn-abort-incomplete")

    called = {"regen": False}
    monkeypatch.setattr(
        integrate_main.rcc, "regenerate_tracked_snapshots",
        lambda *a, **k: called.__setitem__("regen", True) or {},
    )

    real_git = integrate_main._git

    def failing_git(project_root, *args, **kwargs):
        if args[:1] == ("commit",) and "--no-edit" in args:
            raise subprocess.CalledProcessError(1, ["git", *args], stderr="merge commit blocked")
        if args[:2] == ("merge", "--abort"):
            # Simulate the abort failing (index.lock / hook side effect): a no-op
            # that leaves MERGE_HEAD set, so the verify finds the tree still merging.
            return subprocess.CompletedProcess(["git", *args], 1, "", "fatal: could not abort")
        return real_git(project_root, *args, **kwargs)

    monkeypatch.setattr(integrate_main, "_git", failing_git)

    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "merge_commit_failed_abort_incomplete", result
    assert "merge-committed" not in result["steps"]
    assert called["regen"] is False
    assert "resolve by hand" in result["message"]
    # The repo IS still mid-merge — the distinct status exists precisely for this.
    assert _git(wt, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode == 0
