"""What happens when the note CANNOT be carried across the integrate (P2.15).

The sibling ``test_handoff_survives_integrate.py`` pins the composition working. This
file pins the three ways it can fail, because the carve-out that fixed P2.15 is also what
made them reachable: before it, ``restore_derived_to_head`` cleaned the note
unconditionally, so "the stash could not take it" and "the write-back could not put it
back" simply had nowhere to bite for this path.

All three resolve through :data:`~lib.run_written_ledger.BEST_EFFORT_CARRY`, whose whole
job is to say that the two run-written paths are **not worth the same**. Losing the note
costs two WARNINGs (F11 freshness and Canon C3, both advisory by deliberate choice);
losing ``shipwright_test_results.json`` costs the run's only copy of its test evidence.
Stopping the branch is the right trade for the second and the wrong one for the first.

Found by the Stage-3 doubt review (two medium doubts) and the external code review
(openai/medium, the third one). Every test here was verified RED against the real
failure before the asymmetry existed — the uncarried case returns ``merge_failed``
carrying git's own *"Your local changes ... would be overwritten by merge"*.

Its own file because the sibling reached the 300-line source limit; the seam is
"does it work" versus "what does a failure cost", which is where the two differ anyway.
Fixtures are imported from the sibling rather than copied — a second rendering of the
note is exactly what the shared ``_c3_fixtures`` builders exist to prevent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _c3_fixtures import write_handoff  # noqa: E402
from lib.derived_snapshots import SESSION_HANDOFF  # noqa: E402
from test_handoff_survives_integrate import (  # noqa: E402
    SIBLING_AT,
    SIBLING_RUN,
    THIS_RUN,
    _note_bytes,
    _seed_main,
    _stamp_f5b,
)
from test_integrate_main import _git, _write  # noqa: E402
from tools import integrate_main  # noqa: E402
from verifiers.handoff_freshness import check_session_handoff_fresh  # noqa: E402


def test_a_note_that_cannot_be_CARRIED_does_not_block_the_merge(
    git_origin_repo, make_worktree, monkeypatch,
) -> None:
    """Stage-3 doubt review, medium — the failure mode the carve-out imported.

    Before P2.15 the restore cleaned the note unconditionally, so "the stash could not
    take it" was unreachable for this path. Carving it out of the restore made it
    reachable: a note left dirty meets a mainline that moved the same path, and ``git
    merge`` refuses outright — ``ensure_current`` exits 6 and F11 STOPS the run.

    For the F5 ledger stopping is the correct trade. For a note whose loss costs two
    WARNINGs it is not, so :data:`BEST_EFFORT_CARRY` resets an uncarried copy instead.
    The read is failed at ``lib.run_written_ledger.durable_read_bytes`` — patched on the
    module that BINDS the name, per ADR-045 — for this path only, so the ledger's own
    handling is untouched.
    """
    from lib import run_written_ledger

    work, _origin = git_origin_repo
    _seed_main(work)

    wt = make_worktree(work, "p2-15-uncarried")
    _write(wt, "app.py", "source\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes source")
    _stamp_f5b(wt)

    write_handoff(work, phase="iterate", run_id=SIBLING_RUN, timestamp=SIBLING_AT)
    _git(work, "commit", "-am", "a sibling iterate moved the note on main")
    _git(work, "push", "origin", "main")

    real_read = run_written_ledger.durable_read_bytes

    def _unreadable(path, *args, **kwargs):
        if Path(path).as_posix().endswith(SESSION_HANDOFF):
            raise OSError("held open by another process")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(run_written_ledger, "durable_read_bytes", _unreadable)

    result = integrate_main.integrate(wt, THIS_RUN, do_fetch=True)

    assert result["status"] == "ok", (
        f"an uncarried note blocked the branch: {result}. Losing a warning-severity "
        "marker is cheaper than stopping delivery"
    )
    assert "ledger-not-carried" in result["steps"], "the failure must still be named"
    assert "uncarried-reset" in result["steps"], result["steps"]
    # The marker is gone — that is the accepted cost, and it must be the WARNING it
    # claims to be rather than anything that blocks.
    fresh = check_session_handoff_fresh(wt, THIS_RUN)
    assert fresh.ok is False and fresh.severity == "warning", fresh


def test_a_note_that_cannot_be_WRITTEN_BACK_does_not_abort_the_integrate(
    git_origin_repo, make_worktree, monkeypatch,
) -> None:
    """Stage-3 doubt review, medium — the other half of the same asymmetry.

    ``integrate_main`` turns any failed write-back into the terminal
    ``ledger_writeback_failed``, whose message tells the operator to "re-run F5" — a
    remedy that cannot clear a note F5b writes. With a second member in the set that
    status became reachable for the note alone, so it is now split by what the loss
    COSTS: the note is reported as a step and the branch keeps its merge.
    """
    from lib import run_written_ledger

    work, _origin = git_origin_repo
    _seed_main(work)

    wt = make_worktree(work, "p2-15-writeback")
    _write(wt, "app.py", "source\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes source")
    _stamp_f5b(wt)

    write_handoff(work, phase="iterate", run_id=SIBLING_RUN, timestamp=SIBLING_AT)
    _git(work, "commit", "-am", "a sibling iterate moved the note on main")
    _git(work, "push", "origin", "main")

    def _unwritable(path, *args, **kwargs):
        raise OSError("held open by another process")

    monkeypatch.setattr(run_written_ledger, "durable_atomic_write", _unwritable)

    result = integrate_main.integrate(wt, THIS_RUN, do_fetch=True)

    assert result["status"] == "ok", (
        f"a note that could not be written back aborted the integrate: {result}"
    )
    assert "ledger-writeback-failed" in result["steps"], "the failure must still be named"
    assert "writeback-degraded" in result["steps"], result["steps"]


def test_a_reset_that_ALSO_fails_is_named_rather_than_silent(
    git_origin_repo, make_worktree, monkeypatch,
) -> None:
    """External code review, openai/medium — the fallback can itself fail.

    A failed carry and a failed reset share their likeliest cause (a lost `index.lock`,
    an unreadable path), so the fallback is not guaranteed. The merge is still attempted:
    it refuses only when mainline ALSO moved the note, so refusing pre-emptively would
    turn a possible failure into a certain one — and here mainline did move it, so the
    refusal is real, clean, and carries git's own message naming the file.

    What must not happen is silence. The failed reset gets its own step so a
    `merge_failed` arriving afterwards is attributable to it.
    """
    from lib import run_written_ledger

    work, _origin = git_origin_repo
    _seed_main(work)

    wt = make_worktree(work, "p2-15-reset-fails")
    _write(wt, "app.py", "source\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes source")
    _stamp_f5b(wt)

    write_handoff(work, phase="iterate", run_id=SIBLING_RUN, timestamp=SIBLING_AT)
    _git(work, "commit", "-am", "a sibling iterate moved the note on main")
    _git(work, "push", "origin", "main")

    real_read = run_written_ledger.durable_read_bytes

    def _unreadable(path, *args, **kwargs):
        if Path(path).as_posix().endswith(SESSION_HANDOFF):
            raise OSError("held open by another process")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(run_written_ledger, "durable_read_bytes", _unreadable)

    real_git = integrate_main._git

    def _git_reset_fails(project_root, *args, **kwargs):
        if args[:3] == ("checkout", "HEAD", "--") and args[3:] == (SESSION_HANDOFF,):
            return subprocess.CompletedProcess(args, 1, "", "fatal: unable to write file")
        return real_git(project_root, *args, **kwargs)

    monkeypatch.setattr(integrate_main, "_git", _git_reset_fails)

    result = integrate_main.integrate(wt, THIS_RUN, do_fetch=True)

    assert "uncarried-reset-failed" in result["steps"], (
        f"the fallback failed silently: {result}"
    )
    assert "uncarried-reset" not in result["steps"]
    # The merge then refuses — safely, with the file named — rather than losing anything.
    assert result["status"] == "merge_failed", result
    assert SESSION_HANDOFF in result.get("stderr", ""), result
    # And the run's own bytes are still on disk: nothing was destroyed by the attempt.
    assert THIS_RUN in _note_bytes(wt)
