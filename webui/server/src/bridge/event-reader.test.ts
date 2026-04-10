import { describe, it, expect } from "vitest";
import { readEventsFromFile } from "./event-reader.js";
import type { FileSystemDeps } from "./event-reader.js";

function mockFs(content: string | null): FileSystemDeps {
  return {
    readFile: async () => {
      if (content === null) throw new Error("ENOENT");
      return content;
    },
    existsSync: () => content !== null,
  };
}

describe("readEventsFromFile", () => {
  it("parses valid JSONL with 3 events", async () => {
    const lines = [
      JSON.stringify({ type: "task_created", timestamp: "2026-01-01T00:00:00Z", task_id: "t1" }),
      JSON.stringify({ type: "work_completed", timestamp: "2026-01-01T00:01:00Z", task_id: "t1" }),
      JSON.stringify({ type: "phase_started", timestamp: "2026-01-01T00:02:00Z", task_id: "t2", phase: "build" }),
    ].join("\n");
    const events = await readEventsFromFile("events.jsonl", mockFs(lines));
    expect(events).toHaveLength(3);
    expect(events[0].type).toBe("task_created");
  });

  it("skips corrupt line in the middle and returns valid events", async () => {
    const lines = [
      JSON.stringify({ type: "task_created", timestamp: "2026-01-01T00:00:00Z", task_id: "t1" }),
      "NOT VALID JSON",
      JSON.stringify({ type: "work_completed", timestamp: "2026-01-01T00:01:00Z", task_id: "t1" }),
    ].join("\n");
    const events = await readEventsFromFile("events.jsonl", mockFs(lines));
    expect(events).toHaveLength(2);
  });

  it("returns empty array for empty file", async () => {
    const events = await readEventsFromFile("events.jsonl", mockFs(""));
    expect(events).toHaveLength(0);
  });

  it("returns empty array when file does not exist", async () => {
    const events = await readEventsFromFile("events.jsonl", mockFs(null));
    expect(events).toHaveLength(0);
  });

  it("skips line with valid JSON but missing type field", async () => {
    const lines = [
      JSON.stringify({ timestamp: "2026-01-01T00:00:00Z", task_id: "t1" }),
      JSON.stringify({ type: "task_created", timestamp: "2026-01-01T00:00:00Z", task_id: "t1" }),
    ].join("\n");
    const events = await readEventsFromFile("events.jsonl", mockFs(lines));
    expect(events).toHaveLength(1);
  });
});
