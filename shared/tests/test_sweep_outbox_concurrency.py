"""D2 sweep — AC1 EMPIRICAL concurrency + lock-contention proofs (no mocks).

The most data-loss-sensitive assertions in the campaign. Split from
``test_sweep_outbox.py`` so each module stays under the 300-LOC guideline. Uses
REAL threads + the REAL canonical ``triage._FileLock`` + REAL git: a concurrent
background producer appending to the outbox via the canonical lock must lose
ZERO line and duplicate ZERO line while the sweep runs.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
import triage  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402


@pytest.fixture
def repo(git_origin_repo):
    work, origin = git_origin_repo
    h.set_identity(work)
    return work, origin


def _concurrent_producer(work: Path, ids: list[str], started: threading.Event) -> None:
    """Append each id to the outbox via the REAL locked triage append path."""
    started.set()
    for iid in ids:
        triage.append_triage_item(
            work, source="plugin-sync", severity="low", kind="maintenance",
            title=iid, detail="d", to_outbox=True,
        )


@pytest.mark.parametrize("trial", range(20))
def test_concurrent_producer_loses_no_line(repo, trial: int) -> None:
    """A real concurrent producer appends to the outbox (via the canonical lock)
    WHILE the sweep runs. ZERO line may be lost or duplicated. Compared by full
    before/after line-SETS, not counts. Repeated to exercise contention."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-seed"))
    wt = h.make_worktree(work, f"sweep-conc-{trial}")

    pre_ids = [f"trg-pre{trial:02d}{i:02d}" for i in range(5)]
    for iid in pre_ids:
        triage.append_triage_item(
            work, source="plugin-sync", severity="low", kind="maintenance",
            title=iid, detail="d", to_outbox=True,
        )

    conc_ids = [f"trg-cnc{trial:02d}{i:02d}" for i in range(5)]
    started = threading.Event()
    producer = threading.Thread(target=_concurrent_producer, args=(work, conc_ids, started))
    producer.start()
    started.wait(timeout=5.0)

    result = sweep_outbox_to_branch(work, wt, default_branch="main")
    producer.join(timeout=10.0)
    assert not producer.is_alive()
    assert result.status in ("committed", "no_change"), result.to_dict()

    # UNION of {branch-committed lines} ∪ {surviving outbox lines} must contain
    # EVERY append id (pre + concurrent). origin never advanced → nothing GC'd.
    union = h.branch_triage_lines(wt) | h.outbox_lines(work)
    for iid in pre_ids + conc_ids:
        present = any(f'"title":"{iid}"' in ln for ln in union)
        assert present, (
            f"trial {trial}: id {iid} LOST — not on branch nor in outbox.\n"
            f"union={sorted(union)}"
        )

    branch_appends = [ln for ln in h.branch_triage_lines(wt) if '"event":"append"' in ln]
    assert len(branch_appends) == len(set(branch_appends)), "duplicate append on branch"


def test_sweep_blocks_on_held_canonical_lock(repo) -> None:
    """Proof the sweep ACQUIRES the canonical triage lock (not a private one): a
    thread holding ``triage._FileLock(triage._lock_path(main_root))`` blocks the
    sweep until released. The contention proof behind AC1 — a producer holding
    the SAME lock (exactly what ``append_triage_item(to_outbox=True)`` takes)
    serializes the ENTIRE sweep, so no append can interleave mid-section."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-lockheld")
    h.write_outbox(work, h.item("trg-bbbb"))

    sweep_started = threading.Event()
    sweep_finished = threading.Event()
    sweep_result: list = []

    def run_sweep() -> None:
        sweep_started.set()
        sweep_result.append(sweep_outbox_to_branch(work, wt, default_branch="main"))
        sweep_finished.set()

    with triage._FileLock(triage._lock_path(work)):
        t = threading.Thread(target=run_sweep)
        t.start()
        sweep_started.wait(timeout=5.0)
        blocked = not sweep_finished.wait(timeout=1.0)
        assert blocked, "sweep finished while the canonical lock was HELD"
    t.join(timeout=15.0)
    assert not t.is_alive()
    assert sweep_finished.is_set()
    assert sweep_result and sweep_result[0].status == "committed", sweep_result
    assert h.item("trg-bbbb") in h.branch_triage_lines(wt)
