"""``reconcile_main_triage`` must not leave the delivery channel disabled when its
commit fails — audit 2026-07-28, finding 16 (second half).

The dedup rewrite REMOVES lines, so an uncommitted one makes the working log a
non-append-only extension of HEAD; ``plan_main_tracked_drift`` then refuses
``main_tracked_diverged`` and the outbox sweep delivers nothing, forever. There was
no rollback on any failure branch and the reason said only ``commit_failed``.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts", _SHARED / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import _sweep_helpers as h  # noqa: E402
from lib import reconcile_triage as rt  # noqa: E402
from lib.sweep_drift import plan_main_tracked_drift  # noqa: E402


def _append(iid: str, *, title: str, ts: str) -> str:
    return (f'{{"event":"append","id":"{iid}","ts":"{ts}",'
            f'"originalTs":"2026-08-01T00:00:00Z","title":"{title}","status":"triage"}}')


#: The v1 append that is COMMITTED in HEAD. A refreshed v2 landing as drift makes the
#: keep-last collapse remove a HEAD line — which is what turns the rewrite from a
#: harmless tidy-up into a divergence. (A duplicate confined to the drift collapses
#: to something that is still an append-only extension of HEAD, so it cannot
#: reproduce finding 16 — measured while writing this file.)
_V1 = _append("trg-a", title="v1", ts="2026-08-01T00:00:00Z")


@pytest.fixture
def repo(git_origin_repo, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    work, _origin = git_origin_repo
    h.set_identity(work)
    h.seed_tracked(work, _V1)
    return work


def _add_dupe_drift(work: Path) -> str:
    """Uncommitted drift the dedup WILL rewrite destructively: a refreshed append for
    an id HEAD already carries, so keep-last drops HEAD's copy."""
    log = work / ".shipwright" / "triage.jsonl"
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(_append("trg-a", title="v2", ts="2026-08-03T00:00:00Z") + "\n")
    return log.read_text(encoding="utf-8")


def _fail_commit(monkeypatch, *, returncode: int = 1, stderr: str = "hook rejected"):
    real = rt.run_git_soft

    def wrapper(args, **kwargs):
        if args and args[0] == "commit":
            return subprocess.CompletedProcess(["git", *args], returncode, "", stderr)
        return real(args, **kwargs)

    monkeypatch.setattr(rt, "run_git_soft", wrapper)


def test_failed_commit_rolls_the_rewrite_back(repo, monkeypatch) -> None:
    """AC-4. The tree is left exactly as found, so the sweep still works."""
    before = _add_dupe_drift(repo)
    outbox = repo / ".shipwright" / "triage.outbox.jsonl"
    _fail_commit(monkeypatch)

    result = rt.reconcile_main_triage(repo, allow_ci=True)

    assert result.status == "error"
    assert "rolled back" in result.reason and "commit_failed" in result.reason
    assert (repo / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8") == before
    # The real deliverable: the delivery channel is still usable.
    assert plan_main_tracked_drift(repo, outbox).status == "adoptable"


def test_without_the_rollback_the_channel_would_be_dead(repo, monkeypatch) -> None:
    """The discriminating half — pin the state the rollback prevents, so a
    regression that stops restoring is caught by more than a wording assertion."""
    _add_dupe_drift(repo)
    outbox = repo / ".shipwright" / "triage.outbox.jsonl"
    _fail_commit(monkeypatch)
    monkeypatch.setattr(rt, "_rollback_failed_commit",
                        lambda *a, **k: "commit_failed: (rollback disabled for this test)")

    rt.reconcile_main_triage(repo, allow_ci=True)

    plan = plan_main_tracked_drift(repo, outbox)
    assert plan.status == "refused" and "main_tracked_diverged" in plan.reason


def test_rollback_refuses_when_another_writer_appended(repo, monkeypatch) -> None:
    """Restoring would DELETE that append — the wrong trade for a module whose
    subject is not losing records. Nothing is restored and the reason says so."""
    _add_dupe_drift(repo)
    log = repo / ".shipwright" / "triage.jsonl"
    real_write = rt._atomic_write

    def write_then_append(path, text):
        real_write(path, text)
        with Path(path).open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(h.item("trg-late") + "\n")

    monkeypatch.setattr(rt, "_atomic_write", write_then_append)
    _fail_commit(monkeypatch)

    result = rt.reconcile_main_triage(repo, allow_ci=True)

    assert "NOT rolled back" in result.reason and "another writer" in result.reason
    assert "main_tracked_diverged" in result.reason
    assert "trg-late" in log.read_text(encoding="utf-8")   # the append survived


def test_rollback_refuses_when_head_moved(repo, monkeypatch) -> None:
    """A non-zero commit exit is strong evidence but not proof that no commit was
    created (external plan review). If HEAD moved, restoring would re-diverge."""
    _add_dupe_drift(repo)
    real = rt.run_git_soft
    seen = {"n": 0}

    def wrapper(args, **kwargs):
        if args and args[0] == "commit":
            # Make a real commit, then report failure — the "it landed anyway" shape.
            real(["commit", "-m", "sneaky", "--", ".shipwright/triage.jsonl"],
                 cwd=kwargs.get("cwd"), timeout=kwargs.get("timeout"))
            seen["n"] += 1
            return subprocess.CompletedProcess(["git", *args], 1, "", "reported as failed")
        return real(args, **kwargs)

    monkeypatch.setattr(rt, "run_git_soft", wrapper)
    result = rt.reconcile_main_triage(repo, allow_ci=True)

    assert seen["n"] == 1
    assert "NOT rolled back" in result.reason and "HEAD moved" in result.reason


def test_failed_commit_leaves_the_index_clean(repo, monkeypatch) -> None:
    """Both external reviewers asserted a failed commit leaves the rewrite STAGED
    "because `git add` occurred". It does not: this module never calls `git add`, and
    `git commit -- <path>` commits worktree content through a temporary index. Tested
    rather than argued — if it ever becomes true, this fails and the rollback must
    grow an index half."""
    _add_dupe_drift(repo)
    _fail_commit(monkeypatch)
    rt.reconcile_main_triage(repo, allow_ci=True)
    assert h.git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0


def test_no_rewrite_means_nothing_to_roll_back(repo, monkeypatch) -> None:
    """Drift with no duplicates: the dedup changes nothing, so a failed commit has
    no rewrite to undo and the reason stays the plain one."""
    log = repo / ".shipwright" / "triage.jsonl"
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(h.item("trg-b") + "\n")
    before = log.read_text(encoding="utf-8")
    _fail_commit(monkeypatch)

    result = rt.reconcile_main_triage(repo, allow_ci=True)

    assert result.reason == "commit_failed: hook rejected"
    assert log.read_text(encoding="utf-8") == before


def test_dedup_warnings_reach_the_result(repo, monkeypatch) -> None:
    """AC-6: this caller used to discard the dedup's warnings with ``deduped, _ =``."""
    log = repo / ".shipwright" / "triage.jsonl"
    a1 = ('{"event":"append","id":"trg-c","ts":"2026-08-01T00:00:00Z",'
          '"originalTs":"2026-08-01T00:00:00Z","title":"v1","status":"triage"}')
    a2 = ('{"event":"append","id":"trg-c","ts":"2026-08-02T00:00:00Z",'
          '"originalTs":"2026-08-01T00:00:00Z","title":"v2","status":"triage"}')
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(a1 + "\n")
        fh.write(a2 + "\n")

    result = rt.reconcile_main_triage(repo, allow_ci=True)

    assert result.status == "committed", result.to_dict()
    assert result.warnings and "superseded" in result.warnings[0]
    assert "warnings" in result.to_dict()
