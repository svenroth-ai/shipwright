"""Real-git half of the run-written carve-out: the run's ledger survives the merge.

The unit half — `RESTORABLE_SNAPSHOTS`, and which porcelain pairs
`restore_derived_to_head` may act on — is in test_derived_snapshots_run_written.py.
This drives `integrate` against a real repository, because what is under test is a git
behaviour and not a predicate.

**These exist as a SET because the carve-out has two failure modes and they are mutually
exclusive**: restore the ledger with the other ten and the run's evidence dies silently;
leave it dirty and the next `git merge` refuses to start. `lib/run_written_ledger.py`
carries the measurement for both. Helpers come from test_integrate_main.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import integrate_main, integrate_merge  # noqa: E402

_RUN_ID = "iterate-2026-07-27-derived-snapshots-off-branch"
_LEDGER = "shipwright_test_results.json"


def _seeded(git_origin_repo, make_worktree, slug: str):
    """`main` carries a PREVIOUS run's ledger; the branch carries a source change.

    The shared start of every case below, because what makes each one different is
    always what happens to the ledger AFTERWARDS, never how the branch got there.
    """
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _LEDGER, '{"iterate_latest": {"run_id": "iterate-OLD"}}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed ledger")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, slug)
    _write(wt, "app.py", "the real change\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "F6: source only")
    return work, wt


def test_the_run_keeps_its_ledger_when_mainline_moves_the_same_file(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """Both halves of the run-written carve-out, on real git, in one merge.

    Excluding ``shipwright_test_results.json`` from the restore protects its CONTENT
    and leaves it tracked-and-dirty — which is precisely what makes the next merge
    refuse to start ("Your local changes ... would be overwritten by merge") once
    mainline moves the same path. That is not hypothetical: ``main`` still tracks the
    file and one of its twelve most recent commits on 2026-07-30 changed it.

    So the two failures are mutually exclusive by construction and this pins BOTH at
    once. Restore the path and the ledger is gone; leave it dirty and the branch
    cannot advance. Only carrying the bytes across the merge passes.
    """
    mine = '{"iterate_latest": {"run_id": "%s", "totals": 42}}\n' % _RUN_ID

    work, wt = _seeded(git_origin_repo, make_worktree, "ledger-survives")
    _write(wt, _LEDGER, mine)                      # F5 writes THIS run's ledger...

    # ...and mainline moves the very same path, the #497 shape.
    _write(work, _LEDGER, '{"iterate_latest": {"run_id": "iterate-SOMEONE-ELSE"}}\n')
    _git(work, "commit", "-am", "main moves the ledger")
    _git(work, "push", "origin", "main")

    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", lambda *a, **k: {})
    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", f"a dirty ledger must not wedge the merge: {result}"
    assert "ledger-preserved" in result["steps"], result["steps"]
    assert (wt / _LEDGER).read_text(encoding="utf-8") == mine, "the run's evidence is gone"
    # Dirty AND UNSTAGED, and that is correct: no iterate commits this file, so it must
    # not be staged — but it must still be on disk for every F11 reader that opens it.
    # Not `.strip()`: that drops the leading status column, so a STAGED `M ` would pass
    # an assertion whose whole point is that the path is not staged.
    assert _git(wt, "status", "--porcelain", "--", _LEDGER).stdout.startswith(" M")


def test_a_blocked_merge_still_aborts_with_the_ledger_carried(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """The abort path — the case that made the write-back's placement load-bearing.

    ``git merge --abort`` is ``git reset --merge``, which refuses when a path differing
    between HEAD and the index has unstaged changes. Write the ledger back before the
    abort and that is exactly its state (mainline moved it, so the index differs), so
    the abort fails with ``Entry '<path>' not uptodate``, exit 128 — and it runs
    ``check=False``, so ``blocked`` would be returned claiming "merge aborted" over a
    tree still sitting in MERGE_HEAD. Both halves are asserted: the abort really took,
    AND the run's ledger came back afterwards.
    """
    mine = '{"iterate_latest": {"run_id": "%s"}}\n' % _RUN_ID

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _LEDGER, '{"iterate_latest": {"run_id": "iterate-OLD"}}\n')
    _write(work, "app.py", "base\n")               # tracked on BOTH sides, so the
    _git(work, "add", "-A")                        # divergence below really conflicts
    _git(work, "commit", "-m", "seed ledger and app")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "blocked-abort")
    _write(wt, "app.py", "ours\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "F6: source only")
    _write(wt, _LEDGER, mine)

    _write(work, _LEDGER, '{"iterate_latest": {"run_id": "iterate-SOMEONE-ELSE"}}\n')
    _write(work, "app.py", "theirs\n")            # a genuine non-churn conflict
    _git(work, "commit", "-am", "main moves the ledger and app.py")
    _git(work, "push", "origin", "main")

    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", lambda *a, **k: {})
    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "blocked", result
    # The claim the status makes must be TRUE: nothing left mid-merge. check=False —
    # `rev-parse --verify --quiet` EXITS 1 for the passing case, so the default
    # check=True would raise on success and report it as an error.
    merge_head = _git(wt, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False)
    assert merge_head.returncode != 0, "reported 'merge aborted' while still in MERGE_HEAD"
    assert (wt / _LEDGER).read_text(encoding="utf-8") == mine, "the run's evidence is gone"


def test_the_ledger_comes_back_untracked_when_mainline_deletes_it(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """A mainline deletion must not take this run's evidence with it.

    Pins the positive claim ``unstash_run_written`` makes in prose: the bytes are
    written back even with no HEAD copy to hold them, leaving an UNTRACKED file. That
    is the intended outcome — every F11 reader opens it by path — and it stays out of
    the commit by the same route anything untracked does.
    """
    mine = '{"iterate_latest": {"run_id": "%s"}}\n' % _RUN_ID

    work, wt = _seeded(git_origin_repo, make_worktree, "ledger-deleted-upstream")
    _write(wt, _LEDGER, mine)

    _git(work, "rm", "-q", "--", _LEDGER)          # main drops it entirely
    _git(work, "commit", "-m", "main removes the ledger")
    _git(work, "push", "origin", "main")

    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", lambda *a, **k: {})
    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", result
    assert (wt / _LEDGER).read_text(encoding="utf-8") == mine
    assert _git(wt, "status", "--porcelain", "--", _LEDGER).stdout.startswith("??"), (
        "with no HEAD copy the ledger is untracked — and must still be on disk"
    )



def test_an_unreadable_ledger_is_named_rather_than_skipped_in_silence(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """The cost of "never raises", made visible instead of swallowed.

    `stash_run_written` runs OUTSIDE integrate's own try, so letting a read error
    propagate would give `ensure_current` a traceback with no JSON — the shape every
    other failure here is built to avoid. But catching it silently is worse than it
    looks: the path stays dirty, the merge may then refuse, and the operator reads a
    git error about a file nothing in the flow ever mentioned. So it is caught AND
    reported. PermissionError is the real-world case (an indexer or AV holding the
    file open on Windows), which is why it is what gets simulated.
    """
    import lib.run_written_ledger as ds

    work, wt = _seeded(git_origin_repo, make_worktree, "ledger-unreadable")
    _write(wt, _LEDGER, '{"iterate_latest": {"run_id": "%s"}}\n' % _RUN_ID)

    def held_open(_path):
        exc = PermissionError(13, "Access is denied")
        exc.winerror = 32
        raise exc

    monkeypatch.setattr(ds, "durable_read_bytes", held_open)
    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", lambda *a, **k: {})

    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert "ledger-not-carried" in result["steps"], result["steps"]
    assert "ledger-preserved" not in result["steps"], "nothing was carried, so say so"


def test_a_staged_modification_with_the_file_deleted_is_carried_from_the_index(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """`MD` — the state that used to fall between the two functions, now CARRIED.

    Staged modification, worktree deletion. There is nothing on disk to read, and
    `restore_derived_to_head` skips the pair too (it is neither ` D` nor `D `, and the
    index still holds the ledger, which is exactly what must not be clobbered). So
    nothing acted on it: the path rode on, dirty, and if mainline moved it the merge
    refused with an error naming a file no step had mentioned.

    The bytes were never actually gone — they were in the INDEX. `git show :<path>`
    reads them, so this is carried like any other state rather than merely reported.
    The assertion is therefore the strong one: the run's ledger is back on disk with
    ITS content, not a `ledger-not-carried` consolation.
    """
    work, wt = _seeded(git_origin_repo, make_worktree, "ledger-md")

    mine = '{"iterate_latest": {"run_id": "%s"}}\n' % _RUN_ID
    _write(wt, _LEDGER, mine)
    _git(wt, "add", "--", _LEDGER)                 # staged...
    (wt / _LEDGER).unlink()                        # ...then gone from disk → `MD`
    assert _git(wt, "status", "--porcelain", "--", _LEDGER).stdout.startswith("MD")

    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", lambda *a, **k: {})
    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert "ledger-preserved" in result["steps"], result["steps"]
    assert "ledger-not-carried" not in result["steps"], "the index copy IS reachable"
    assert (wt / _LEDGER).read_text(encoding="utf-8") == mine
    # And the staged deletion is gone with it: `checkout HEAD --` clears index AND
    # worktree, so the ledger cannot ride into the merge commit either.
    assert _git(wt, "status", "--porcelain", "--", _LEDGER).stdout.startswith(" M")


def test_a_failed_write_back_is_reported_and_not_mistaken_for_nothing_to_do(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """The last path on which the run's ledger can still be lost.

    The write-back sits in a `finally`, where raising would mask the result or error
    being returned — so swallowing is forced. Being silent about it is not, and the
    silence is what would make this indistinguishable from the ordinary case where
    there was nothing to carry at all. That is the exact confusion trg-ad29a709 cost
    whole sessions, arriving one layer further in.
    """
    import lib.run_written_ledger as ds

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _LEDGER, '{"iterate_latest": {"run_id": "iterate-OLD"}}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed ledger")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "ledger-writeback-fails")
    _write(wt, "app.py", "the real change\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "F6: source only")
    _write(wt, _LEDGER, '{"iterate_latest": {"run_id": "%s"}}\n' % _RUN_ID)

    def refuse(_path, _content):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(ds, "durable_atomic_write", refuse)
    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", lambda *a, **k: {})

    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert "ledger-writeback-failed" in result["steps"], result["steps"]
    assert "ledger-preserved" not in result["steps"]
    # The STATUS, not just the step. `ensure_current` derives its verdict from this key
    # and F11 gates on the exit code, so a regression that appends the step and still
    # returns `ok` would report success over a lost ledger — and would pass an assertion
    # that only read `steps`. That is the whole reason the `finally` returns at all.
    assert result["status"] == "ledger_writeback_failed", result
    assert _LEDGER in result["failed"], result


def test_an_exception_mid_merge_surfaces_AND_leaves_the_ledger_on_disk(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """Why the write-back is in a `finally` at all — the half no status can express.

    Between the stash and the write-back the ONLY copy of the run's evidence is in
    memory, so anything that raises in that window takes it unless a `finally` puts it
    back. The earlier draft returned from that `finally`, which restored the file but
    also SWALLOWED the exception — a crash quietly downgraded to a status. Both halves
    are asserted here: the error still reaches the caller, and the ledger is on disk.
    """
    mine = '{"iterate_latest": {"run_id": "%s"}}\n' % _RUN_ID
    work, wt = _seeded(git_origin_repo, make_worktree, "ledger-exception")
    _write(wt, _LEDGER, mine)

    def boom(*a, **k):
        raise RuntimeError("the merge blew up")

    monkeypatch.setattr(integrate_main, "merge_and_reconcile", boom)

    with pytest.raises(RuntimeError, match="the merge blew up"):
        integrate_main.integrate(wt, _RUN_ID, do_fetch=False)

    assert (wt / _LEDGER).read_text(encoding="utf-8") == mine, "the finally must still run"
