import { describe, it, expect, vi } from "vitest";
import {
  appendEvent,
  emitTaskCreatedEvent,
  emitTaskCancelledEvent,
  emitTaskOrphanedEvent,
  emitTaskUpdatedEvent,
  emitWorkCompletedEvent,
  emitSessionCapturedEvent,
  emitTaskResumedEvent,
} from "./event-writer.js";
import type { WriterDeps } from "./event-writer.js";
import type { ShipwrightEvent } from "../../../client/src/types/event.js";

function mockDeps(): WriterDeps & { appended: string[] } {
  const appended: string[] = [];
  return {
    appended,
    appendFile: vi.fn(async (_path: string, data: string) => {
      appended.push(data);
    }),
    lock: vi.fn(async () => vi.fn(async () => {})),
  };
}

describe("appendEvent", () => {
  it("appends event with trailing newline", async () => {
    const deps = mockDeps();
    const event: ShipwrightEvent = {
      type: "task_created",
      timestamp: "2026-01-01T00:00:00Z",
      task_id: "t1",
    };
    await appendEvent("events.jsonl", event, deps);
    expect(deps.appended).toHaveLength(1);
    expect(deps.appended[0]).toMatch(/\n$/);
    expect(JSON.parse(deps.appended[0].trim())).toEqual(event);
  });

  it("acquires lock before write and releases after", async () => {
    const releaseFn = vi.fn(async () => {});
    const deps: WriterDeps = {
      appendFile: vi.fn(async () => {}),
      lock: vi.fn(async () => releaseFn),
    };
    const event: ShipwrightEvent = {
      type: "task_created",
      timestamp: "2026-01-01T00:00:00Z",
      task_id: "t1",
    };
    await appendEvent("events.jsonl", event, deps);
    expect(deps.lock).toHaveBeenCalledWith("events.jsonl");
    expect(releaseFn).toHaveBeenCalled();
  });
});

describe("emitTaskCreatedEvent", () => {
  it("produces correct event shape", async () => {
    const deps = mockDeps();
    const event = await emitTaskCreatedEvent(
      "events.jsonl",
      "t1",
      "p1",
      "Fix bug",
      "fix",
      "low",
      undefined,
      deps
    );
    expect(event.type).toBe("task_created");
    expect(event.task_id).toBe("t1");
    expect(event.project_id).toBe("p1");
    expect(event.description).toBe("Fix bug");
    expect(event.intent).toBe("fix");
    expect(event.priority).toBe("low");
    expect(event.source).toBe("webui");
    expect(event.timestamp).toBeDefined();
    expect(event.phase).toBeUndefined();
  });

  it("includes phase when provided", async () => {
    const deps = mockDeps();
    const event = await emitTaskCreatedEvent(
      "events.jsonl",
      "t1",
      "p1",
      "Design hero",
      undefined,
      undefined,
      "design",
      deps
    );
    expect(event.phase).toBe("design");
  });
});

describe("emitTaskCancelledEvent", () => {
  it("writes a task_cancelled event to disk and returns it", async () => {
    const deps = mockDeps();
    const event = await emitTaskCancelledEvent("events.jsonl", "t1", "p1", deps);
    expect(event.type).toBe("task_cancelled");
    expect(event.task_id).toBe("t1");
    expect(event.project_id).toBe("p1");
    expect(event.source).toBe("webui");
    expect(deps.appended).toHaveLength(1);
    expect(JSON.parse(deps.appended[0].trim()).type).toBe("task_cancelled");
  });
});

describe("emitWorkCompletedEvent", () => {
  it("writes a work_completed event to disk and returns it", async () => {
    const deps = mockDeps();
    const event = await emitWorkCompletedEvent("events.jsonl", "t1", "p1", deps);
    expect(event.type).toBe("work_completed");
    expect(event.task_id).toBe("t1");
    expect(event.project_id).toBe("p1");
    expect(deps.appended).toHaveLength(1);
  });
});

describe("emitTaskOrphanedEvent", () => {
  it("writes a task_orphaned event with reason in detail field", async () => {
    const deps = mockDeps();
    const event = await emitTaskOrphanedEvent(
      "events.jsonl",
      "t1",
      "p1",
      "process_dead",
      deps,
    );
    expect(event.type).toBe("task_orphaned");
    expect(event.task_id).toBe("t1");
    expect(event.project_id).toBe("p1");
    expect(event.detail).toBe("process_dead");
    expect(event.source).toBe("webui");
    expect(deps.appended).toHaveLength(1);
    const written = JSON.parse(deps.appended[0].trim());
    expect(written.type).toBe("task_orphaned");
    expect(written.detail).toBe("process_dead");
  });

  it("distinguishes stale_on_startup vs process_dead reasons", async () => {
    const deps = mockDeps();
    const startupEvent = await emitTaskOrphanedEvent(
      "events.jsonl", "t1", "p1", "stale_on_startup", deps,
    );
    const heartbeatEvent = await emitTaskOrphanedEvent(
      "events.jsonl", "t2", "p1", "process_dead", deps,
    );
    expect(startupEvent.detail).toBe("stale_on_startup");
    expect(heartbeatEvent.detail).toBe("process_dead");
  });
});

describe("emitTaskUpdatedEvent", () => {
  it("writes a task_updated event with title + description", async () => {
    const deps = mockDeps();
    const event = await emitTaskUpdatedEvent(
      "events.jsonl",
      "t1",
      "p1",
      { title: "New title", description: "New body" },
      deps,
    );
    expect(event.type).toBe("task_updated");
    expect(event.task_id).toBe("t1");
    expect((event as Record<string, unknown>).title).toBe("New title");
    expect((event as Record<string, unknown>).description).toBe("New body");
    expect(deps.appended).toHaveLength(1);
  });

  it("writes only the fields that were passed", async () => {
    const deps = mockDeps();
    const event = await emitTaskUpdatedEvent(
      "events.jsonl",
      "t1",
      "p1",
      { description: "Only body" },
      deps,
    );
    expect((event as Record<string, unknown>).title).toBeUndefined();
    expect((event as Record<string, unknown>).description).toBe("Only body");
  });
});

// Iterate 14.7.0 — session_captured and task_resumed
describe("emitSessionCapturedEvent", () => {
  it("writes session_captured event with session_id payload", async () => {
    const deps = mockDeps();
    const event = await emitSessionCapturedEvent(
      "events.jsonl",
      "t1",
      "p1",
      "real-claude-sess-abc123",
      deps,
    );
    expect(event.type).toBe("session_captured");
    expect(event.task_id).toBe("t1");
    expect(event.project_id).toBe("p1");
    expect((event as Record<string, unknown>).session_id).toBe("real-claude-sess-abc123");
    expect(deps.appended).toHaveLength(1);
    const written = JSON.parse(deps.appended[0].trim());
    expect(written.type).toBe("session_captured");
    expect(written.session_id).toBe("real-claude-sess-abc123");
  });
});

describe("emitTaskResumedEvent", () => {
  it("writes task_resumed event with session_id", async () => {
    const deps = mockDeps();
    const event = await emitTaskResumedEvent(
      "events.jsonl",
      "t1",
      "p1",
      "real-claude-sess-abc123",
      deps,
    );
    expect(event.type).toBe("task_resumed");
    expect(event.task_id).toBe("t1");
    expect((event as Record<string, unknown>).session_id).toBe("real-claude-sess-abc123");
    expect(deps.appended).toHaveLength(1);
  });
});
