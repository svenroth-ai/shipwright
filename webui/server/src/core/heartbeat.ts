import type { ProcessGovernor, GovernorDeps } from "./process-governor.js";

export interface CronDeps {
  schedule: (expression: string, callback: () => void) => { stop: () => void };
}

export interface HeartbeatEventSink {
  onDeadProcess: (taskId: string, projectId: string) => void;
}

export class HeartbeatScheduler {
  private job: { stop: () => void } | null = null;

  constructor(
    private governor: ProcessGovernor,
    private deps: GovernorDeps,
    private cronDeps: CronDeps,
    private eventSink?: HeartbeatEventSink,
    private expression: string = "*/30 * * * * *"
  ) {}

  start(): void {
    this.job = this.cronDeps.schedule(this.expression, () => {
      this.check();
    });
  }

  stop(): void {
    this.job?.stop();
    this.job = null;
  }

  private check(): void {
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
}
