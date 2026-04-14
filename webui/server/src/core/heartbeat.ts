import type { ProcessGovernor, GovernorDeps } from "./process-governor.js";
import type { EventStore } from "./event-store.js";
import type { ShipwrightEvent } from "../../../client/src/types/event.js";

export interface CronDeps {
  schedule: (expression: string, callback: () => void) => { stop: () => void };
}

export interface HeartbeatEventSink {
  onDeadProcess: (taskId: string, projectId: string) => void;
}

/**
 * Iterate 12.0b — zombie-task reconciler plumbing.
 *
 * When a heartbeat tick detects a dead PID, the scheduler needs to
 * persist that as a `task_orphaned` event before releasing the
 * governor slot, so the next restart's replay sees the task as
 * orphaned (and the Kanban UI + inbox filter render it correctly).
 *
 * `eventStore.getTaskState` is consulted first to skip emits for tasks
 * that have already flipped to a terminal state between ticks
 * (idempotency). `resolveEventsPath` turns a projectId into the
 * absolute path of the project's `shipwright_events.jsonl` so the
 * writer can append. `emitTaskOrphaned` is fail-open: if the write
 * fails we still release the governor slot — leaking a slot forever
 * is worse than missing one orphan-event line in the log.
 */
export interface HeartbeatReconcilerDeps {
  eventStore: Pick<EventStore, "getTaskState" | "addEvent">;
  resolveEventsPath: (projectId: string) => string | undefined;
  emitTaskOrphaned: (
    eventsPath: string,
    taskId: string,
    projectId: string,
    reason: string,
  ) => Promise<ShipwrightEvent>;
}

export class HeartbeatScheduler {
  private job: { stop: () => void } | null = null;

  constructor(
    private governor: ProcessGovernor,
    private deps: GovernorDeps,
    private cronDeps: CronDeps,
    private eventSink?: HeartbeatEventSink,
    private expression: string = "*/30 * * * * *",
    private reconciler?: HeartbeatReconcilerDeps,
  ) {}

  start(): void {
    this.job = this.cronDeps.schedule(this.expression, () => {
      // Fire-and-forget — cron callbacks don't await. Any reconciler
      // failure is logged inside `check` and does not propagate.
      void this.check();
    });
  }

  stop(): void {
    this.job?.stop();
    this.job = null;
  }

  // Public for testing (e.g. forcing a tick without waiting 30s).
  async check(): Promise<void> {
    const active = this.governor.getAllActive();
    for (const proc of active) {
      if (!this.deps.isProcessRunning(proc.pid)) {
        console.log(
          JSON.stringify({
            level: "warn",
            message: "Dead process detected",
            pid: proc.pid,
            taskId: proc.taskId,
          })
        );
        await this.reconcileOrphan(proc.taskId, proc.projectId, "process_dead");
        this.governor.release(proc.taskId);
        this.eventSink?.onDeadProcess(proc.taskId, proc.projectId);
      }
    }
    console.log(
      JSON.stringify({
        level: "info",
        message: "Heartbeat check",
        active: active.length,
        queue: this.governor.getQueueLength(),
      })
    );
  }

  /**
   * Emit a `task_orphaned` event for a dead PID before the governor
   * releases the slot. Idempotent + fail-open:
   *
   * 1. If the reconciler wasn't wired (legacy / unit-test paths), skip.
   * 2. If the task is already in a non-running status (e.g. cancelled
   *    between ticks), skip — would be a no-op anyway thanks to the
   *    event-store idempotency guard, but saves the write.
   * 3. If the path can't be resolved (deleted project?), skip with a
   *    warning — there's nowhere to write.
   * 4. Emit + addEvent. Any exception logs and returns; the caller
   *    still releases the slot so a broken writer can't leak slots.
   */
  private async reconcileOrphan(
    taskId: string,
    projectId: string,
    reason: string,
  ): Promise<void> {
    if (!this.reconciler) return;

    const state = this.reconciler.eventStore.getTaskState(taskId);
    if (!state || state.status !== "running") return;

    const eventsPath = this.reconciler.resolveEventsPath(projectId);
    if (!eventsPath) {
      console.log(JSON.stringify({
        level: "warn",
        message: "Heartbeat orphan reconciliation: events path unresolved",
        taskId,
        projectId,
      }));
      return;
    }

    try {
      const event = await this.reconciler.emitTaskOrphaned(
        eventsPath,
        taskId,
        projectId,
        reason,
      );
      this.reconciler.eventStore.addEvent(projectId, event);
    } catch (err) {
      console.error(JSON.stringify({
        level: "warn",
        message: "Heartbeat orphan reconciliation failed (fail-open)",
        taskId,
        projectId,
        error: String(err),
      }));
    }
  }
}
