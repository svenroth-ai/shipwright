import { describe, it, expect, vi } from "vitest";
import { HeartbeatScheduler, type HeartbeatReconcilerDeps } from "./heartbeat.js";
import type { ProcessGovernor, GovernorDeps } from "./process-governor.js";
import type { CronDeps } from "./heartbeat.js";
import type { ShipwrightEvent } from "../../../client/src/types/event.js";

describe("HeartbeatScheduler", () => {
  function setup(isRunning: boolean = true, reconciler?: HeartbeatReconcilerDeps) {
    let scheduledCallback: (() => void) | null = null;
    const stopFn = vi.fn();
    const cronDeps: CronDeps = {
      schedule: vi.fn((_expr, cb) => {
        scheduledCallback = cb;
        return { stop: stopFn };
      }),
    };
    const govDeps: GovernorDeps = {
      isProcessRunning: vi.fn(() => isRunning),
      kill: vi.fn(),
      readFile: vi.fn(async () => "[]"),
      writeFile: vi.fn(async () => {}),
      existsSync: vi.fn(() => true),
      mkdirSync: vi.fn(),
    };
    const governor = {
      getAllActive: vi.fn(() =>
        isRunning
          ? [{ pid: 123, taskId: "t1", projectId: "p1", state: "running" }]
          : [{ pid: 999, taskId: "t1", projectId: "p1", state: "running" }]
      ),
      getQueueLength: vi.fn(() => 0),
      release: vi.fn(async () => {}),
    } as unknown as ProcessGovernor;

    const scheduler = new HeartbeatScheduler(
      governor,
      govDeps,
      cronDeps,
      undefined,
      "*/30 * * * * *",
      reconciler,
    );
    return { scheduler, trigger: () => scheduledCallback?.(), governor, stopFn, govDeps };
  }

  it("detects dead process and calls release", async () => {
    const { scheduler, trigger, governor } = setup(false);
    scheduler.start();
    trigger();
    // check() is fire-and-forget inside the cron callback (void-wrapped),
    // so flush the microtask queue before asserting.
    await new Promise((resolve) => setImmediate(resolve));
    expect(governor.release).toHaveBeenCalledWith("t1");
  });

  it("healthy processes: no release called", async () => {
    const { scheduler, trigger, governor } = setup(true);
    scheduler.start();
    trigger();
    await new Promise((resolve) => setImmediate(resolve));
    expect(governor.release).not.toHaveBeenCalled();
  });

  it("stop destroys cron job", () => {
    const { scheduler, stopFn } = setup(true);
    scheduler.start();
    scheduler.stop();
    expect(stopFn).toHaveBeenCalled();
  });

  // ---------------------------------------------------------------------
  // Iterate 12.0b — reconciler plumbing
  // ---------------------------------------------------------------------

  it("emits task_orphaned event before release when reconciler is wired", async () => {
    const state = { id: "t1", projectId: "p1", status: "running" as const };
    const emit = vi.fn(async (_p, taskId, projectId, reason): Promise<ShipwrightEvent> => ({
      type: "task_orphaned",
      timestamp: "2026-04-14T10:00:00Z",
      task_id: taskId,
      project_id: projectId,
      detail: reason,
    }));
    const addEvent = vi.fn();
    const reconciler: HeartbeatReconcilerDeps = {
      eventStore: {
        getTaskState: vi.fn(() => state as any),
        addEvent,
      },
      resolveEventsPath: vi.fn(() => "/project/shipwright_events.jsonl"),
      emitTaskOrphaned: emit,
    };

    const { scheduler, trigger, governor } = setup(false, reconciler);
    scheduler.start();
    trigger();
    await new Promise((resolve) => setImmediate(resolve));

    expect(emit).toHaveBeenCalledWith(
      "/project/shipwright_events.jsonl",
      "t1",
      "p1",
      "process_dead",
    );
    expect(addEvent).toHaveBeenCalled();
    expect(governor.release).toHaveBeenCalledWith("t1");
  });

  it("reconciler skips emit when task is already non-running (idempotency)", async () => {
    const state = { id: "t1", projectId: "p1", status: "done" as const };
    const emit = vi.fn();
    const reconciler: HeartbeatReconcilerDeps = {
      eventStore: {
        getTaskState: vi.fn(() => state as any),
        addEvent: vi.fn(),
      },
      resolveEventsPath: vi.fn(() => "/project/shipwright_events.jsonl"),
      emitTaskOrphaned: emit,
    };

    const { scheduler, trigger, governor } = setup(false, reconciler);
    scheduler.start();
    trigger();
    await new Promise((resolve) => setImmediate(resolve));

    expect(emit).not.toHaveBeenCalled();
    // Release still happens even when the emit is skipped.
    expect(governor.release).toHaveBeenCalledWith("t1");
  });

  it("reconciler emit failure does not block governor.release (fail-open)", async () => {
    const emit = vi.fn(async () => {
      throw new Error("disk full");
    });
    const reconciler: HeartbeatReconcilerDeps = {
      eventStore: {
        getTaskState: vi.fn(() => ({ id: "t1", projectId: "p1", status: "running" } as any)),
        addEvent: vi.fn(),
      },
      resolveEventsPath: vi.fn(() => "/project/shipwright_events.jsonl"),
      emitTaskOrphaned: emit,
    };

    const { scheduler, trigger, governor } = setup(false, reconciler);
    scheduler.start();
    trigger();
    await new Promise((resolve) => setImmediate(resolve));

    expect(emit).toHaveBeenCalled();
    // Even though the writer threw, the governor slot is still released
    // so we never leak it.
    expect(governor.release).toHaveBeenCalledWith("t1");
  });

  it("reconciler skips when events path cannot be resolved", async () => {
    const emit = vi.fn();
    const reconciler: HeartbeatReconcilerDeps = {
      eventStore: {
        getTaskState: vi.fn(() => ({ id: "t1", projectId: "p1", status: "running" } as any)),
        addEvent: vi.fn(),
      },
      resolveEventsPath: vi.fn(() => undefined),
      emitTaskOrphaned: emit,
    };

    const { scheduler, trigger, governor } = setup(false, reconciler);
    scheduler.start();
    trigger();
    await new Promise((resolve) => setImmediate(resolve));

    expect(emit).not.toHaveBeenCalled();
    expect(governor.release).toHaveBeenCalledWith("t1");
  });
});
