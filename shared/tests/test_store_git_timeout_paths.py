"""Every git timeout inside the triage store's locked sections is REPORTED, not raised.

Stage-1 review of iterate-2026-07-31-triage-store-failsafe correctly rejected these
behaviours being dispositioned ``covered-by-existing-test``: nothing pre-existing
pinned them, and the timeout branches are not the ordinary ``returncode != 0``
branches — at three sites they are the OPPOSITE of them (a non-zero
``diff --cached`` means "there is a staged delta and we should commit", while a
timeout must mean "stop"). They are also entirely deterministic to test: a
``subprocess.TimeoutExpired`` is a plain exception, which this repo already raises
synthetically in several suites.

Why it matters: every call here runs while the canonical triage ``_FileLock`` is
held, on the ``setup_iterate_worktree`` step-5 path. ``run_git`` KILLS the process on
timeout, stranding ``.git/index.lock`` — and for ``reconcile_triage`` and
``sweep_drift`` that lock lands in the operator's MAIN tree. An escaping exception
also aborts setup after ``git worktree add`` has already succeeded, orphaning it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib import sweep_gc as sgc  # noqa: E402
from lib import sweep_outbox as so  # noqa: E402
from lib import git_base as gb  # noqa: E402
from lib.git_base import TIMEOUT_RETURNCODE, run_git_soft  # noqa: E402


def _timeout(*_a, **_k):
    raise subprocess.TimeoutExpired(cmd=["git", "x"], timeout=15.0)


@pytest.fixture
def repo(git_origin_repo, monkeypatch):
    # These drive the REAL sweep / reconcile, which no-op under `$CI`
    # (`ci_without_optin`) — green locally, ten false failures in CI.
    monkeypatch.delenv("CI", raising=False)
    work, _origin = git_origin_repo
    h.set_identity(work)
    return work


# ---------------------------------------------------------------------------
# The primitive itself
# ---------------------------------------------------------------------------

def test_run_git_soft_reports_a_timeout_as_a_failed_process(tmp_path, monkeypatch) -> None:
    """The whole design rests on this: a timeout becomes data, not an exception."""
    # Module OBJECT, never the "lib.git_base.run_git" string: the string form
    # re-resolves `lib` at patch time and can bind a different one (ADR-045).
    monkeypatch.setattr(gb, "run_git", _timeout)
    proc = run_git_soft(["status"], cwd=tmp_path)
    assert proc.returncode == TIMEOUT_RETURNCODE
    assert "timed out" in proc.stderr


def test_run_git_soft_passes_a_normal_result_through(repo) -> None:
    """It must not swallow ordinary outcomes — a real call still reports truthfully."""
    proc = run_git_soft(["rev-parse", "--verify", "HEAD"], cwd=repo)
    assert proc.returncode == 0 and proc.stdout.strip()


# ---------------------------------------------------------------------------
# sweep_outbox — three sites whose timeout branch is the OPPOSITE of non-zero
# ---------------------------------------------------------------------------

def test_op_in_progress_says_yes_when_it_cannot_tell(repo, monkeypatch) -> None:
    """An ordinary non-zero means "no such ref"; a timeout must NOT mean that.

    Reading "no operation in progress" from a question that was never answered would
    let the sweep commit into a half-finished merge.
    """
    monkeypatch.setattr(so, "run_git_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], TIMEOUT_RETURNCODE, "", "timed out"))
    assert so._op_in_progress(repo) is True


def test_sweep_skips_when_the_guard_times_out(repo, monkeypatch) -> None:
    """End-to-end: the sweep declines rather than raising out of setup step 5."""
    h.seed_tracked(repo, h.item("trg-seed"))
    wt = h.make_worktree(repo, "timeout-guard")
    h.write_outbox(repo, h.item("trg-new"))

    monkeypatch.setattr(so, "run_git_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], TIMEOUT_RETURNCODE, "", "timed out"))
    result = so.sweep_outbox_to_branch(repo, wt, default_branch="main")
    assert result.status == "skipped", result.to_dict()
    assert result.reason == "op_in_progress", result.to_dict()


def test_staged_probe_timeout_does_not_read_as_a_staged_delta(repo, monkeypatch) -> None:
    """The sharpest of the three: ``diff --cached --quiet`` exits NON-ZERO to mean
    "there IS a delta, go commit". A timeout must not be read as that."""
    h.seed_tracked(repo, h.item("trg-seed"))
    wt = h.make_worktree(repo, "timeout-staged")
    h.write_outbox(repo, h.item("trg-new"))

    real = so.run_git_soft

    def wrapper(args, **kwargs):
        if args[:3] == ["diff", "--cached", "--quiet"] and "--" in args:
            return subprocess.CompletedProcess(["git", *args], TIMEOUT_RETURNCODE, "", "timed out")
        return real(args, **kwargs)

    monkeypatch.setattr(so, "run_git_soft", wrapper)
    result = so.sweep_outbox_to_branch(repo, wt, default_branch="main")
    assert result.status == "error", result.to_dict()
    assert result.reason == "git_timeout: diff --cached", result.to_dict()


def test_commit_timeout_is_reported_structurally(repo, monkeypatch) -> None:
    h.seed_tracked(repo, h.item("trg-seed"))
    wt = h.make_worktree(repo, "timeout-commit")
    h.write_outbox(repo, h.item("trg-new"))

    real = so.run_git_soft

    def wrapper(args, **kwargs):
        if args and args[0] == "commit":
            return subprocess.CompletedProcess(["git", *args], TIMEOUT_RETURNCODE, "", "timed out")
        return real(args, **kwargs)

    monkeypatch.setattr(so, "run_git_soft", wrapper)
    result = so.sweep_outbox_to_branch(repo, wt, default_branch="main")
    assert result.status == "error", result.to_dict()
    assert result.reason == "commit_timeout", result.to_dict()


# ---------------------------------------------------------------------------
# sweep_gc — the documented fail-safe direction must absorb a timeout too
# ---------------------------------------------------------------------------

def test_delivered_membership_gcs_nothing_on_timeout(repo, monkeypatch) -> None:
    """Empty sets mean "drop nothing", which is already this function's safe answer."""
    monkeypatch.setattr(sgc, "run_git_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], TIMEOUT_RETURNCODE, "", "timed out"))
    assert sgc.delivered_membership(repo, "main") == (set(), set())
