import { describe, it, expect } from "vitest";
import { EventStore } from "./event-store.js";
import type { ShipwrightEvent } from "../../../client/src/types/event.js";

function makeEvent(overrides: Partial<ShipwrightEvent> & { type: ShipwrightEvent["type"]; task_id: string }): ShipwrightEvent {
  return {
    timestamp: new Date().toISOString(),
    ...overrides,
  };
}

describe("EventStore", () => {
  it("replay with task_created + work_completed -> task status is done", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Fix bug" }),
      makeEvent({ type: "work_completed", task_id: "t1" }),
    ]);
    const tasks = store.getTasksForProject("p1");
    expect(tasks).toHaveLength(1);
    expect(tasks[0].status).toBe("done");
  });

  it("replay with task_created only -> task status is pending", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Fix bug" }),
    ]);
    const tasks = store.getTasksForProject("p1");
    expect(tasks[0].status).toBe("pending");
  });

  it("deduplicates phase_completed within 60s, keeping one with detail", () => {
    const store = new EventStore();
    const t1 = "2026-01-01T00:00:00Z";
    const t2 = "2026-01-01T00:00:30Z";
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
      makeEvent({ type: "phase_completed", task_id: "t1", phase: "build", timestamp: t1 }),
      makeEvent({ type: "phase_completed", task_id: "t1", phase: "build", timestamp: t2, detail: "All tests pass" }),
    ]);
    const pipeline = store.getPipelineState("p1");
    const buildPhase = pipeline.find((p) => p.name === "build");
    expect(buildPhase?.detail).toBe("All tests pass");
  });

  it("keeps both phase_completed if >60s apart", () => {
    const store = new EventStore();
    const t1 = "2026-01-01T00:00:00Z";
    const t2 = "2026-01-01T00:02:00Z";
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
      makeEvent({ type: "phase_completed", task_id: "t1", phase: "build", timestamp: t1 }),
      makeEvent({ type: "phase_completed", task_id: "t1", phase: "build", timestamp: t2, detail: "Re-run" }),
    ]);
    const pipeline = store.getPipelineState("p1");
    const buildPhase = pipeline.find((p) => p.name === "build");
    expect(buildPhase?.status).toBe("completed");
  });

  it("task_orphaned flips running task to orphaned and updates timestamp", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
      makeEvent({ type: "phase_started", task_id: "t1", phase: "build" }),
    ]);
    expect(store.getTaskState("t1")?.status).toBe("running");

    store.addEvent("p1", makeEvent({
      type: "task_orphaned",
      task_id: "t1",
      timestamp: "2026-04-14T10:00:00Z",
    }));

    const task = store.getTaskState("t1");
    expect(task?.status).toBe("orphaned");
    expect(task?.updatedAt).toBe("2026-04-14T10:00:00Z");
  });

  it("task_orphaned is idempotent — does not flip already-orphaned task again", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
      makeEvent({ type: "phase_started", task_id: "t1", phase: "build" }),
    ]);

    store.addEvent("p1", makeEvent({
      type: "task_orphaned",
      task_id: "t1",
      timestamp: "2026-04-14T10:00:00Z",
    }));
    const firstUpdate = store.getTaskState("t1")?.updatedAt;

    // Second emit (e.g. startup reconciliation + first heartbeat race)
    store.addEvent("p1", makeEvent({
      type: "task_orphaned",
      task_id: "t1",
      timestamp: "2026-04-14T10:01:00Z",
    }));

    // Status stays orphaned; updatedAt is NOT re-touched because the
    // idempotency guard skipped the second apply.
    expect(store.getTaskState("t1")?.status).toBe("orphaned");
    expect(store.getTaskState("t1")?.updatedAt).toBe(firstUpdate);
  });

  it("task_orphaned does not clobber a done task (late orphan arrival)", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
      makeEvent({ type: "phase_started", task_id: "t1", phase: "build" }),
      makeEvent({ type: "work_completed", task_id: "t1" }),
    ]);
    expect(store.getTaskState("t1")?.status).toBe("done");

    // Late orphan event from a stale heartbeat tick — must be ignored.
    store.addEvent("p1", makeEvent({
      type: "task_orphaned",
      task_id: "t1",
    }));

    expect(store.getTaskState("t1")?.status).toBe("done");
  });

  it("task_orphaned for unknown task is a no-op (no throw)", () => {
    const store = new EventStore();
    expect(() => store.addEvent("p1", makeEvent({
      type: "task_orphaned",
      task_id: "ghost",
    }))).not.toThrow();
    expect(store.getTaskState("ghost")).toBeUndefined();
  });

  // Iterate 14.7.0 — session_captured + task_resumed + orphanReason
  it("session_captured stores claudeSessionId on task state", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
      makeEvent({ type: "phase_started", task_id: "t1", phase: "build" }),
      makeEvent({
        type: "session_captured",
        task_id: "t1",
        project_id: "p1",
        session_id: "real-claude-sess-abc",
      }),
    ]);
    const task = store.getTaskState("t1");
    expect(task?.claudeSessionId).toBe("real-claude-sess-abc");
  });

  it("task_orphaned records orphanReason from event detail", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
      makeEvent({ type: "phase_started", task_id: "t1", phase: "build" }),
    ]);
    store.addEvent("p1", makeEvent({
      type: "task_orphaned",
      task_id: "t1",
      detail: "stale_on_startup",
    }));
    expect(store.getOrphanReason("t1")).toBe("stale_on_startup");
  });

  it("task_resumed flips orphaned task back to running and clears orphanReason", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
      makeEvent({ type: "phase_started", task_id: "t1", phase: "build" }),
      makeEvent({
        type: "session_captured",
        task_id: "t1",
        project_id: "p1",
        session_id: "real-claude-sess-abc",
      }),
      makeEvent({ type: "task_orphaned", task_id: "t1", detail: "stale_on_startup" }),
    ]);
    expect(store.getTaskState("t1")?.status).toBe("orphaned");
    expect(store.getOrphanReason("t1")).toBe("stale_on_startup");

    store.addEvent("p1", makeEvent({
      type: "task_resumed",
      task_id: "t1",
      project_id: "p1",
      session_id: "real-claude-sess-abc",
    }));

    const task = store.getTaskState("t1");
    expect(task?.status).toBe("running");
    expect(store.getOrphanReason("t1")).toBeUndefined();
    // claudeSessionId preserved (so a future interruption still resumes)
    expect(task?.claudeSessionId).toBe("real-claude-sess-abc");
  });

  it("addEvent incrementally updates state", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
    ]);
    expect(store.getTasksForProject("p1")[0].status).toBe("pending");

    store.addEvent("p1", makeEvent({ type: "phase_started", task_id: "t1", phase: "build" }));
    expect(store.getTasksForProject("p1")[0].status).toBe("running");
    expect(store.getTasksForProject("p1")[0].currentPhase).toBe("build");
  });

  it("task_created with phase populates task.requestedPhase", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Design hero", phase: "design" }),
    ]);
    const tasks = store.getTasksForProject("p1");
    expect(tasks[0].requestedPhase).toBe("design");
  });

  it("task_created without phase leaves requestedPhase undefined", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
    ]);
    const tasks = store.getTasksForProject("p1");
    expect(tasks[0].requestedPhase).toBeUndefined();
  });

  it("derives pipeline state with correct phase statuses", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Task" }),
      makeEvent({ type: "phase_started", task_id: "t1", phase: "project" }),
      makeEvent({ type: "phase_completed", task_id: "t1", phase: "project" }),
      makeEvent({ type: "phase_started", task_id: "t1", phase: "build" }),
    ]);
    const pipeline = store.getPipelineState("p1");
    const project = pipeline.find((p) => p.name === "project");
    const build = pipeline.find((p) => p.name === "build");
    expect(project?.status).toBe("completed");
    expect(build?.status).toBe("running");
  });

  it("replays 1000 events in under 2 seconds", () => {
    const store = new EventStore();
    const events: ShipwrightEvent[] = [];
    for (let i = 0; i < 1000; i++) {
      events.push(makeEvent({
        type: i % 2 === 0 ? "task_created" : "work_completed",
        task_id: `t${Math.floor(i / 2)}`,
        description: `Task ${i}`,
      }));
    }
    const start = Date.now();
    store.replayProject("p1", events);
    const duration = Date.now() - start;
    expect(duration).toBeLessThan(2000);
  });
});
