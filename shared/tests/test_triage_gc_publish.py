"""``triage_gc`` must not silently switch off the delivery channel — audit
2026-07-28, finding 16.

Reproduced against shipped code 2026-08-06: ``plan_main_tracked_drift`` returned
``no_drift`` before ``apply_gc`` and ``refused: main_tracked_diverged`` immediately
after, because the compaction removes lines from a tracked log and is not committed.
The outbox sweep then reports ``skipped`` on every later iterate. The tool printed
``APPLIED`` and said nothing about it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts", _SHARED / "scripts" / "tools", _SHARED / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import _sweep_helpers as h  # noqa: E402
import triage_gc  # noqa: E402
from lib.sweep_drift import plan_main_tracked_drift  # noqa: E402

_MACHINE = ('{{"event":"status","id":"{iid}","ts":"2026-08-02T00:00:00Z",'
            '"newStatus":"dismissed","by":"auditDetector","reason":"auditResolved"}}')


@pytest.fixture
def repo(git_origin_repo, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    work, _origin = git_origin_repo
    h.set_identity(work)
    h.seed_tracked(work, h.item("trg-mach"), _MACHINE.format(iid="trg-mach"), h.item("trg-keep"))
    return work


def _outbox(work: Path) -> Path:
    return work / ".shipwright" / "triage.outbox.jsonl"


def test_apply_leaves_the_channel_disabled_and_says_so(repo, capsys) -> None:
    """AC-1. The warning must name the state, the consequence and the remedy."""
    assert plan_main_tracked_drift(repo, _outbox(repo)).status == "no_drift"

    rc = triage_gc.main(["--project-root", str(repo), "--apply"])
    assert rc == 0
    out = capsys.readouterr().out

    # The defect is real in this run, not just described in the warning.
    after = plan_main_tracked_drift(repo, _outbox(repo))
    assert after.status == "refused" and "main_tracked_diverged" in after.reason

    assert "WARNING" in out and "NOT committed" in out
    assert "main_tracked_diverged" in out and "deliver NOTHING" in out
    assert "--commit" in out and "git" in out          # a remedy that can be run


def test_no_warning_when_there_was_nothing_to_compact(repo, capsys) -> None:
    """A dry run, and an apply with an empty plan, leave the log clean — warning
    about a divergence that does not exist would train the operator to ignore it."""
    triage_gc.main(["--project-root", str(repo)])
    assert "WARNING" not in capsys.readouterr().out
    triage_gc.main(["--project-root", str(repo), "--apply"])   # drops trg-mach
    capsys.readouterr()
    triage_gc.main(["--project-root", str(repo), "--apply"])   # nothing left to drop
    assert "WARNING" not in capsys.readouterr().out


def test_commit_keeps_the_sweep_working(repo, capsys) -> None:
    """AC-2. The whole point: after --commit the delivery channel still works."""
    rc = triage_gc.main(["--project-root", str(repo), "--apply", "--commit"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "committed: chore(triage): compact 1 machine-churn dismissal(s)" in out
    assert "WARNING" not in out
    assert plan_main_tracked_drift(repo, _outbox(repo)).status == "no_drift"
    assert h.git(repo, "status", "--porcelain", "--", ".shipwright/triage.jsonl").stdout == ""


def test_commit_refuses_when_the_log_already_carried_drift(repo, capsys) -> None:
    """External plan review, round 2. Background producers append to this log all
    day; folding their undelivered work into a commit that says "compact" would
    publish content the operator never reviewed under a false subject.

    And it refuses BEFORE compacting (code review): an earlier cut rewrote the log and
    only then declined to publish it, leaving exactly the divergence --commit prevents."""
    log = repo / ".shipwright" / "triage.jsonl"
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(h.item("trg-drift") + "\n")
    before = log.read_bytes()

    rc = triage_gc.main(["--project-root", str(repo), "--apply", "--commit"])

    assert rc == 2
    out = capsys.readouterr().out
    assert "--commit refused" in out and "nothing was rewritten" in out
    assert "reconcile_main_triage" in out
    assert log.read_bytes() == before                 # the compaction never happened
    assert h.git(repo, "log", "-1", "--format=%s").stdout.strip() == "seed triage"


def test_commit_refuses_when_the_log_moved_after_the_compaction(repo) -> None:
    """The WebUI writer does not take the triage lock, so it can append after GC
    released it and before the commit. Committing then publishes content GC never
    planned. Driven through the two functions directly, because the append has to
    land in the window BETWEEN them."""
    log = repo / ".shipwright" / "triage.jsonl"
    applied = triage_gc.apply_gc_reporting(repo, triage_gc.plan_gc(repo)["drop_ids"])
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(h.item("trg-late") + "\n")

    ok, note = triage_gc.commit_compaction(repo, applied.written_text, applied.dropped)
    assert ok is False
    assert "REFUSED" in note and "main_tracked_diverged" in note
    assert h.git(repo, "log", "-1", "--format=%s").stdout.strip() == "seed triage"
    assert "trg-late" in log.read_text(encoding="utf-8")


def test_commit_skips_on_a_detached_head(repo, capsys) -> None:
    """An unreferenced commit would lose the compaction outright — so refuse the whole
    run rather than compacting and then declining to publish."""
    log = repo / ".shipwright" / "triage.jsonl"
    before = log.read_bytes()
    sha = h.git(repo, "rev-parse", "HEAD").stdout.strip()
    h.git(repo, "checkout", "--detach", sha)

    rc = triage_gc.main(["--project-root", str(repo), "--apply", "--commit"])

    assert rc == 2
    out = capsys.readouterr().out
    assert "HEAD is detached" in out and "nothing was rewritten" in out
    assert log.read_bytes() == before


def test_commit_skips_when_something_is_staged(repo, capsys) -> None:
    """The third of the three guards ``reconcile_main_triage`` uses. AC-2 names it,
    and the extraction into lib.main_tree_guards was justified by this caller
    sharing it — so shipping only two would have made that rationale false."""
    log = repo / ".shipwright" / "triage.jsonl"
    before = log.read_bytes()
    (repo / "unrelated.txt").write_text("wip\n", encoding="utf-8")
    h.git(repo, "add", "--", "unrelated.txt")

    rc = triage_gc.main(["--project-root", str(repo), "--apply", "--commit"])

    assert rc == 2
    out = capsys.readouterr().out
    assert "something is staged" in out and "nothing was rewritten" in out
    assert log.read_bytes() == before
    assert h.git(repo, "log", "-1", "--format=%s").stdout.strip() == "seed triage"


def test_a_blocked_commit_never_compacts_so_there_is_nothing_to_warn_about(repo, capsys) -> None:
    """The pay-off of checking first: a refused --commit leaves the tree exactly as it
    was, so no divergence warning is owed. The earlier cut printed one — correctly, but
    only because it had already created the divergence it was warning about."""
    h.git(repo, "checkout", "--detach", h.git(repo, "rev-parse", "HEAD").stdout.strip())
    triage_gc.main(["--project-root", str(repo), "--apply", "--commit"])
    assert "WARNING" not in capsys.readouterr().out
    assert triage_gc.describe_post_gc_divergence(repo) is None


def test_commit_without_apply_is_rejected_not_ignored(repo) -> None:
    """It used to return 0 having silently done nothing at all."""
    with pytest.raises(SystemExit) as exc:
        triage_gc.main(["--project-root", str(repo), "--commit"])
    assert exc.value.code != 0


def test_unknown_git_state_still_warns_after_a_rewrite(repo, monkeypatch, capsys) -> None:
    """Silence on 'git could not answer' hid the very divergence AC-1 announces: the
    rewrite definitely removed lines, so an unconfirmed state must SPEAK."""
    from lib import triage_gc_publish
    monkeypatch.setattr(triage_gc_publish, "path_state_vs_head", lambda *a: "unknown")
    triage_gc.main(["--project-root", str(repo), "--apply"])
    out = capsys.readouterr().out
    assert "could not confirm" in out and "main_tracked_diverged" in out


def test_commit_from_inside_a_worktree_targets_main_not_the_iterate_branch(repo, capsys) -> None:
    """`--commit` is main-tree only. From a worktree it would land a
    `chore(triage): compact ...` commit on somebody's feature branch, so it refuses —
    and refuses BEFORE compacting, so the worktree's store is untouched too.

    (The first attempt resolved the main root for the git half while the store half
    stayed on --project-root. That compacted one file and compared the OTHER against
    it, and this test caught it.)"""
    wt = h.make_worktree(repo, "gc-from-worktree")
    branch_before = h.git(wt, "rev-parse", "HEAD").stdout.strip()
    wt_log_before = (wt / ".shipwright" / "triage.jsonl").read_bytes()

    rc = triage_gc.main(["--project-root", str(wt), "--apply", "--commit"])

    assert rc == 2
    out = capsys.readouterr().out
    assert "not the main repo root" in out and "nothing was rewritten" in out
    assert (wt / ".shipwright" / "triage.jsonl").read_bytes() == wt_log_before
    assert h.git(wt, "rev-parse", "HEAD").stdout.strip() == branch_before
    assert h.git(repo, "log", "-1", "--format=%s").stdout.strip() == "seed triage"


def test_apply_without_commit_still_works_from_a_worktree(repo, capsys) -> None:
    """The refusal above is scoped to --commit: compacting a store wherever it lives
    is the tool's job, and the warning then names that tree's divergence."""
    wt = h.make_worktree(repo, "gc-worktree-apply")
    rc = triage_gc.main(["--project-root", str(wt), "--apply"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "APPLIED" in out and "WARNING" in out


def test_a_non_git_directory_gets_no_divergence_warning(tmp_path: Path, capsys) -> None:
    """`--apply` on a plain directory made no git call at all before this change. An
    earlier cut reported "not a repository" as `unknown` and printed the full "the
    sweep will deliver NOTHING on every iterate" text, which is not true of a directory
    that has no sweep (doubt review)."""
    log = tmp_path / ".shipwright" / "triage.jsonl"
    log.parent.mkdir(parents=True)
    body = [h.HEADER, h.item("trg-m"), _MACHINE.format(iid="trg-m")]
    log.write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")

    rc = triage_gc.main(["--project-root", str(tmp_path), "--apply"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "APPLIED" in out
    assert "WARNING" not in out
    assert triage_gc.describe_post_gc_divergence(tmp_path) is None


def test_commit_compaction_reguards_itself(repo, monkeypatch) -> None:
    """It is the guarded half of the public re-export surface, and the CLI's preflight
    runs BEFORE the rewrite — two durable writes and a validation pass earlier. A HEAD
    that detaches in that interval would otherwise get a cheerful "committed:" on a
    dangling commit (doubt review). Driven directly, as a forgetful caller would."""
    from lib import triage_gc_publish
    applied = triage_gc.apply_gc_reporting(repo, triage_gc.plan_gc(repo)["drop_ids"])
    monkeypatch.setattr(triage_gc_publish, "is_detached", lambda root: True)

    ok, note = triage_gc.commit_compaction(repo, applied.written_text, applied.dropped)

    assert ok is False
    assert "HEAD is detached" in note and "main_tracked_diverged" in note
    assert h.git(repo, "log", "-1", "--format=%s").stdout.strip() == "seed triage"


def test_a_failed_commit_exits_nonzero(repo, monkeypatch, capsys) -> None:
    """The compaction happened and the commit did not, so the delivery channel is off.
    Returning 0 there let automation read it as a clean run (external code review).

    Driven by detaching HEAD in the window BETWEEN the CLI's pre-rewrite preflight and
    ``commit_compaction``'s re-check — which is also the case that re-check exists for.
    """
    from lib import triage_gc_publish
    calls: list[int] = []

    def detached_only_on_the_recheck(_root) -> bool:
        calls.append(1)
        return len(calls) > 1

    monkeypatch.setattr(triage_gc_publish, "is_detached", detached_only_on_the_recheck)

    rc = triage_gc.main(["--project-root", str(repo), "--apply", "--commit"])

    out = capsys.readouterr().out
    assert rc == 3, out
    assert "HEAD is detached" in out
    assert "WARNING" in out          # and the operator is still told what it costs
    assert len(calls) == 2, "the re-check never ran, so this proved nothing"


def test_describe_divergence_is_none_on_a_clean_log(repo) -> None:
    assert triage_gc.describe_post_gc_divergence(repo) is None
