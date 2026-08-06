"""Shared helpers for the SessionStart fan-out barrier tests.

Sibling-fixture module, following ``ensure_shared_cache_fixtures``: two test
modules use these (``…_fanout_timing`` for the arrival policy,
``…_fanout_markers`` for observation-marker validity) and neither owns them.

The clock is the point. ``await_fanout_observers`` is a wall-clock state
machine, and asserting a wall-clock state machine against the real clock is how
you write the flaky tests this whole area is being repaired for. So the module
under test gets a virtual ``time`` whose ``sleep`` advances simulated time and
materialises whichever peers were scheduled to arrive by then — nothing sleeps
for real, and every assertion is about the policy rather than the host.
"""

from __future__ import annotations

import importlib
import json
import sys
import time as _real_time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared" / "templates" / "hooks"))

lock_helper = importlib.import_module("cache_repair_lock")
# The ceiling is coupled to its neighbours' patience. Import the real constants
# rather than duplicating the literals, or lowering one silently breaks it.
ready_guard = importlib.import_module("run_if_cache_ready")
healer = importlib.import_module("ensure_shared_cache")


class VirtualClock:
    """Deterministic stand-in for the module's `time`, driving peer arrivals.

    ``schedule`` entries are ``(at_seconds, peer)`` arrivals; ``tamper`` entries
    are ``(at_seconds, peer)`` invalidations, which write a byte into an
    already-created marker so it stops validating mid-wait.
    """

    def __init__(self, schedule: list[tuple[float, str]], done: Path,
                 tamper: list[tuple[float, str]] | None = None) -> None:
        self.now = 0.0
        self.slept: list[float] = []
        self._pending = sorted(schedule)
        self._tamper = sorted(tamper or [])
        self._done = done

    # Anything the module reaches for that this clock does not model must fall
    # through to the real `time`, or a future helper turns every monkeypatched
    # test into an AttributeError on the harness instead of a real failure.
    def __getattr__(self, name: str):
        return getattr(_real_time, name)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.slept.append(seconds)
        while self._pending and self._pending[0][0] <= self.now:
            lock_helper.observe_completion(self._done, self._pending.pop(0)[1])
        while self._tamper and self._tamper[0][0] <= self.now:
            marker = lock_helper._completion_observer_marker(
                self._done, self._tamper.pop(0)[1],
            )
            marker.write_bytes(b"\n")


def fanout_layout(
    tmp_path: Path, slugs: tuple[str, ...],
) -> tuple[Path, Path, tuple[str, ...]]:
    """Minimal installed-plugin manifest whose peers all register SessionStart."""
    cache = tmp_path / "plugins" / "cache" / "shipwright"
    installed: dict[str, list[dict[str, str]]] = {}
    for slug in slugs:
        version = cache / f"shipwright-{slug}" / "1.0.0"
        (version / "hooks").mkdir(parents=True)
        (version / "hooks" / "hooks.json").write_text(
            '{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":'
            '"run_if_cache_ready.py"}]}]}}', encoding="utf-8",
        )
        installed[f"shipwright-{slug}@shipwright"] = [{"installPath": str(version)}]
    (cache.parent.parent / "installed_plugins.json").write_text(
        json.dumps({"plugins": installed}), encoding="utf-8",
    )
    done = cache / ".sessionstart-claims" / "generation.done"
    done.parent.mkdir()
    return cache, done, tuple(f"shipwright-{slug}:sessionstart" for slug in slugs)
