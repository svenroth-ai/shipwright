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
_OUTPUT_LOCK = threading.Lock()


class SuiteCancelled(RuntimeError):
    """Admission stopped because the parent suite is cancelling."""


class Budget:
    """Outer pool and inner xdist workers draw from one granted budget."""

    def __init__(self, total: int) -> None:
        self.total = max(1, total)
        self._used = 0
        self._cond = threading.Condition()

    def acquire(self, weight: int,
                cancel_event: threading.Event | None = None) -> int:
        weight = max(1, min(weight, self.total))
        with self._cond:
            while self._used + weight > self.total:
                if cancel_event is not None and cancel_event.is_set():
                    raise SuiteCancelled("suite cancellation stopped budget admission")
                self._cond.wait(timeout=.1)
            if cancel_event is not None and cancel_event.is_set():
                raise SuiteCancelled("suite cancellation stopped budget admission")
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
        with _OUTPUT_LOCK:
            print(line[:1000], file=stream, flush=True)
    except (OSError, ValueError):
        pass


def emit_unit_event(stream: TextIO | None, *, run_id: str | None, event: str,
                    unit_id: str, weight: int, outcome: str = "-",
                    seconds: float = 0.0, phase: str = "initial",
                    retry_kind: str = "-") -> None:
    """Emit one locked, ASCII-safe, length-capped lifecycle record."""
    output = stream if stream is not None else sys.stderr
    _emit_heartbeat(
        output,
        f"F0 suite unit: run_id={_ascii_field(run_id)} event={_ascii_field(event)} "
        f"unit={_ascii_field(unit_id)} weight={max(1, int(weight))} "
        f"outcome={_ascii_field(outcome)} elapsed={max(0.0, seconds):.1f}s "
        f"phase={_ascii_field(phase)} retry_kind={_ascii_field(retry_kind)}",
    )


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
    cancel_event: threading.Event | None = None,
) -> list[Result]:
    """Collect results in input order while keeping the parent channel visible."""
    output = stream if stream is not None else sys.stderr
    interval = max(0.01, heartbeat_seconds)
    results: list[Result | None] = [None] * len(items)
    started = time.monotonic()
    pool = cf.ThreadPoolExecutor(max_workers=max(1, len(items)))
    pending: dict[cf.Future, int] = {}
    try:
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
    except BaseException:
        if cancel_event is not None:
            cancel_event.set()
        for future in pending:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    return [result for result in results if result is not None]
