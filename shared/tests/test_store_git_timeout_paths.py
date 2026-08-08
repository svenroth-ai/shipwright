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
from lib import main_tree_guards as mtg  # noqa: E402
from lib import sweep_gc as sgc  # noqa: E402
from lib import sweep_outbox as so  # noqa: E402
from lib import git_base as gb  # noqa: E402
from lib.git_base import TIMEOUT_RETURNCODE, run_git_soft  # noqa: E402


def _timeout(*_a, **_k):
    raise subprocess.TimeoutExpired(cmd=["git", "x"], timeout=15.0)


def _unrunnable(*_a, **_k):
    raise FileNotFoundError("git not found")


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
    let the sweep commit into a half-finished merge. The probe now runs inside
    ``lib.main_tree_guards`` (iterate-2026-08-07-shared-op-predicates), so the patch
    target moved with it — mirroring the reconcile sibling in
    test_main_tree_git_timeout_paths.py.
    """
    monkeypatch.setattr(mtg, "run_git_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], TIMEOUT_RETURNCODE, "", "timed out"))
    assert so._op_in_progress(repo) is True


def test_sweep_skips_when_the_guard_times_out(repo, monkeypatch) -> None:
    """End-to-end: the sweep declines rather than raising out of setup step 5."""
    h.seed_tracked(repo, h.item("trg-seed"))
    wt = h.make_worktree(repo, "timeout-guard")
    h.write_outbox(repo, h.item("trg-new"))

    monkeypatch.setattr(mtg, "run_git_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], TIMEOUT_RETURNCODE, "", "timed out"))
    result = so.sweep_outbox_to_branch(repo, wt, default_branch="main")
    assert result.status == "skipped", result.to_dict()
    assert result.reason == "op_in_progress", result.to_dict()


def test_op_in_progress_fails_closed_when_git_is_unrunnable(repo, monkeypatch) -> None:
    """A missing git binary must fail closed too, not raise past the sweep's "never
    raises for an expected condition" contract.

    Before the extraction this called ``run_git_soft`` bare, and ``run_git_soft``
    (``lib.git_base``) only maps ``subprocess.TimeoutExpired`` — an ``OSError`` from
    ``Popen`` propagated uncaught. ``lib.main_tree_guards._probe`` additionally catches
    ``OSError``, so this is a behavior WIDENING the extraction picks up for free
    (opus-plan-review + external review, both flagged the "byte-identical" framing as
    incomplete without this pin).
    """
    monkeypatch.setattr(mtg, "run_git_soft", _unrunnable)
    assert so._op_in_progress(repo) is True


def test_has_staged_changes_fails_closed_when_git_is_unrunnable(repo, monkeypatch) -> None:
    """Same fail-closed widening as above, for the OTHER predicate the extraction
    changes — external review (OpenAI + DeepSeek) both asked for this: the new
    OSError coverage must not stop at ``_op_in_progress``."""
    monkeypatch.setattr(mtg, "run_git_soft", _unrunnable)
    assert so._has_staged_changes(repo) is True


def test_sweep_skips_when_git_is_unrunnable_end_to_end(repo, monkeypatch) -> None:
    """External review (OpenAI): prove the PUBLIC ``sweep_outbox_to_branch`` contract
    for the extracted guard seam specifically, not only the private predicate — an
    unrunnable git at the op-in-progress probe must surface as a structured skip,
    never an escaping exception. Patches only ``mtg.run_git_soft`` (what the guards
    call); ``sweep_outbox.py``'s own bare ``run_git_soft`` calls at the later add/diff/
    commit steps are untouched by this extraction and remain a separate, pre-existing
    surface (code review) — not pinned here."""
    h.seed_tracked(repo, h.item("trg-seed"))
    wt = h.make_worktree(repo, "unrunnable-guard")
    h.write_outbox(repo, h.item("trg-new"))

    monkeypatch.setattr(mtg, "run_git_soft", _unrunnable)
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
    """Empty sets mean "drop nothing", which is already this function's safe answer.

    Reads origin through ``run_git_bytes_soft`` since
    iterate-2026-08-06-gc-decode-parity — the blob must be decoded with the STORE's
    rule, not the text helper's lossy ``errors="replace"``. The timeout fail-safe is
    unchanged and pinned here on the new seam: ``b""`` stdout, same empty sets.
    """
    monkeypatch.setattr(sgc, "run_git_bytes_soft",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], TIMEOUT_RETURNCODE, b"", b"timed out"))
    assert sgc.delivered_membership(repo, "main") == (set(), set())
