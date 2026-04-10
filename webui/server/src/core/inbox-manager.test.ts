import { describe, it, expect, vi } from "vitest";
import { InboxManager } from "./inbox-manager.js";
import type { ProcessGovernor } from "./process-governor.js";
import type { ClaudeAdapter, ClaudeProcess } from "./claude-adapter.js";

function setup(processState: string = "running") {
  const onNotify = vi.fn();
  const governor = {
    getProcess: vi.fn(() =>
      processState === "none"
        ? undefined
        : ({ pid: 123, taskId: "t1", state: processState, process: {} } as unknown as ClaudeProcess)
    ),
  } as unknown as ProcessGovernor;
  const adapter = {
    sendStdin: vi.fn(),
  } as unknown as ClaudeAdapter;
  const mgr = new InboxManager(governor, adapter, onNotify);
  return { mgr, onNotify, governor, adapter };
}

describe("InboxManager", () => {
  it("addQuestion creates item with correct fields", () => {
    const { mgr } = setup();
    const item = mgr.addQuestion("p1", "t1", "Continue?", "context", ["yes", "no"]);
    expect(item.id).toBeDefined();
    expect(item.projectId).toBe("p1");
    expect(item.taskId).toBe("t1");
    expect(item.question).toBe("Continue?");
    expect(item.status).toBe("pending");
    expect(item.createdAt).toBeDefined();
  });

  it("addQuestion calls onNotify", () => {
    const { mgr, onNotify } = setup();
    const item = mgr.addQuestion("p1", "t1", "Continue?");
    expect(onNotify).toHaveBeenCalledWith(item);
  });

  it("answer delivers text to stdin", () => {
    const { mgr, adapter } = setup();
    mgr.addQuestion("p1", "t1", "Continue?");
    const items = mgr.getAll();
    mgr.answer(items[0].id, "yes");
    expect(adapter.sendStdin).toHaveBeenCalled();
  });

  it("answer marks item as answered", () => {
    const { mgr } = setup();
    mgr.addQuestion("p1", "t1", "Continue?");
    const items = mgr.getAll();
    const answered = mgr.answer(items[0].id, "yes");
    expect(answered.status).toBe("answered");
    expect(answered.answeredAt).toBeDefined();
  });

  it("answer on non-existent item throws 404", () => {
    const { mgr } = setup();
    expect(() => mgr.answer("nonexistent", "yes")).toThrow("Inbox item not found");
  });

  it("answer on already-answered item throws 400", () => {
    const { mgr } = setup();
    mgr.addQuestion("p1", "t1", "Continue?");
    const items = mgr.getAll();
    mgr.answer(items[0].id, "yes");
    expect(() => mgr.answer(items[0].id, "no")).toThrow("Already answered");
  });

  it("answer when process not running throws 400", () => {
    const { mgr } = setup("none");
    mgr.addQuestion("p1", "t1", "Continue?");
    const items = mgr.getAll();
    expect(() => mgr.answer(items[0].id, "yes")).toThrow("Process no longer running");
  });

  it("getAll returns items sorted by createdAt desc", () => {
    const { mgr } = setup();
    mgr.addQuestion("p1", "t1", "First?");
    mgr.addQuestion("p1", "t1", "Second?");
    const all = mgr.getAll();
    expect(all).toHaveLength(2);
  });

  it("getAll with status filter returns only matching", () => {
    const { mgr } = setup();
    mgr.addQuestion("p1", "t1", "Q1");
    mgr.addQuestion("p1", "t1", "Q2");
    const items = mgr.getAll();
    mgr.answer(items[0].id, "yes");
    expect(mgr.getAll({ status: "pending" })).toHaveLength(1);
  });

  it("getByProject filters by projectId", () => {
    const { mgr } = setup();
    mgr.addQuestion("p1", "t1", "Q1");
    mgr.addQuestion("p2", "t2", "Q2");
    expect(mgr.getByProject("p1")).toHaveLength(1);
  });
});
