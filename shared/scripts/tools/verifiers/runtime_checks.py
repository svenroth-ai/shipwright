"""Runtime reconciliation checks (zombie-task detection).

Iterate 12.0 ships this module as a **stub** — the real implementation
lands in 12.0b after the webui TypeScript event-store and heartbeat
changes are in place. The stub exists today so ``verify_phase.py`` can
dispatch the ``runtime`` phase name and surface a clear SKIPPED result
rather than silently producing a false-green.

Rationale (GPT R2 review): a stub that returns ``ok=True`` would let
``verify_phase --phase all`` pass before 12.0b ships. Instead we return
``ok=None`` with severity SKIPPED, which the CLI must render visibly
and must not count as a pass.

In 12.0b this module will:

1. Replay ``shipwright_events.jsonl`` into a task-state dict.
2. For each ``status == "running"`` task, look up ``webui/pids.json``
   (the governor's PID file) and verify the PID is alive.
3. Any running task without a live PID → WARNING (transient race
   possible during heartbeat tick) unless the ``task_orphaned`` event is
   also present, in which case → PASS.
"""

from __future__ import annotations

from pathlib import Path

from .common import CheckResult, Severity


def check_no_zombie_running_tasks(project_root: Path) -> CheckResult:
    """Stub — becomes a real check in iterate 12.0b.

    The signature matches the 12.0b implementation so callers don't have
    to change when the real check lands: same name, same single
    ``project_root`` argument, same return type. Only the body is a
    stub today.
    """
    del project_root  # not used in the stub
    return CheckResult(
        name="zombie_tasks",
        ok=None,
        detail="not implemented until 12.0b (webui event-store + heartbeat changes)",
        severity=Severity.SKIPPED.value,
    )


def run_all_checks(project_root: Path) -> list[CheckResult]:
    """Return the runtime check suite.

    Today this is a single stub; in 12.0b it will include
    ``check_no_zombie_running_tasks`` (real), plus a PID-file-vs-event-store
    drift check.
    """
    return [check_no_zombie_running_tasks(project_root)]
