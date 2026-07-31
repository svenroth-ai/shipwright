"""D2 sweep — an append landing DURING the commit window must survive the GC.

The gap `test_sweep_outbox_concurrency.py` cannot see. That module's producer
appends through ``triage.append_triage_item``, which **takes the canonical lock**,
so it can only ever serialize *around* the sweep — never interleave *inside* the
critical section. It also notes "origin never advanced -> nothing GC'd", so the
survivor rewrite it would have to catch never even executes there.

The writer this module models is the NON-cooperating one, which is real and
documented: ``triage_repair.py`` records that the WebUI uses ``proper-lockfile``,
which does not compose with the Python byte lock — and the WebUI is the operator's
primary dismiss surface. An editor or a stray ``git`` invocation is the same shape.

The window is not hypothetical either: between the outbox read and the survivor
write sit the drift adoption's own outbox write, ``git add``, ``git diff --cached``
and a ``git commit`` budgeted 120 s. The sibling ``sweep_drift.commit_main_tracked_drift``
re-reads the outbox inside this very section for exactly this reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib import sweep_outbox as sweep_mod  # noqa: E402


@pytest.fixture
def repo(git_origin_repo):
    work, origin = git_origin_repo
    h.set_identity(work)
    return work, origin


def _append_during_commit(monkeypatch, work: Path, line: str) -> dict:
    """Make the sweep's own ``git commit`` the moment an unlocked writer appends.

    Patches the module OBJECT (never the ``"lib.sweep_outbox.run_git_soft"`` string —
    ADR-045: the string form can bind a different ``lib``). Returns a dict whose
    ``fired`` key proves the injection actually happened, so a refactor that stops
    routing the commit through this seam fails loudly instead of passing vacuously.
    """
    real_run_git = sweep_mod.run_git_soft
    state = {"fired": False}

    def wrapper(args, **kwargs):
        if args and args[0] == "commit" and not state["fired"]:
            state["fired"] = True
            h.write_outbox(work, line)  # unlocked, exactly like a foreign writer
        return real_run_git(args, **kwargs)

    monkeypatch.setattr(sweep_mod, "run_git_soft", wrapper)
    return state


def test_append_during_commit_window_is_not_deleted_by_the_gc(repo, monkeypatch) -> None:
    """An unlocked append made while the sweep commits must SURVIVE the GC rewrite.

    ``trg-seed`` is already in origin, so it is GC-delivered and the survivor
    rewrite actually fires (``if gc_dropped or quarantined``) — without that the
    stale-list write is never reached and the bug is invisible.
    """
    work, _ = repo
    h.seed_tracked(work, h.item("trg-seed"))
    wt = h.make_worktree(work, "gc-reread")

    # delivered in origin -> GC drops it -> the survivor rewrite executes
    h.write_outbox(work, h.item("trg-seed"))
    # NOT in origin -> genuinely new -> the sweep commits, opening the window
    h.write_outbox(work, h.item("trg-new"))

    state = _append_during_commit(monkeypatch, work, h.item("trg-race"))

    result = sweep_mod.sweep_outbox_to_branch(work, wt, default_branch="main")
    assert state["fired"], "the commit seam never fired — the test proves nothing"
    assert result.status == "committed", result.to_dict()
    assert result.gc_dropped >= 1, (
        f"the survivor rewrite did not fire, so this test cannot see the bug: "
        f"{result.to_dict()}"
    )

    surviving = h.outbox_lines(work)
    branch = h.branch_triage_lines(wt)

    assert h.item("trg-race") in surviving or h.item("trg-race") in branch, (
        "an append made during the commit window was DELETED by the GC survivor "
        "write, which was computed from the pre-commit read.\n"
        f"outbox={sorted(surviving)}\nbranch={sorted(branch)}"
    )


def test_delivered_line_is_still_gcd_when_an_append_races(repo, monkeypatch) -> None:
    """The re-read must not weaken the GC: a delivered line still gets dropped.

    Guards the opposite direction — re-reading the outbox could trivially be
    'fixed' by never dropping anything, which would make the first test pass while
    breaking the GC's whole purpose.
    """
    work, _ = repo
    h.seed_tracked(work, h.item("trg-seed"))
    wt = h.make_worktree(work, "gc-reread-drop")

    h.write_outbox(work, h.item("trg-seed"))
    h.write_outbox(work, h.item("trg-new"))

    _append_during_commit(monkeypatch, work, h.item("trg-race"))
    result = sweep_mod.sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    surviving = h.outbox_lines(work)
    assert h.item("trg-seed") not in surviving, (
        f"origin-delivered line survived the GC: {sorted(surviving)}"
    )
