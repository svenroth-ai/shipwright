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

  it("detectOrphans returns tasks with task_created but no completion", () => {
    const store = new EventStore();
    store.replayProject("p1", [
      makeEvent({ type: "task_created", task_id: "t1", description: "Orphan" }),
      makeEvent({ type: "task_created", task_id: "t2", description: "Done" }),
      makeEvent({ type: "work_completed", task_id: "t2" }),
    ]);
    const orphans = store.detectOrphans();
    expect(orphans).toHaveLength(1);
    expect(orphans[0].id).toBe("t1");
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
