"""D2V — EMPIRICAL verification gate: concurrency stress (>=200 real trials).

Campaign 2026-06-08-triage-outbox-delivery / D2V — the HARD safety gate stacked
under D3. This module owns mandatory method 1 (CONCURRENCY STRESS) and the
evidence-flush orchestration; the abandoned-branch / exactly-once / no-pollution
e2e proofs (methods 2-4) live in ``test_d2v_empirical_gate_e2e.py`` so each
module stays under the 300-LOC guideline.

Method 1 — CONCURRENCY STRESS (no mocks): a REAL concurrent producer (a thread
calling the canonical ``triage.append_triage_item(..., to_outbox=True)``, which
takes the SAME ``_FileLock`` the sweep holds) appends to the outbox WHILE the
REAL ``sweep_outbox_to_branch`` runs, repeated ``_STRESS_TRIALS`` (>=200) times
with randomized jitter so the lock-interleaving varies. On EVERY trial we assert
ZERO line loss AND ZERO duplication by comparing the FULL before/after line-SETS
(expected append-ids == ids present in {branch-committed} ∪ {surviving outbox}),
not just counts.

The heavy >=200-trial run is ``@pytest.mark.slow`` so the default fast suite
(``-m 'not slow'``) stays tractable; run the gate via ``pytest -m slow
shared/tests/test_d2v_empirical_gate.py``. A FAST 12-trial smoke
(``test_concurrency_smoke``) runs in the default suite so a regression in the
harness itself is caught without the multi-minute load — but the smoke does NOT
satisfy the gate (the artifact records the heavy count).
"""

from __future__ import annotations

import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # helpers

import _d2v_helpers as ev  # noqa: E402
import _sweep_helpers as h  # noqa: E402
import triage  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402

#: The load-bearing proof count. >=200 per the D2V spec — do NOT reduce to make
#: the run fast (the spec calls the heavy run "the load-bearing proof").
_STRESS_TRIALS = 200
_SMOKE_TRIALS = 12
#: appends per side per trial (pre-seeded + concurrent).
_PRE = 4
_CONC = 4
#: Deterministic base seed (external-review openai-M7) so the jitter/interleave
#: schedule is reproducible + recorded in the evidence artifact for replay. Each
#: trial reseeds with ``_BASE_SEED + trial`` before drawing its timing choices.
_BASE_SEED = 20260608


@pytest.fixture
def repo(git_origin_repo):
    work, _origin = git_origin_repo
    h.set_identity(work)
    return work


def _producer(work: Path, ids: list[str], first_done: threading.Event, jitter: float) -> None:
    """Append each id to the outbox via the REAL locked triage append path. Signal
    ``first_done`` AFTER the first append, then keep appending the rest with a
    randomized sub-ms jitter — so the parent starts the sweep with at least one
    append already in flight AND more appends arriving DURING the sweep window
    (external-review: guarantee real overlap, not a producer that finished early)."""
    for i, iid in enumerate(ids):
        if jitter and i:
            time.sleep(random.uniform(0.0, jitter))
        triage.append_triage_item(
            work, source="plugin-sync", severity="low", kind="maintenance",
            title=iid, detail="d", to_outbox=True,
        )
        if i == 0:
            first_done.set()


def _one_trial(work: Path, trial: int) -> tuple[set[str], set[str], set[str]]:
    """Run ONE real concurrency trial. Returns
    ``(expected_ids, union_lines_before_implicit, union_after)`` — really
    ``(expected_ids, pre_outbox_snapshot, post_union_lines)`` for evidence.

    A fresh worktree per trial (origin never advances → nothing is ever GC'd, so
    every expected id must live on the branch OR still in the outbox)."""
    random.seed(_BASE_SEED + trial)  # reproducible interleave schedule (openai-M7)
    wt = h.make_worktree(work, f"d2v-conc-{trial}")

    pre_ids = [f"trg-pre{trial:03d}{i:02d}" for i in range(_PRE)]
    for iid in pre_ids:
        triage.append_triage_item(
            work, source="plugin-sync", severity="low", kind="maintenance",
            title=iid, detail="d", to_outbox=True,
        )
    pre_snapshot = h.outbox_lines(work)

    # More concurrent appends than the single-shot case so the producer is
    # demonstrably still appending while the sweep holds the lock (real overlap).
    conc_ids = [f"trg-cnc{trial:03d}{i:02d}" for i in range(_CONC)]
    first_done = threading.Event()
    jitter = random.choice((0.0005, 0.001, 0.002))  # always non-zero → spans sweep
    producer = threading.Thread(target=_producer, args=(work, conc_ids, first_done, jitter))
    producer.start()
    # Start the sweep ONLY after the producer's first append landed → guaranteed
    # at least one concurrent append is already committed-to-outbox and more are
    # still arriving (the remaining ids sleep-jitter into the sweep's lock window).
    assert first_done.wait(timeout=5.0), f"trial {trial}: producer never started"

    result = sweep_outbox_to_branch(work, wt, default_branch="main")
    producer.join(timeout=15.0)
    assert not producer.is_alive(), f"trial {trial}: producer hung"
    assert result.status in ("committed", "no_change"), (trial, result.to_dict())

    # Per-file PHYSICAL duplicate check over RAW (un-deduped) lines (external-review:
    # a set-union of branch ∪ outbox would collapse a legitimate cross-file copy
    # AND mask an in-file dup; so assert NO title repeats within EITHER file before
    # the union compare).
    ev.assert_no_physical_dup(ev.branch_raw_lines(wt), f"trial {trial} branch")
    ev.assert_no_physical_dup(ev.outbox_raw_lines(work), f"trial {trial} outbox")
    branch_lines, outbox_remaining = ev.union_appends_present(work, wt)
    union = branch_lines | outbox_remaining
    expected = set(pre_ids + conc_ids)
    return expected, pre_snapshot, union


