import { describe, it, expect, vi } from "vitest";
import {
  deriveKanbanStatus,
  TaskManager,
  DEFAULT_PHASE_TO_STATUS_MAPPING,
} from "./task-manager.js";
import type { EventStore } from "./event-store.js";
import type { Task, TaskStatus, KanbanStatus, PhaseToStatusMapping } from "../../../client/src/types/task.js";

function makeTask(overrides: Partial<Task>): Task {
  return {
    id: "t1",
    projectId: "p1",
    description: "Test task",
    status: "pending",
    kanbanStatus: "backlog",
    sessionId: "s1",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("deriveKanbanStatus", () => {
  const mapping = DEFAULT_PHASE_TO_STATUS_MAPPING;

  it("phase build -> in_progress", () => {
    expect(deriveKanbanStatus({ currentPhase: "build", status: "running" }, mapping)).toBe("in_progress");
  });

  it("phase test -> in_review", () => {
    expect(deriveKanbanStatus({ currentPhase: "test", status: "running" }, mapping)).toBe("in_review");
  });

  it("phase project -> backlog", () => {
    expect(deriveKanbanStatus({ currentPhase: "project", status: "running" }, mapping)).toBe("backlog");
  });

  it("phase deploy -> done", () => {
    expect(deriveKanbanStatus({ currentPhase: "deploy", status: "running" }, mapping)).toBe("done");
  });

  it("no phase and status pending -> backlog", () => {
    expect(deriveKanbanStatus({ status: "pending" }, mapping)).toBe("backlog");
  });

  it("status done regardless of phase -> done", () => {
    expect(deriveKanbanStatus({ currentPhase: "build", status: "done" }, mapping)).toBe("done");
  });

  it("status failed -> failed", () => {
    expect(deriveKanbanStatus({ status: "failed" }, mapping)).toBe("failed");
  });

  it("status cancelled -> cancelled", () => {
    expect(deriveKanbanStatus({ status: "cancelled" }, mapping)).toBe("cancelled");
  });

  it("status orphaned -> backlog", () => {
    expect(deriveKanbanStatus({ status: "orphaned" }, mapping)).toBe("backlog");
  });
});

describe("custom mapping", () => {
  it("custom mapping overrides default for build", () => {
    const custom: PhaseToStatusMapping = { build: "in_review" };
    const resolved = { ...DEFAULT_PHASE_TO_STATUS_MAPPING, ...custom };
    expect(deriveKanbanStatus({ currentPhase: "build", status: "running" }, resolved)).toBe("in_review");
  });

  it("custom mapping missing test uses default", () => {
    const custom: PhaseToStatusMapping = { build: "in_review" };
    const resolved = { ...DEFAULT_PHASE_TO_STATUS_MAPPING, ...custom };
    expect(deriveKanbanStatus({ currentPhase: "test", status: "running" }, resolved)).toBe("in_review");
  });
});

describe("TaskManager", () => {
  function mockEventStore(tasks: Task[]): EventStore {
    return {
      getTasksForProject: vi.fn(() => tasks),
    } as unknown as EventStore;
  }

  it("getTasksWithKanban returns tasks with kanbanStatus populated", () => {
    const tasks = [makeTask({ currentPhase: "build", status: "running" })];
    const store = mockEventStore(tasks);
    const mgr = new TaskManager(store);
    const result = mgr.getTasksWithKanban("p1");
    expect(result[0].kanbanStatus).toBe("in_progress");
  });

  it("getTasksWithKanban with custom mapping applies overrides", () => {
    const tasks = [makeTask({ currentPhase: "build", status: "running" })];
    const store = mockEventStore(tasks);
    const mgr = new TaskManager(store);
    const result = mgr.getTasksWithKanban("p1", { build: "in_review" });
    expect(result[0].kanbanStatus).toBe("in_review");
  });

  it("getTaskById returns single task or undefined", () => {
    const tasks = [makeTask({ id: "t1" }), makeTask({ id: "t2" })];
    const store = mockEventStore(tasks);
    const mgr = new TaskManager(store);
    expect(mgr.getTaskById("p1", "t1")?.id).toBe("t1");
    expect(mgr.getTaskById("p1", "t99")).toBeUndefined();
  });

  it("getTasksByStatus filters correctly", () => {
    const tasks = [
      makeTask({ id: "t1", currentPhase: "build", status: "running" }),
      makeTask({ id: "t2", status: "done" }),
    ];
    const store = mockEventStore(tasks);
    const mgr = new TaskManager(store);
    const inProgress = mgr.getTasksByStatus("p1", "in_progress");
    expect(inProgress).toHaveLength(1);
    expect(inProgress[0].id).toBe("t1");
  });
});
