"""Arrival-timing contracts for the SessionStart fan-out barrier.

These are the contracts that #543's fixed 0.1s existence-probe missed: it
read "nobody here within a tenth of a second" as "there is no fan-out to
wait for", so on a loaded host the owner published its completion before
eleven peers had even spawned, and each straggler re-elected itself and
repeated the whole cache scan
(iterate-2026-08-06-parallel-global-state-tests).

Split from one another at the 300-LOC ceiling; the virtual clock and the
manifest builder both live in the sibling ``fanout_barrier_fixtures`` module.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling fanout_barrier_fixtures module

from fanout_barrier_fixtures import (  # noqa: E402
    VirtualClock as _VirtualClock,
    fanout_layout as _fanout_layout,
    healer,
    lock_helper,
    ready_guard,
)


def test_a_fanout_arriving_after_the_probe_window_is_still_awaited(
    tmp_path: Path, monkeypatch,
):
    """AC-4 — the pinned root cause.

    Under host CPU saturation the first peer needs ~0.2-0.4s merely to spawn.
    The owner must not conclude "no fan-out is running" just because nobody has
    arrived within a tenth of a second: it published `.done` at 0.106s with
    1/12 observed, and the eleven stragglers each re-elected themselves and
    repeated the whole cache scan.
    """
    cache, done, peers = _fanout_layout(tmp_path, ("a", "b", "c", "d"))
    assert lock_helper.observe_completion(done, peers[0]) is True  # the owner
    clock = _VirtualClock(
        [(0.5, peers[1]), (0.8, peers[2]), (1.1, peers[3])], done,
    )
    monkeypatch.setattr(lock_helper, "time", clock)

    lock_helper.await_fanout_observers(cache, done, peers[0])

    unobserved = [
        peer for peer in peers
        if lock_helper.has_completion_observation(done, peer) is not True
    ]
    assert not unobserved, (
        f"barrier published before {unobserved} joined — each becomes a second "
        "owner and repeats the entire cache scan"
    )


def test_a_fanout_that_never_arrives_is_abandoned_at_the_arrival_grace(
    tmp_path: Path, monkeypatch,
):
    """AC-3 — a configured-but-absent fan-out must not cost the full ceiling."""
    cache, done, peers = _fanout_layout(tmp_path, ("a", "b", "c"))
    lock_helper.observe_completion(done, peers[0])
    clock = _VirtualClock([], done)
    monkeypatch.setattr(lock_helper, "time", clock)

    lock_helper.await_fanout_observers(cache, done, peers[0])

    assert clock.now == pytest.approx(
        lock_helper._FANOUT_ARRIVAL_GRACE_SECONDS, abs=0.05,
    )
    assert clock.now < lock_helper._FANOUT_WAIT_SECONDS


def test_all_peers_present_returns_without_consuming_the_grace(
    tmp_path: Path, monkeypatch,
):
    """AC-2 — the fast path is preserved: no waiting once everyone is in."""
    cache, done, peers = _fanout_layout(tmp_path, ("a", "b", "c"))
    for peer in peers:
        lock_helper.observe_completion(done, peer)
    clock = _VirtualClock([], done)
    monkeypatch.setattr(lock_helper, "time", clock)

    lock_helper.await_fanout_observers(cache, done, peers[0])

    assert clock.slept == []


def test_continuous_arrivals_cannot_push_the_ceiling_past_entry_plus_wait(
    tmp_path: Path, monkeypatch,
):
    """AC-5 — the hard ceiling is anchored at entry and never reset.

    Progress extends the idle deadline; it must not extend the ceiling, or a
    steady trickle of arrivals would hold SessionStart open indefinitely.
    """
    cache, done, peers = _fanout_layout(
        tmp_path, tuple(f"p{n}" for n in range(40)),
    )
    lock_helper.observe_completion(done, peers[0])
    # One arrival every 0.2s for far longer than the ceiling allows.
    clock = _VirtualClock(
        [(0.2 * n, peers[n]) for n in range(1, len(peers))], done,
    )
    monkeypatch.setattr(lock_helper, "time", clock)

    lock_helper.await_fanout_observers(cache, done, peers[0])

    # EXACTLY the ceiling, not "within a poll interval of it". A flat poll
    # would step past the deadline and return on the next pass, so a tolerance
    # here would have accepted the barrier overshooting the bound it
    # advertises — the test tolerating the defect instead of catching it.
    assert clock.now == pytest.approx(lock_helper._FANOUT_WAIT_SECONDS, abs=1e-9)
    # The BINDING neighbour. A peer queued in _claim_session gives up after
    # _CLAIM_WAIT_SECONDS and enters the recovering-owner path — which costs a
    # stall and lock contention, NOT a duplicate scan (it finds the repair
    # state already True and returns without scanning). Import both constants
    # rather than repeating the literals, or lowering either silently breaks
    # the coupling.
    assert lock_helper._FANOUT_WAIT_SECONDS < healer._CLAIM_WAIT_SECONDS, (
        "the barrier must not outlast a queued peer's claim wait"
    )
    assert lock_helper._FANOUT_WAIT_SECONDS < ready_guard._READY_WAIT_SECONDS, (
        "secondary: the ceiling must also stay under the guard's ready-wait"
    )


def test_only_a_new_expected_peer_counts_as_progress(
    tmp_path: Path, monkeypatch,
):
    """AC-5b — duplicates and outsiders must not extend the idle deadline."""
    cache, done, peers = _fanout_layout(tmp_path, ("a", "b", "c"))
    lock_helper.observe_completion(done, peers[0])
    # An identity outside `peers`, re-marked repeatedly, is not progress.
    clock = _VirtualClock(
        [(0.2 * n, "shipwright-outsider:sessionstart") for n in range(1, 40)],
        done,
    )
    monkeypatch.setattr(lock_helper, "time", clock)

    lock_helper.await_fanout_observers(cache, done, peers[0])

    assert clock.now == pytest.approx(
        lock_helper._FANOUT_ARRIVAL_GRACE_SECONDS, abs=0.05,
    ), "an unexpected identity must not keep the barrier open"


def test_a_repeated_observation_by_an_expected_peer_is_not_progress(
    tmp_path: Path, monkeypatch,
):
    """AC-5b, second case — a duplicate must not extend the idle deadline.

    The re-observing peer must be a NON-OWNER expected peer, and it must arrive
    once before repeating. Re-observing the participant itself would prove
    nothing: the caller is subtracted out of the arrival count anyway, so that
    version of the test passes even against an implementation whose duplicate
    handling is broken. Here `b` genuinely arrives (0.3s) and then re-observes
    forever while `c` never comes:

      correct  -> one arrival, so the barrier goes idle at 0.3 + _IDLE
      broken   -> each repeat reads as progress and it rides to the ceiling
    """
    cache, done, peers = _fanout_layout(tmp_path, ("a", "b", "c"))
    lock_helper.observe_completion(done, peers[0])
    clock = _VirtualClock(
        [(0.3, peers[1])] + [(0.3 + 0.2 * n, peers[1]) for n in range(1, 40)],
        done,
    )
    monkeypatch.setattr(lock_helper, "time", clock)

    lock_helper.await_fanout_observers(cache, done, peers[0])

    assert clock.now == pytest.approx(
        0.3 + lock_helper._FANOUT_IDLE_SECONDS, abs=0.05,
    ), "re-observing an already-counted peer must not keep the barrier open"
    assert clock.now < lock_helper._FANOUT_WAIT_SECONDS, (
        "a duplicate-driven wait would have run to the hard ceiling"
    )
