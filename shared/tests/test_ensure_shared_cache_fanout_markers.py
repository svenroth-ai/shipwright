"""Observation-marker validity inside the fan-out barrier.

An observation marker is evidence only while it stays a readable, zero-byte
regular file. Two ways that evidence can move under the barrier's feet: a
transient OSError makes it unreadable for one pass, and a write makes it
permanently invalid. Both used to end the wait early and republish the
defect this area was repaired for.

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
    lock_helper,
)


def test_one_unreadable_marker_does_not_abandon_the_barrier(
    tmp_path: Path, monkeypatch,
):
    """A transient OSError is "cannot tell yet", not "no fan-out".

    The barrier used to `return` outright when `has_completion_observation`
    answered None, which is any OSError other than FileNotFoundError. On
    Windows one virus-scanner or indexer touch of a just-created zero-byte
    marker was therefore enough to publish the generation with 1/12 observed
    and send eleven peers into their own re-election — the exact defect this
    change fixes, reached by a one-in-a-hundred filesystem hiccup.
    """
    cache, done, peers = _fanout_layout(tmp_path, ("a", "b", "c"))
    for peer in peers:
        lock_helper.observe_completion(done, peer)
    real = lock_helper.has_completion_observation
    calls = {"n": 0}

    def flaky(done_path, observer):
        calls["n"] += 1
        if calls["n"] == 2:          # one transient failure, then healthy
            return None
        return real(done_path, observer)

    monkeypatch.setattr(lock_helper, "has_completion_observation", flaky)
    clock = _VirtualClock([], done)
    monkeypatch.setattr(lock_helper, "time", clock)

    lock_helper.await_fanout_observers(cache, done, peers[0])

    assert calls["n"] > len(peers), (
        "the barrier gave up on the first unreadable marker instead of "
        "re-reading it on the next pass"
    )
    assert clock.now < lock_helper._FANOUT_ARRIVAL_GRACE_SECONDS, (
        "once every marker reads, the all-present fast path must still fire"
    )


def test_an_observation_that_stops_validating_stops_counting(
    tmp_path: Path, monkeypatch,
):
    """Completion membership is rebuilt each pass, never accumulated.

    An observation marker is valid only while it stays zero bytes
    (``test_completion_observation_can_be_queried_safely``). The invalidation
    must happen MID-WAIT, after the peer has already validated on an earlier
    pass — invalidating before entry proves nothing, because an implementation
    that accumulated `present` would never have added the peer either.

    It also needs a FOURTH peer arriving after the tamper. With three, `c`'s
    arrival completes the set on the very pass it validates, the barrier
    returns, and there is no later pass for the tamper to affect. Here `d`
    lands at 0.8s, after `c` has been invalidated at 0.6s:

      correct     -> `present` is rebuilt, so at 0.8s it is {a, b, d} and the
                     set is never complete; the barrier runs to the idle
                     deadline at 0.8 + _IDLE
      accumulated -> `c` is remembered, so 0.8s reads as all four present and
                     the barrier returns immediately, publishing a generation
                     one of whose observations no longer validates
    """
    cache, done, peers = _fanout_layout(tmp_path, ("a", "b", "c", "d"))
    lock_helper.observe_completion(done, peers[0])
    clock = _VirtualClock(
        [(0.2, peers[1]), (0.4, peers[2]), (0.8, peers[3])], done,
        tamper=[(0.6, peers[2])],
    )
    monkeypatch.setattr(lock_helper, "time", clock)

    lock_helper.await_fanout_observers(cache, done, peers[0])

    assert lock_helper.has_completion_observation(done, peers[2]) is False
    assert clock.now == pytest.approx(
        0.8 + lock_helper._FANOUT_IDLE_SECONDS, abs=0.05,
    ), "a peer whose marker stopped validating must not count as present"