def _run_stress(work: Path, trials: int) -> tuple[int, set[str], set[str]]:
    """Run ``trials`` real trials, asserting zero-loss + zero-dup on EACH. Returns
    ``(trials, sample_before, sample_after)`` from a representative middle trial
    for the evidence artifact.

    Seed a tracked triage log (header + a seed item) on ``main`` ONCE up front so
    every per-trial worktree branches from a repo that carries the schema header —
    otherwise the header-less outbox materializes a header-less branch log and the
    sweep's ``validate_triage_text`` rejects it (the seed mirrors a real adopted
    repo, where ``.shipwright/triage.jsonl`` always has the header)."""
    h.seed_tracked(work, h.item("trg-seed"))
    sample_before: set[str] = set()
    sample_after: set[str] = set()
    for trial in range(trials):
        expected, pre_snapshot, union = _one_trial(work, trial)

        # ZERO LOSS: every expected id is present in the union (branch ∪ outbox).
        for iid in expected:
            assert ev.title_present(union, iid), (
                f"trial {trial}: id {iid} LOST — absent from branch ∪ outbox.\n"
                f"union={sorted(union)}"
            )
        # ZERO DUPLICATION (MULTISET — external-review openai-H1): a plain set
        # compare can hide a swap (one lost + one dup nets the same size). Assert
        # the MULTISET. The branch log and the outbox are physically distinct
        # files; a just-swept line legitimately lives in BOTH pre-GC, so we first
        # collapse PHYSICALLY-identical lines across the two files (set union),
        # then count append-ids: each EXPECTED id's logical multiplicity MUST be
        # exactly 1. >1 means a genuine duplicate of distinct physical lines (two
        # differently-serialized copies of the same id) survived — a real dup.
        logical = ev.count_titles(union)
        offenders = {tag: logical.get(tag, 0) for tag in expected if logical.get(tag, 0) != 1}
        assert not offenders, (
            f"trial {trial}: logical multiplicity != 1 (loss or dup): {offenders}"
        )
        # And the BRANCH file itself carries no PHYSICAL duplicate append line.
        branch_appends = [ln for ln in h.branch_triage_lines(work / ".worktrees" / f"d2v-conc-{trial}")
                          if '"event":"append"' in ln]
        assert len(branch_appends) == len(set(branch_appends)), (
            f"trial {trial}: duplicate append line on branch:\n{sorted(branch_appends)}"
        )
        if trial == trials // 2:
            sample_before = pre_snapshot
            sample_after = union
    return trials, sample_before, sample_after


def _sample(lines: set[str], n: int = 6) -> list[str]:
    return sorted(lines)[:n]


@pytest.mark.slow
def test_concurrency_stress_200_trials(repo, _evidence) -> None:
    """METHOD 1 (GATE): >=200 REAL concurrency trials, zero loss / zero dup by
    full line-SET comparison, FileLock not mocked. Records the evidence artifact."""
    work = repo
    passed = True
    detail = ""
    trials = sample_before = sample_after = None
    try:
        trials, sb, sa = _run_stress(work, _STRESS_TRIALS)
        sample_before, sample_after = _sample(sb), _sample(sa)
        detail = (
            f"{trials} real THREAD-concurrent trials (spec's >=200; thread permitted) "
            f"with guaranteed overlap (producer signals after append-1, keeps "
            f"appending while the sweep holds the lock), deterministic seed "
            f"base={_BASE_SEED}; zero loss, no in-file physical dup (raw per-file "
            f"check), MULTISET count==1 per title over branch ∪ outbox each trial. "
            f"Cross-PROCESS contention proved ADDITIONALLY by METHOD 1b."
        )
    except AssertionError as exc:
        passed = False
        detail = f"FAILED: {exc}"
        raise
    finally:
        _evidence.record(ev.MethodResult(
            name="METHOD 1 — concurrency stress (real FileLock contention)",
            passed=passed,
            iterations=trials or 0,
            detail=detail,
            sample_before=sample_before or [],
            sample_after=sample_after or [],
        ))


