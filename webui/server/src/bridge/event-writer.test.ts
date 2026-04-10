import { describe, it, expect, vi } from "vitest";
import { appendEvent, emitTaskCreatedEvent } from "./event-writer.js";
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
  });
});
