import { describe, it, expect, vi } from "vitest";
import {
  deriveKanbanStatus,
  TaskManager,
  DEFAULT_PHASE_TO_STATUS_MAPPING,
  ORPHAN_REASONS,
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

  it("phase project -> in_progress (new default)", () => {
    expect(deriveKanbanStatus({ currentPhase: "project", status: "running" }, mapping)).toBe("in_progress");
  });

  it("phase design -> in_progress (new default)", () => {
    expect(deriveKanbanStatus({ currentPhase: "design", status: "running" }, mapping)).toBe("in_progress");
  });

  it("phase plan -> in_progress (new default)", () => {
    expect(deriveKanbanStatus({ currentPhase: "plan", status: "running" }, mapping)).toBe("in_progress");
  });

  it("phase deploy -> in_review (new default)", () => {
    expect(deriveKanbanStatus({ currentPhase: "deploy", status: "running" }, mapping)).toBe("in_review");
  });

  it("phase changelog -> in_review (new default)", () => {
    expect(deriveKanbanStatus({ currentPhase: "changelog", status: "running" }, mapping)).toBe("in_review");
  });

  it("phase security -> in_review (new entry)", () => {
    expect(deriveKanbanStatus({ currentPhase: "security", status: "running" }, mapping)).toBe("in_review");
  });

  it("phase compliance -> in_review (new entry)", () => {
    expect(deriveKanbanStatus({ currentPhase: "compliance", status: "running" }, mapping)).toBe("in_review");
  });

  it("unknown-phase + running -> backlog (fallback)", () => {
    expect(deriveKanbanStatus({ currentPhase: "unknown-phase", status: "running" }, mapping)).toBe("backlog");
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

  // Iterate 14.7.0 / 14.9 — resumable orphans now keep their phase column
  // instead of being forced into a separate "interrupted" bucket.
  // TaskCard derives the pause/resume affordance from task.status +
  // task.orphanReason directly.
  it("status orphaned + stale_on_startup + claudeSessionId + phase=build -> in_progress (phase column)", () => {
    expect(
      deriveKanbanStatus(
        {
          status: "orphaned",
          orphanReason: "stale_on_startup",
          claudeSessionId: "real-claude-sess-abc",
          currentPhase: "build",
        },
        mapping,
      ),
    ).toBe("in_progress");
  });

  it("status orphaned + stale_on_startup + claudeSessionId + phase=test -> in_review (phase column)", () => {
    expect(
      deriveKanbanStatus(
        {
          status: "orphaned",
          orphanReason: "stale_on_startup",
          claudeSessionId: "real-claude-sess-abc",
          currentPhase: "test",
        },
        mapping,
      ),
    ).toBe("in_review");
  });

  it("status orphaned + stale_on_startup + claudeSessionId + no phase -> in_progress (fallback)", () => {
    expect(
      deriveKanbanStatus(
        {
          status: "orphaned",
          orphanReason: "stale_on_startup",
          claudeSessionId: "real-claude-sess-abc",
        },
        mapping,
      ),
    ).toBe("in_progress");
  });

  it("status orphaned + stale_on_startup but no claudeSessionId -> backlog", () => {
    expect(
      deriveKanbanStatus(
        { status: "orphaned", orphanReason: "stale_on_startup" },
        mapping,
      ),
    ).toBe("backlog");
  });

  it("status orphaned + process_dead -> backlog (even with claudeSessionId)", () => {
    expect(
      deriveKanbanStatus(
        {
          status: "orphaned",
          orphanReason: "process_dead",
          claudeSessionId: "real-claude-sess-abc",
        },
        mapping,
      ),
    ).toBe("backlog");
  });

  // Iterate 14.8.3 — user-initiated interrupt
  // Iterate 14.9 — same as stale_on_startup: keep phase column.
  it("status orphaned + user_interrupted + claudeSessionId + phase=test -> in_review (phase column)", () => {
    expect(
      deriveKanbanStatus(
        {
          status: "orphaned",
          orphanReason: "user_interrupted",
          claudeSessionId: "real-claude-sess-abc",
          currentPhase: "test",
        },
        mapping,
      ),
    ).toBe("in_review");
  });

  it("status orphaned + user_interrupted + claudeSessionId + phase=project -> in_progress", () => {
    expect(
      deriveKanbanStatus(
        {
          status: "orphaned",
          orphanReason: "user_interrupted",
          claudeSessionId: "real-claude-sess-abc",
          currentPhase: "project",
        },
        mapping,
      ),
    ).toBe("in_progress");
  });

  it("status orphaned + user_interrupted but no claudeSessionId -> backlog", () => {
    expect(
      deriveKanbanStatus(
        { status: "orphaned", orphanReason: "user_interrupted" },
        mapping,
      ),
    ).toBe("backlog");
  });
});

describe("ORPHAN_REASONS", () => {
  it("exports the three expected reason constants", () => {
    expect(ORPHAN_REASONS.STALE_ON_STARTUP).toBe("stale_on_startup");
    expect(ORPHAN_REASONS.PROCESS_DEAD).toBe("process_dead");
    expect(ORPHAN_REASONS.USER_INTERRUPTED).toBe("user_interrupted");
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

  it("resolveMapping({ project: 'in_review' }) overrides project to in_review", () => {
    const mgr = new TaskManager({ getTasksForProject: () => [] } as unknown as EventStore);
    const resolved = mgr.resolveMapping({ project: "in_review" });
    expect(resolved.project).toBe("in_review");
    // Other phases remain default
    expect(resolved.build).toBe("in_progress");
    expect(resolved.test).toBe("in_review");
    expect(resolved.deploy).toBe("in_review");
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
