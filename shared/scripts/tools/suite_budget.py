"""In-process weighted budget and observable parallel result collection for F0."""

from __future__ import annotations

import concurrent.futures as cf
import sys
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import TextIO, TypeVar

Item = TypeVar("Item")
Result = TypeVar("Result")


class Budget:
    """Outer pool and inner xdist workers draw from one granted budget."""

    def __init__(self, total: int) -> None:
        self.total = max(1, total)
        self._used = 0
        self._cond = threading.Condition()

    def acquire(self, weight: int) -> int:
        weight = max(1, min(weight, self.total))
        with self._cond:
            while self._used + weight > self.total:
                self._cond.wait()
            self._used += weight
        return weight

    def release(self, weight: int) -> None:
        with self._cond:
            self._used -= weight
            self._cond.notify_all()


def _ascii_field(value: object) -> str:
    text = " ".join(str(value or "-").split())[:200]
    return text.encode("ascii", "backslashreplace").decode("ascii")


def _emit_heartbeat(stream: TextIO, line: str) -> None:
    try:
        print(line, file=stream, flush=True)
    except (OSError, ValueError):
        pass


@contextmanager
def heartbeat_while(*, heartbeat_seconds: float, run_id: str | None,
                    completed: int, total: int, initial_completed: int,
                    phase: str, unit_id: str,
                    stream: TextIO | None):
    """Keep a parent-process heartbeat alive around one blocking suite action."""
    output = stream if stream is not None else sys.stderr
    interval = max(0.01, heartbeat_seconds)
    stopped = threading.Event()
    started = time.monotonic()

    def _report() -> None:
        while not stopped.wait(interval):
            _emit_heartbeat(
                output,
                f"F0 suite heartbeat: run_id={_ascii_field(run_id)} "
                f"completed={completed}/{total} "
                f"initial_completed={initial_completed}/{total} "
                f"elapsed={time.monotonic() - started:.1f}s "
                f"phase={_ascii_field(phase)} unit={_ascii_field(unit_id)}",
            )

    reporter = threading.Thread(target=_report, name="f0-heartbeat", daemon=True)
    reporter.start()
    try:
        yield
    finally:
        stopped.set()
        reporter.join(timeout=interval + 1.0)


def run_parallel(
    items: list[Item],
    one: Callable[[tuple[int, Item]], Result],
    *,
    heartbeat_seconds: float,
    run_id: str | None,
    stream: TextIO | None,
) -> list[Result]:
    """Collect results in input order while keeping the parent channel visible."""
    output = stream if stream is not None else sys.stderr
    interval = max(0.01, heartbeat_seconds)
    results: list[Result | None] = [None] * len(items)
    started = time.monotonic()
    with cf.ThreadPoolExecutor(max_workers=max(1, len(items))) as pool:
        pending = {
            pool.submit(one, indexed): indexed[0]
            for indexed in enumerate(items)
        }
        next_heartbeat = started + interval
        while pending:
            timeout = max(0.0, next_heartbeat - time.monotonic())
            done, _ = cf.wait(pending, timeout=timeout, return_when=cf.FIRST_COMPLETED)
            for future in done:
                results[pending.pop(future)] = future.result()
            now = time.monotonic()
            if pending and now >= next_heartbeat:
                complete = len(items) - len(pending)
                _emit_heartbeat(
                    output,
                    f"F0 suite heartbeat: run_id={_ascii_field(run_id)} "
                    f"completed={complete}/{len(items)} elapsed={now - started:.1f}s",
                )
                next_heartbeat = now + interval
    return [result for result in results if result is not None]