def test_concurrency_smoke(repo) -> None:
    """FAST harness smoke (12 trials, default suite) — catches a regression in the
    stress harness itself without the multi-minute heavy load. Does NOT satisfy
    the gate (the >=200 count is recorded only by the slow test)."""
    work = repo
    trials, _sb, _sa = _run_stress(work, _SMOKE_TRIALS)
    assert trials == _SMOKE_TRIALS


_PRODUCER = str(Path(__file__).resolve().parent / "_d2v_outbox_producer.py")
#: Cross-PROCESS trials (real subprocess spawn is ~100x slower than a thread, so
#: fewer trials — the THREAD proof carries the >=200 count; this proves the lock
#: is contended at the OS level too, not merely cross-thread under one GIL).
_SUBPROC_TRIALS = 40


def _subproc_one_trial(work: Path, trial: int) -> None:
    """ONE cross-process trial: a REAL separate ``python`` process appends to the
    outbox (canonical OS-level _FileLock) WHILE the parent runs the real sweep."""
    random.seed(_BASE_SEED + 9000 + trial)
    wt = h.make_worktree(work, f"d2v-sub-{trial}")
    pre_ids = [f"trg-spr{trial:03d}{i:02d}" for i in range(_PRE)]
    for iid in pre_ids:
        triage.append_triage_item(
            work, source="plugin-sync", severity="low", kind="maintenance",
            title=iid, detail="d", to_outbox=True,
        )
    conc_ids = [f"trg-scn{trial:03d}{i:02d}" for i in range(_CONC)]
    proc = subprocess.Popen(
        [sys.executable, _PRODUCER, str(work), *conc_ids],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if random.random() < 0.5:
        time.sleep(random.uniform(0.0, 0.002))
    result = sweep_outbox_to_branch(work, wt, default_branch="main")
    _out, err = proc.communicate(timeout=30)
    assert proc.returncode == 0, f"trial {trial}: producer process failed: {err!r}"
    assert result.status in ("committed", "no_change"), (trial, result.to_dict())

    ev.assert_no_physical_dup(ev.branch_raw_lines(wt), f"sub-trial {trial} branch")
    ev.assert_no_physical_dup(ev.outbox_raw_lines(work), f"sub-trial {trial} outbox")
    branch_lines, outbox_remaining = ev.union_appends_present(work, wt)
    union = branch_lines | outbox_remaining
    expected = set(pre_ids + conc_ids)
    for iid in expected:
        assert ev.title_present(union, iid), (
            f"trial {trial}: id {iid} LOST cross-process — absent from branch ∪ outbox"
        )
    logical = ev.count_titles(union)
    offenders = {tag: logical.get(tag, 0) for tag in expected if logical.get(tag, 0) != 1}
    assert not offenders, f"trial {trial}: cross-process multiplicity != 1: {offenders}"


@pytest.mark.slow
def test_subprocess_concurrency_stress(repo, _evidence) -> None:
    """METHOD 1b (GATE): REAL cross-PROCESS contention (separate OS process appends
    to the outbox via the canonical OS-level _FileLock while the sweep runs).
    Proves the lock is contended across processes, not just threads under one GIL
    (external-review openai-H2 / gemini). Multiset zero-loss/zero-dup each trial."""
    work = repo
    h.seed_tracked(work, h.item("trg-seed"))
    passed = True
    detail = ""
    n = 0
    try:
        for trial in range(_SUBPROC_TRIALS):
            _subproc_one_trial(work, trial)
            n = trial + 1
        detail = (
            f"{n} real CROSS-PROCESS trials (separate python process appends via the "
            f"canonical OS-level _FileLock while the sweep runs); zero loss, "
            f"multiset count==1 per id over branch ∪ outbox each trial."
        )
    except AssertionError as exc:
        passed = False
        detail = f"FAILED: {exc}"
        raise
    finally:
        _evidence.record(ev.MethodResult(
            name="METHOD 1b — cross-process concurrency stress (OS-level FileLock)",
            passed=passed, iterations=n, detail=detail,
        ))
