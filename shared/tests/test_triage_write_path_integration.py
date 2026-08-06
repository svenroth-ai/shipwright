"""Integration coverage for the tracked triage store's WRITE PATH — the
``cross_component`` obligation of iterate-2026-08-06-triage-store-write-path.

Four defects were fixed in four modules that each looked self-contained:
``triage_gc`` (compaction), ``reconcile_triage`` (fold-and-commit),
``sweep_drift`` (adopt-and-restore) and ``churn_merge``/``triage_dedup`` (dedup).
Unit tests prove each one in isolation. What they cannot prove is the thing the
card is actually about: these components share ONE artifact, and each of them can
leave it in a state that silently disables the others.

So this file drives them against a real git repo, in the order an operator hits
them, and asserts on the property that spans all four: **the delivery channel still
works, and when it does not, something said so.**

Reference shape: ``shared/tests/test_parallel_merge_cascade_integration.py``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts", _SHARED / "scripts" / "tools", _SHARED / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import _sweep_helpers as h  # noqa: E402
import triage_gc  # noqa: E402
from lib import reconcile_triage as rt  # noqa: E402
from lib import sweep_drift_restore as sdr  # noqa: E402
from lib.sweep_drift import plan_main_tracked_drift  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402
from lib.sweep_result import sweep_warnings  # noqa: E402

_CHURN = ('{{"event":"status","id":"{iid}","ts":"2026-08-02T00:00:00Z",'
          '"newStatus":"dismissed","by":"auditDetector","reason":"auditResolved"}}')


def _append(iid: str, *, title: str, ts: str) -> str:
    """An append carrying ``originalTs``, as every real one does. ``h.item`` omits it,
    which is fine for distinct ids but cannot express a REFRESH of an existing item —
    two anchorless same-id appends read as a possible id collision (lib/triage_dedup)."""
    return (f'{{"event":"append","id":"{iid}","ts":"{ts}",'
            f'"originalTs":"2026-08-01T00:00:00Z","title":"{title}","status":"triage"}}')


@pytest.fixture
def project(git_origin_repo, monkeypatch):
    """A main tree with an origin, one machine-churn item and one live item."""
    monkeypatch.delenv("CI", raising=False)
    work, _origin = git_origin_repo
    h.set_identity(work)
    h.seed_tracked(work, h.item("trg-churn"), _CHURN.format(iid="trg-churn"),
                   _append("trg-live", title="v1", ts="2026-08-01T00:00:00Z"))
    return work


def _outbox(work: Path) -> Path:
    return work / ".shipwright" / "triage.outbox.jsonl"


def test_gc_then_sweep_compose_only_because_the_compaction_is_committed(project, capsys):
    """The end-to-end shape of finding 16.

    An operator compacts the backlog, then the next iterate starts and its worktree
    setup sweeps buffered triage into the branch. Those are different tools, run at
    different times, by different people — and before this change the first one
    silently disabled the second one for good.
    """
    work = project

    # 1. A background producer buffers a dismiss into the gitignored outbox.
    h.write_outbox(work, h.item("trg-buffered"))

    # 2. The operator compacts — WITHOUT --commit. The tool must say what it did.
    triage_gc.main(["--project-root", str(work), "--apply"])
    warned = capsys.readouterr().out
    assert "WARNING" in warned and "main_tracked_diverged" in warned

    # 3. That is not a hypothetical: the next iterate's sweep is now dead.
    wt_dead = h.make_worktree(work, "iterate-a")
    dead = sweep_outbox_to_branch(work, wt_dead, default_branch="main")
    # Exact, not a disjunction: the mechanism produces `skipped` + this reason, and an
    # `or` would also pass on an unrelated validator failure (code review).
    assert dead.status == "skipped", dead.to_dict()
    assert "main_tracked_diverged" in dead.reason, dead.to_dict()
    assert h.item("trg-buffered") not in h.branch_triage_lines(wt_dead)
    # ...and the operator hears about it rather than reading a green sweep.
    assert any("main_tracked_diverged" in n for n in sweep_warnings(dead)), dead.to_dict()

    # 4. Committing the compaction — what --commit does for you — revives it.
    h.git(work, "commit", "-m", "chore(triage): compact", "--", ".shipwright/triage.jsonl")
    # `no_drift` exactly: `adoptable` would mean the commit did NOT clean the log, i.e.
    # the opposite of what this step proves (code review).
    assert plan_main_tracked_drift(work, _outbox(work)).status == "no_drift"

    wt = h.make_worktree(work, "iterate-b")
    alive = sweep_outbox_to_branch(work, wt, default_branch="main")
    assert alive.status == "committed", alive.to_dict()
    assert h.item("trg-buffered") in h.branch_triage_lines(wt)


def test_gc_with_commit_never_breaks_the_sweep_in_the_first_place(project):
    """AC-2 composed: the supported one-step path leaves the channel working."""
    work = project
    h.write_outbox(work, h.item("trg-buffered"))

    assert triage_gc.main(["--project-root", str(work), "--apply", "--commit"]) == 0

    wt = h.make_worktree(work, "iterate-c")
    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert h.item("trg-buffered") in h.branch_triage_lines(wt)
    # The compaction really happened, and the live item survived it. Asserted on
    # MAIN's tracked log, not the branch: the worktree is cut from ORIGIN/main, which
    # does not carry the compaction commit — so a branch-side assertion here would be
    # measuring the wrong tree (and passed for the wrong reason until this was fixed).
    main_log = (work / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    assert "trg-churn" not in main_log
    assert "trg-live" in main_log


def test_main_tree_drift_is_adopted_and_a_late_append_is_not_destroyed(project, monkeypatch):
    """finding 23 composed: the sweep adopts uncommitted main-tree drift, and a writer
    landing in the restore window is recovered rather than overwritten."""
    work = project
    log = work / ".shipwright" / "triage.jsonl"
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(h.item("trg-drift") + "\n")

    real_claim = sdr._claim_salvage_path

    def claim_then_append(triage_path: Path) -> Path:
        claimed = real_claim(triage_path)
        with triage_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(h.item("trg-late") + "\n")
        return claimed

    monkeypatch.setattr(sdr, "_claim_salvage_path", claim_then_append)

    wt = h.make_worktree(work, "iterate-d")
    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert h.item("trg-drift") in h.branch_triage_lines(wt)
    assert "late_append_salvaged" in result.reason
    # Main's tracked log is back to HEAD, and no salvage file was left behind.
    assert "trg-drift" not in log.read_text(encoding="utf-8")
    assert list((work / ".shipwright").glob("triage.jsonl.salvage-*")) == []

    # The late line does NOT reach THIS branch — the sweep materialized the outbox
    # before the restore ran, so it arrives one step later. That is the correct
    # behaviour and the claim being made is "preserved", not "delivered this run":
    # it is in the outbox, and the NEXT sweep delivers it. Asserting it onto this
    # branch would have been asserting a bug.
    assert h.item("trg-late") in h.outbox_lines(work)
    wt2 = h.make_worktree(work, "iterate-d2")
    follow_up = sweep_outbox_to_branch(work, wt2, default_branch="main")
    assert follow_up.status == "committed", follow_up.to_dict()
    assert h.item("trg-late") in h.branch_triage_lines(wt2)


def test_a_failed_reconcile_commit_leaves_the_sweep_usable(project, monkeypatch):
    """finding 16's second half, composed: reconcile's rewrite is destructive, so a
    failed commit used to strand main diverged. The rollback keeps the sweep alive."""
    work = project
    log = work / ".shipwright" / "triage.jsonl"
    # A REFRESHED append (same id, same originalTs) for an id HEAD already carries →
    # the keep-last collapse drops a HEAD line, which is what makes the rewrite
    # destructive and an uncommitted result a divergence. An ANCHORLESS pair would
    # instead be treated as a possible id collision and kept, so reconcile would
    # return `invalid` and never reach the commit this test is about.
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(_append("trg-live", title="v2", ts="2026-08-03T00:00:00Z") + "\n")

    real = rt.run_git_soft

    def fail_commit(args, **kwargs):
        if args and args[0] == "commit":
            return subprocess.CompletedProcess(["git", *args], 1, "", "hook rejected")
        return real(args, **kwargs)

    monkeypatch.setattr(rt, "run_git_soft", fail_commit)
    result = rt.reconcile_main_triage(work, allow_ci=True)
    assert result.status == "error" and "rolled back" in result.reason, result.to_dict()

    # The channel survived the failure: a following iterate still delivers.
    h.write_outbox(work, h.item("trg-buffered"))
    wt = h.make_worktree(work, "iterate-e")
    swept = sweep_outbox_to_branch(work, wt, default_branch="main")
    assert swept.status == "committed", swept.to_dict()
    assert h.item("trg-buffered") in h.branch_triage_lines(wt)


def test_an_id_collision_blocks_loudly_instead_of_deleting_a_record(project):
    """finding 25 composed: two DISTINCT items sharing a 32-bit id must not have one
    of them quietly deleted on the way to the branch. The sweep blocks, and the
    reason names the collision and the repair tool."""
    work = project
    a = ('{"event":"append","id":"trg-dupe","ts":"2026-08-01T00:00:00Z",'
         '"originalTs":"2026-01-01T00:00:00Z","title":"finding A","status":"triage"}')
    b = ('{"event":"append","id":"trg-dupe","ts":"2026-08-02T00:00:00Z",'
         '"originalTs":"2026-07-07T00:00:00Z","title":"finding B","status":"triage"}')
    h.write_outbox(work, a, b)

    wt = h.make_worktree(work, "iterate-f")
    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "invalid", result.to_dict()
    joined = " ".join(result.errors)
    assert "32-bit id collision" in joined and "triage_repair.py" in joined
    # Nothing was delivered, but nothing was destroyed either — both are still buffered.
    buffered = _outbox(work).read_text(encoding="utf-8")
    assert "finding A" in buffered and "finding B" in buffered


def test_a_benign_refresh_still_delivers_and_only_warns(project):
    """The other side of finding 25, and the thing three reviewers warned about: a
    keep-last collapse of ONE logical item must NOT block delivery."""
    work = project
    v1 = ('{"event":"append","id":"trg-ref","ts":"2026-08-01T00:00:00Z",'
          '"originalTs":"2026-08-01T00:00:00Z","title":"v1","status":"triage"}')
    v2 = ('{"event":"append","id":"trg-ref","ts":"2026-08-02T00:00:00Z",'
          '"originalTs":"2026-08-01T00:00:00Z","title":"v2","status":"triage"}')
    h.write_outbox(work, v1, v2)

    wt = h.make_worktree(work, "iterate-g")
    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert result.dedup_notes and "superseded" in result.dedup_notes[0]
    assert any("dedup" in n for n in sweep_warnings(result))
    branch = h.branch_triage_lines(wt)
    assert v2 in branch and v1 not in branch
