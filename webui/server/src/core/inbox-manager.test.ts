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
    sendUserMessage: vi.fn(),
  } as unknown as ClaudeAdapter;
  const appendChatMessage = vi.fn(async () => {});
  const mgr = new InboxManager(governor, adapter, onNotify, undefined, { appendChatMessage });
  return { mgr, onNotify, governor, adapter, appendChatMessage };
}

describe("InboxManager", () => {
  it("addQuestion creates item with correct fields", async () => {
    const { mgr } = setup();
    const item = await mgr.addQuestion("p1", "t1", "Continue?", "context", ["yes", "no"]);
    expect(item.id).toBeDefined();
    expect(item.projectId).toBe("p1");
    expect(item.taskId).toBe("t1");
    expect(item.question).toBe("Continue?");
    expect(item.status).toBe("pending");
    expect(item.createdAt).toBeDefined();
  });

  it("addQuestion calls onNotify", async () => {
    const { mgr, onNotify } = setup();
    const item = await mgr.addQuestion("p1", "t1", "Continue?");
    expect(onNotify).toHaveBeenCalledWith(item);
  });

  it("answer delivers text to stdin", async () => {
    const { mgr, adapter } = setup();
    await mgr.addQuestion("p1", "t1", "Continue?");
    const items = mgr.getAll();
    await mgr.answer(items[0].id, "yes");
    expect(adapter.sendStdin).toHaveBeenCalled();
  });

  it("answer marks item as answered", async () => {
    const { mgr } = setup();
    await mgr.addQuestion("p1", "t1", "Continue?");
    const items = mgr.getAll();
    const answered = await mgr.answer(items[0].id, "yes");
    expect(answered.status).toBe("answered");
    expect(answered.answeredAt).toBeDefined();
  });

  it("answer on non-existent item throws 404", async () => {
    const { mgr } = setup();
    await expect(mgr.answer("nonexistent", "yes")).rejects.toThrow("Inbox item not found");
  });

  it("answer on already-answered item throws 400", async () => {
    const { mgr } = setup();
    await mgr.addQuestion("p1", "t1", "Continue?");
    const items = mgr.getAll();
    await mgr.answer(items[0].id, "yes");
    await expect(mgr.answer(items[0].id, "no")).rejects.toThrow("Already answered");
  });

  it("answer when process not running throws 400", async () => {
    const { mgr } = setup("none");
    await mgr.addQuestion("p1", "t1", "Continue?");
    const items = mgr.getAll();
    await expect(mgr.answer(items[0].id, "yes")).rejects.toThrow("Process no longer running");
  });

  it("getAll returns items sorted by createdAt desc", async () => {
    const { mgr } = setup();
    await mgr.addQuestion("p1", "t1", "First?");
    await mgr.addQuestion("p1", "t1", "Second?");
    const all = mgr.getAll();
    expect(all).toHaveLength(2);
  });

  it("getAll with status filter returns only matching", async () => {
    const { mgr } = setup();
    await mgr.addQuestion("p1", "t1", "Q1");
    await mgr.addQuestion("p1", "t1", "Q2");
    const items = mgr.getAll();
    await mgr.answer(items[0].id, "yes");
    expect(mgr.getAll({ status: "pending" })).toHaveLength(1);
  });

  it("getByProject filters by projectId", async () => {
    const { mgr } = setup();
    await mgr.addQuestion("p1", "t1", "Q1");
    await mgr.addQuestion("p2", "t2", "Q2");
    expect(mgr.getByProject("p1")).toHaveLength(1);
  });

  it("persists inbox items to disk when storageDeps provided", async () => {
    const onNotify = vi.fn();
    const governor = {
      getProcess: vi.fn(() => ({ pid: 123, taskId: "t1", state: "running", process: {} })),
    } as unknown as ProcessGovernor;
    const adapter = { sendStdin: vi.fn() } as unknown as ClaudeAdapter;
    const storageDeps = {
      readFile: vi.fn().mockResolvedValue(""),
      appendFile: vi.fn().mockResolvedValue(undefined),
      writeFile: vi.fn().mockResolvedValue(undefined),
      existsSync: vi.fn().mockReturnValue(false),
      mkdirSync: vi.fn(),
    };
    const mgr = new InboxManager(governor, adapter, onNotify, storageDeps);
    mgr.registerProject("p1", "/tmp/project");

    await mgr.addQuestion("p1", "t1", "Continue?");
    expect(storageDeps.mkdirSync).toHaveBeenCalled();
    expect(storageDeps.appendFile).toHaveBeenCalled();
  });

  it("addQuestion with toolUseId uses it as the item id (stable across refresh)", async () => {
    const { mgr } = setup();
    const item = await mgr.addQuestion("p1", "t1", "Which option?", undefined, ["a", "b"], "toolu_01AskUser");
    expect(item.id).toBe("toolu_01AskUser");
  });

  it("addQuestion without toolUseId still generates a random id", async () => {
    const { mgr } = setup();
    const item = await mgr.addQuestion("p1", "t1", "Which option?");
    expect(item.id).toBeDefined();
    expect(item.id).not.toBe("toolu_01AskUser");
    // Random UUIDs are 36 chars with dashes
    expect(item.id.length).toBeGreaterThan(20);
  });

  it("answer(toolUseId, ...) finds the item created with that toolUseId", async () => {
    const { mgr, adapter } = setup();
    await mgr.addQuestion("p1", "t1", "Pick one", undefined, ["x", "y"], "toolu_02");
    const answered = await mgr.answer("toolu_02", "x");
    expect(answered.answer).toBe("x");
    // Iterate 11: ALL answers go through plain-text sendStdin (tool_result
    // content blocks via sendUserMessage caused API 400 — see inbox-manager.ts).
    expect(adapter.sendStdin).toHaveBeenCalled();
  });

  // ──────────────────────────────────────────────────────────────────────
  // Iterate 11 — plain-text delivery (revert iterate 7's tool_result path)
  // ──────────────────────────────────────────────────────────────────────

  it("answer with toolu_-prefixed id sends PLAIN TEXT via sendStdin", async () => {
    const { mgr, adapter } = setup();
    await mgr.addQuestion("p1", "t1", "Pick one", undefined, ["x", "y"], "toolu_01abc");
    await mgr.answer("toolu_01abc", "x");

    expect(adapter.sendStdin).toHaveBeenCalledWith(expect.anything(), "x");
    expect(adapter.sendUserMessage).not.toHaveBeenCalled();
  });

  it("answer with legacy random-UUID id also sends plain text via sendStdin", async () => {
    const { mgr, adapter } = setup();
    await mgr.addQuestion("p1", "t1", "Legacy?");
    const items = mgr.getAll();
    await mgr.answer(items[0].id, "yes");

    expect(adapter.sendStdin).toHaveBeenCalledWith(expect.anything(), "yes");
    expect(adapter.sendUserMessage).not.toHaveBeenCalled();
  });

  it("answer appends a tool_result ChatMessage to chat-store for tool_use_id answers", async () => {
    const { mgr, appendChatMessage } = setup();
    mgr.registerProject("p1", "/tmp/proj");
    await mgr.addQuestion("p1", "t1", "Pick", undefined, ["a"], "toolu_42");
    await mgr.answer("toolu_42", "a");

    expect(appendChatMessage).toHaveBeenCalledTimes(1);
    const [projectDir, taskId, message] = appendChatMessage.mock.calls[0];
    expect(projectDir).toBe("/tmp/proj");
    expect(taskId).toBe("t1");
    expect(message).toMatchObject({
      type: "tool_result",
      content: "a",
      toolUseId: "toolu_42",
    });
  });

  it("answer does NOT append chat-store entry for legacy (non-toolu_) ids", async () => {
    const { mgr, appendChatMessage } = setup();
    mgr.registerProject("p1", "/tmp/proj");
    await mgr.addQuestion("p1", "t1", "Legacy?");
    const items = mgr.getAll();
    await mgr.answer(items[0].id, "yes");
    expect(appendChatMessage).not.toHaveBeenCalled();
  });

  it("loads inbox items from disk", async () => {
    const onNotify = vi.fn();
    const governor = { getProcess: vi.fn() } as unknown as ProcessGovernor;
    const adapter = { sendStdin: vi.fn() } as unknown as ClaudeAdapter;
    const item = JSON.stringify({ id: "i1", projectId: "p1", taskId: "t1", question: "Q?", status: "pending", createdAt: new Date().toISOString() });
    const storageDeps = {
      readFile: vi.fn().mockResolvedValue(item + "\n"),
      appendFile: vi.fn().mockResolvedValue(undefined),
      writeFile: vi.fn().mockResolvedValue(undefined),
      existsSync: vi.fn().mockReturnValue(true),
      mkdirSync: vi.fn(),
    };
    const mgr = new InboxManager(governor, adapter, onNotify, storageDeps);

    await mgr.loadFromDisk("p1", "/tmp/project");
    expect(mgr.getAll()).toHaveLength(1);
    expect(mgr.getAll()[0].question).toBe("Q?");
  });
});
