"""The handover note survives a REAL integrate, on real git (P2.15, trg-01cd6aef).

The sibling ``test_handoff_survives_restore.py`` pins ``restore_derived_to_head`` as a
unit. This one pins the **composition**, because the defect is an interaction and a unit
test of the carve-out would not have caught it: F5b writes the note, ``stash_run_written``
takes its bytes off the worktree so ``git merge`` cannot refuse on a tracked-and-dirty
path, the merge and its churn resolution run, ``restore_derived_to_head`` cleans up
everything re-derivable, and ``unstash_run_written`` — in a ``finally`` — puts the note
back. Five components; the note is correct only if all five agree.

Recorded as a ``category:"integration"`` behavior in the Test Completeness Ledger even
though the diff does not trip ``cross_component`` (verified against the real detectors,
not assumed): the flag decides escalation, the defect decides what must be tested.

Three things the external plan review asked to see proved rather than argued:

* the merge SUCCEEDS and the post-merge bytes are the ones F5b wrote (openai #2);
* a merge that FAILS after the stash still leaves the note in place, because the
  write-back sits in a ``finally`` and not on the success path (openai #3);
* the note ends modified-but-UNSTAGED, so nothing downstream inherits a staged
  derived snapshot (deepseek #4).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _c3_fixtures import write_handoff, write_iterate_entry  # noqa: E402
from lib.derived_snapshots import SESSION_HANDOFF  # noqa: E402
from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import integrate_main, integrate_merge  # noqa: E402
from verifiers.handoff_freshness import check_session_handoff_fresh  # noqa: E402
from verifiers.handoff_phase_canon import (  # noqa: E402
    check_c3_session_handoff_fresh_after_phase,
)

THIS_RUN = "iterate-2026-08-05-p2-15-handoff-freshness"
PREV_RUN = "iterate-2026-07-28-some-earlier-run"
THIS_AT = "2026-08-05T12:00:00+00:00"
PREV_AT = "2026-07-28T12:00:00+00:00"
SIBLING_RUN = "iterate-2026-08-04-a-sibling"
SIBLING_AT = "2026-08-04T09:00:00+00:00"


def _write_note(root: Path, run_id: str, at: str) -> str:
    """The note and its completion record, through the SHARED C3 builders.

    ``_c3_fixtures`` owns these two shapes because they are load-bearing: its ledger
    entry carries every field ``validate_iterate_entry`` requires and stamps the wall
    clock 900ms later than the anchor, so a suite cannot pass whether the code reads
    the anchor or the wall clock. A local copy would have been an entry the real
    writer refuses (Stage-2 code review, medium).
    """
    write_handoff(root, phase="iterate", run_id=run_id, timestamp=at)
    write_iterate_entry(root, run_id, at)
    return _note_bytes(root)


def _note_bytes(root: Path) -> str:
    return (root / SESSION_HANDOFF).read_text(encoding="utf-8")


def _seed_main(work: Path) -> str:
    """``main`` carries an EARLIER run's note — the real shape.

    Since iterate-2026-07-27-derived-snapshots-off-branch no iterate commits it, so the
    committed copy is whatever last touched it and every worktree starts from that.
    """
    _set_repo_identity(work)
    seeded = _write_note(work, PREV_RUN, PREV_AT)
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed an earlier run's handoff")
    _git(work, "push", "origin", "main")
    return seeded


def _stamp_f5b(wt: Path) -> str:
    """What F5b does in the worktree: write the note for the run that is finishing.

    Deliberately left unstaged — F6's add-list excludes derived snapshots, which is
    exactly why the note is tracked-and-dirty when the integrate starts.
    """
    stamped = _write_note(wt, THIS_RUN, THIS_AT)
    _git(wt, "add", "--", f".shipwright/agent_docs/iterates/{THIS_RUN}.json")
    _git(wt, "commit", "-m", "F5c: this run's ledger entry")
    return stamped


def test_the_note_survives_a_real_integrate_and_both_readers_agree(
    git_origin_repo, make_worktree,
) -> None:
    """The whole composition, against a mainline that MOVED the note.

    Mainline moving the same path is the case that makes ``git merge`` refuse on a dirty
    tracked file — the reason the stash exists at all — so it is the case worth driving.
    """
    work, _origin = git_origin_repo
    _seed_main(work)

    wt = make_worktree(work, "p2-15-handoff")
    _write(wt, "app.py", "the iterate's actual source change\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes source")
    stamped = _stamp_f5b(wt)

    # main advances ON THE NOTE, exactly as any other iterate's finalization would.
    write_handoff(work, phase="iterate", run_id=SIBLING_RUN, timestamp=SIBLING_AT)
    _git(work, "commit", "-am", "a sibling iterate moved the note on main")
    _git(work, "push", "origin", "main")

    result = integrate_main.integrate(wt, THIS_RUN, do_fetch=True)

    assert result["status"] == "ok", result
    assert "ledger-not-carried" not in result["steps"], (
        "the note could not be taken off the worktree, so the merge was run dirty"
    )
    assert "ledger-preserved" in result["steps"], result["steps"]

    # openai #2 — the bytes after the merge are the ones F5b wrote, not mainline's.
    assert _note_bytes(wt) == stamped

    # Both readers, from one run of the real thing.
    fresh = check_session_handoff_fresh(wt, THIS_RUN)
    assert fresh.ok is True, fresh.detail
    canon = check_c3_session_handoff_fresh_after_phase(wt, "iterate")
    assert canon.ok is True, canon.detail

    # deepseek #4 — modified, and NOT staged. `git checkout HEAD --` inside the stash
    # clears the index too, and the write-back touches only the worktree.
    status = _git(wt, "status", "--porcelain", "--", SESSION_HANDOFF).stdout
    assert status.startswith(" M"), f"expected an unstaged modification, got {status!r}"

    # AC4 restated where it matters most: the branch still ships no note.
    diff = _git(wt, "diff", "--name-only", "origin/main", "HEAD").stdout.split()
    assert SESSION_HANDOFF not in diff, "the note must contribute nothing to the PR diff"
    assert "app.py" in diff, "the real change must still be there"


def test_the_note_survives_a_merge_that_FAILS_after_the_stash(
    git_origin_repo, make_worktree, monkeypatch,
) -> None:
    """openai #3 — the write-back is in a ``finally``, so prove it from the failure side.

    Once the stash has run, its in-memory copy is the ONLY copy: the path on disk is back
    at ``HEAD``. Any exit that skipped the write-back would leave this run's worktree
    holding some earlier run's note, silently — which is the defect this change closes,
    arriving through the error path instead of the happy one.

    The failure is injected at ``regenerate_after_merge`` — AFTER the merge has really
    run and committed, which is where ``integrate_merge`` itself says nothing can be
    aborted any more. That makes the mainline move above load-bearing: the merge writes
    the sibling's note into the worktree, and only the write-back can put this run's
    bytes back over it. Injecting at ``merge_and_reconcile`` instead would raise before
    any merge happened, leaving the mainline commit unable to affect the assertion
    (Stage-2 code review, low).

    Patched on ``integrate_merge`` — the module that BINDS the name — not on
    ``integrate_regenerate`` where it is defined: ``integrate_merge`` imports it by
    value at load time, so rebinding the definition site would not be seen (ADR-045).
    """
    work, _origin = git_origin_repo
    _seed_main(work)

    wt = make_worktree(work, "p2-15-handoff-fail")
    _write(wt, "app.py", "source\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes source")
    stamped = _stamp_f5b(wt)

    write_handoff(work, phase="iterate", run_id=SIBLING_RUN, timestamp=SIBLING_AT)
    _git(work, "commit", "-am", "a sibling iterate moved the note on main")
    _git(work, "push", "origin", "main")

    boom = RuntimeError("merge exploded after the stash")

    def _explode(*_args, **_kwargs):
        raise boom

    monkeypatch.setattr(integrate_merge, "regenerate_after_merge", _explode)

    try:
        integrate_main.integrate(wt, THIS_RUN, do_fetch=True)
    except RuntimeError as exc:
        assert exc is boom
    else:  # pragma: no cover — only reached if the injection stops working
        raise AssertionError("the injected failure did not propagate")

    assert _note_bytes(wt) == stamped, (
        "the stash took the note off the worktree and the failure path did not put it "
        "back — this run's evidence would be gone, replaced by an earlier run's note"
    )
    assert check_session_handoff_fresh(wt, THIS_RUN).ok is True


def test_an_untouched_note_is_a_no_op(git_origin_repo, make_worktree) -> None:
    """deepseek #2 — a run that has not reached F5b leaves the note clean.

    Integrate is then a no-op on it, and the freshness check correctly says the note is
    not this run's rather than being laundered into a pass.

    **This passes with or without the carve-out, and it is a guard rather than a
    regression pin.** The first draft's docstring claimed it covered
    ``stash_run_written``'s clean-path branch, which it does not: with the carve-out
    reverted the note is not in ``RUN_WRITTEN_SNAPSHOTS`` at all, so the stash never
    looks at the path and the test passes for a different reason than the one written
    down (Stage-3 doubt review, test-validity).
    """
    work, _origin = git_origin_repo
    seeded = _seed_main(work)

    wt = make_worktree(work, "p2-15-handoff-clean")
    _write(wt, "app.py", "source\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes source")

    _write(work, "unrelated.py", "main moves elsewhere\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main advances")
    _git(work, "push", "origin", "main")

    result = integrate_main.integrate(wt, THIS_RUN, do_fetch=True)

    assert result["status"] == "ok", result
    assert "ledger-not-carried" not in result["steps"]
    # Untouched by this run, so it still holds what main committed — and the check
    # correctly says so rather than being laundered into a pass.
    assert _note_bytes(wt) == seeded
    assert check_session_handoff_fresh(wt, THIS_RUN).ok is False
