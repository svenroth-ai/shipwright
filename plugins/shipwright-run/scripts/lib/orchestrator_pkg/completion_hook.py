"""The one ``on_complete`` hook ``single-session-apply`` hands to ``complete_phase_task``.

Everything apply writes besides the completion itself goes through this hook, so it lands
in the SAME locked read-modify-write as the completion, after the lifecycle's owner +
version check: a stale apply (its task re-dispatched or recovered, even while its gate was
running) is refused there and writes none of it. In order:

1. the override record (``phase_gate.override_hook``) — first, because it may refuse on
   the locked config (``OverrideRefused``), and then nothing at all is written;
2. the design freeze (``splits_frozen`` + ``runConditions.splitMode``) — before the
   lifecycle plans the successor, so plan/build fan out per split;
3. the durable ``phase_tasks[].gate`` record of a gated completion.

No ``try``: an exception must reach ``complete_phase_task`` unchanged (it maps the
override's refusal by its type name). The hook does no I/O and calls no lifecycle function
(the lock is not re-entrant for read-modify-write).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from . import phase_gate

Hook = Callable[[dict[str, Any], dict[str, Any]], None]


def completion_hook(
    *, override: Optional[Hook], frozen_splits: Optional[list[str]],
    verdict: Optional[dict[str, Any]], now: Callable[[], str],
    freeze: Callable[[dict[str, Any], list[str]], Any],
) -> Optional[Hook]:
    """Compose the hook, or None when there is nothing to write beside the completion.

    ``frozen_splits`` (None = not a design completion) is resolved by the caller BEFORE
    the lock (it reads the design/project config files); ``freeze`` applies it in place
    (``phase_task_planning.apply_frozen_splits``). ``verdict`` (None = the gate did not
    run) produces the gate record; ``override`` marks it ``overridden``.
    """
    if override is None and frozen_splits is None and verdict is None:
        return None

    def _hook(config: dict[str, Any], task: dict[str, Any]) -> None:
        if override is not None:
            override(config, task)
        if frozen_splits is not None:
            freeze(config, frozen_splits)
        if verdict is not None:
            task["gate"] = phase_gate.gate_record(task, verdict,
                                                  overridden=override is not None, at=now())

    return _hook
