import { describe, it, expect, vi } from "vitest";
import { HeartbeatScheduler } from "./heartbeat.js";
import type { ProcessGovernor, GovernorDeps } from "./process-governor.js";
import type { CronDeps } from "./heartbeat.js";

describe("HeartbeatScheduler", () => {
  function setup(isRunning: boolean = true) {
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
          ? [{ pid: 123, taskId: "t1", state: "running" }]
          : [{ pid: 999, taskId: "t1", state: "running" }]
      ),
      getQueueLength: vi.fn(() => 0),
      release: vi.fn(async () => {}),
    } as unknown as ProcessGovernor;

    const scheduler = new HeartbeatScheduler(governor, govDeps, cronDeps);
    return { scheduler, scheduledCallback: () => scheduledCallback?.(), governor, stopFn, govDeps };
  }

  it("detects dead process and calls release", () => {
    const { scheduler, scheduledCallback, governor, govDeps } = setup(false);
    scheduler.start();
    scheduledCallback();
    expect(governor.release).toHaveBeenCalledWith("t1");
  });

  it("healthy processes: no release called", () => {
    const { scheduler, scheduledCallback, governor } = setup(true);
    scheduler.start();
    scheduledCallback();
    expect(governor.release).not.toHaveBeenCalled();
  });

  it("stop destroys cron job", () => {
    const { scheduler, stopFn } = setup(true);
    scheduler.start();
    scheduler.stop();
    expect(stopFn).toHaveBeenCalled();
  });
});
