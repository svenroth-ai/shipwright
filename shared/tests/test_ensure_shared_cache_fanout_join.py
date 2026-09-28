"""Focused contracts for the dynamic SessionStart fan-out join barrier."""

from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "shared" / "templates" / "hooks"))
lock_helper = importlib.import_module("cache_repair_lock")


def test_completion_observation_can_be_queried_safely(tmp_path: Path):
    done = tmp_path / "generation.done"

    assert lock_helper.has_completion_observation(done, "participant") is False
    assert lock_helper.observe_completion(done, "participant") is True
    assert lock_helper.has_completion_observation(done, "participant") is True
    # An immutable observation marker is valid only while it stays zero bytes.
    marker = next(tmp_path.glob("observed-*.seen"))
    marker.write_bytes(b"\n")
    assert lock_helper.has_completion_observation(done, "participant") is False


def test_detected_fanout_waits_for_all_installed_hook_participants(
    tmp_path: Path, monkeypatch,
):
    cache = tmp_path / "plugins" / "cache" / "shipwright"
    participants = tuple(
        f"shipwright-{slug}:sessionstart" for slug in ("a", "b", "c")
    )
    installed: dict[str, list[dict[str, str]]] = {}
    for participant in participants:
        plugin = participant.split(":", 1)[0]
        version = cache / plugin / "1.0.0"
        hooks = version / "hooks"
        hooks.mkdir(parents=True)
        hooks.joinpath("hooks.json").write_text(
            '{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":'
            '"run_if_cache_ready.py"}]}]}}',
            encoding="utf-8",
        )
        installed[f"{plugin}@shipwright"] = [{"installPath": str(version)}]
    for plugin, hook_type, command in (
        ("shipwright-substring", "command", "not_run_if_cache_ready.py"),
        ("shipwright-noncommand", "prompt", "run_if_cache_ready.py"),
    ):
        version = cache / plugin / "1.0.0"
        hooks = version / "hooks"
        hooks.mkdir(parents=True)
        hooks.joinpath("hooks.json").write_text(json.dumps({
            "hooks": {"SessionStart": [{"hooks": [{
                "type": hook_type, "command": command,
            }]}]},
        }), encoding="utf-8")
        installed[f"{plugin}@shipwright"] = [{"installPath": str(version)}]
    stale = cache / "shipwright-stale" / "9.9.9"
    stale.joinpath("hooks").mkdir(parents=True)
    stale.joinpath("hooks", "hooks.json").write_text(
        '{"hooks":{"SessionStart":[{"hooks":[{"command":'
        '"run_if_cache_ready.py"}]}]}}',
        encoding="utf-8",
    )
    manifest = cache.parent.parent / "installed_plugins.json"
    manifest.write_text(
        json.dumps({"plugins": installed}), encoding="utf-8",
    )
    done = cache / ".sessionstart-claims" / "generation.done"
    done.parent.mkdir()
    assert lock_helper.observe_completion(done, participants[0]) is True
    # This test asserts JOIN semantics (the barrier returns only once every peer
    # has observed), not timing, so every wall-clock exit is pushed out of reach:
    # a joiner thread starved past a sub-second ceiling must not fail the test.
    # The barrier returns the instant all peers are present, so the large values
    # cost nothing on success. _FANOUT_PROBE_SECONDS is not patched: it bounds
    # only the un-enumerable early return, and the peer set IS enumerable here
    # (asserted below).
    for ceiling in (
        "_FANOUT_WAIT_SECONDS",
        "_FANOUT_ARRIVAL_GRACE_SECONDS",
        "_FANOUT_IDLE_SECONDS",
    ):
        monkeypatch.setattr(lock_helper, ceiling, 60.0)
    assert lock_helper._installed_fanout_participants(
        cache, participants[0],
    ) == participants

    # Order the peers' arrival on the barrier itself, not on a sleep: the joiner
    # writes its markers only once the barrier has started a SECOND pass over
    # the peers. Pass one therefore sees them absent for certain, and a barrier
    # that returned after a single pass (or without waiting) always finds them
    # absent. A correct barrier always reaches pass two, since nobody has joined.
    polling = threading.Event()
    real_observation = lock_helper.has_completion_observation
    calls = 0

    def observed_by_barrier(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > len(participants):
            polling.set()
        return real_observation(*args, **kwargs)

    monkeypatch.setattr(
        lock_helper, "has_completion_observation", observed_by_barrier,
    )
    errors: list[Exception] = []

    def join_fanout() -> None:
        try:
            # Bounded only so a barrier that never re-polls cannot hang the test.
            # On expiry write NOTHING: markers that appear late must never be
            # able to satisfy the post-return check on a barrier that did not wait.
            if not polling.wait(timeout=30):
                raise AssertionError("barrier never began a second pass")
            for participant in participants[1:]:
                if lock_helper.observe_completion(done, participant) is not True:
                    raise AssertionError(f"observation failed for {participant}")
        except Exception as exc:
            errors.append(exc)

    joiner = threading.Thread(target=join_fanout, daemon=True)
    joiner.start()
    started = time.monotonic()
    lock_helper.await_fanout_observers(cache, done, participants[0])
    elapsed = time.monotonic() - started
    monkeypatch.setattr(
        lock_helper, "has_completion_observation", real_observation,
    )
    # Check the markers as the barrier returns: the contract is about the
    # markers, and a thread-side flag would lag the marker the barrier polls.
    # Every marker must read True. A marker that reads False is definitively
    # absent (an early return) and fails at once. One that reads None is
    # unreadable (a transient Windows sharing violation, which the barrier itself
    # treats as "cannot tell yet") and is re-read for a bounded time, since the
    # barrier had already read it as True.
    settle_deadline = time.monotonic() + 10
    while True:
        states = {
            participant: lock_helper.has_completion_observation(done, participant)
            for participant in participants
        }
        if all(state is True for state in states.values()):
            break
        if (
            any(state is False for state in states.values())
            or time.monotonic() >= settle_deadline
        ):
            break
        time.sleep(0.01)
    missing = [p for p, state in states.items() if state is not True]
    assert not missing, (
        f"barrier returned before every active peer joined: {missing}"
    )
    # Half the ceiling: no host load reaches it, yet a barrier that sat out the
    # ceiling instead of returning once everyone joined is caught.
    assert elapsed < 30, f"barrier held for {elapsed:.1f}s after all peers joined"
    # Generous: this only reaps the thread, it must not be able to fail the test.
    joiner.join(timeout=30)

    assert not errors
    assert not joiner.is_alive()


@pytest.mark.parametrize("payload", [None, [], 42, "plugins"])
def test_non_object_install_manifest_uses_bounded_fallback(
    tmp_path: Path, monkeypatch, payload: object,
):
    cache = tmp_path / "plugins" / "cache" / "shipwright"
    cache.mkdir(parents=True)
    manifest = cache.parent.parent / "installed_plugins.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    sleeps: list[float] = []
    monkeypatch.setattr(lock_helper.time, "sleep", sleeps.append)

    lock_helper.await_fanout_observers(
        cache, cache / "generation.done", "shipwright-run:sessionstart",
    )

    assert sleeps == [lock_helper._FANOUT_PROBE_SECONDS]
