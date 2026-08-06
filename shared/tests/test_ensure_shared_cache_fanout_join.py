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
    # Only the ceiling is patched. _FANOUT_PROBE_SECONDS no longer bounds the
    # wait loop — it survives solely for the un-enumerable early return, and
    # this test asserts just below that the peer set IS enumerable, so patching
    # it here would describe a mechanism that no longer exists.
    monkeypatch.setattr(lock_helper, "_FANOUT_WAIT_SECONDS", 0.5)
    assert lock_helper._installed_fanout_participants(
        cache, participants[0],
    ) == participants
    joined = threading.Event()
    errors: list[Exception] = []

    def join_fanout() -> None:
        try:
            time.sleep(0.02)
            for participant in participants[1:]:
                if lock_helper.observe_completion(done, participant) is not True:
                    raise AssertionError(f"observation failed for {participant}")
            joined.set()
        except Exception as exc:
            errors.append(exc)

    joiner = threading.Thread(target=join_fanout)
    joiner.start()
    lock_helper.await_fanout_observers(cache, done, participants[0])
    assert joined.is_set(), "barrier returned before every active peer joined"
    joiner.join(timeout=1)

    assert not errors
    assert not joiner.is_alive()
    assert all(
        lock_helper.has_completion_observation(done, participant) is True
        for participant in participants
    )


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
