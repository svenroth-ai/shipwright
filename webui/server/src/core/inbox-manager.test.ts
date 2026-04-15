import { describe, it, expect, vi } from "vitest";
import { InboxManager } from "./inbox-manager.js";
import type { ProcessGovernor } from "./process-governor.js";
import type { ClaudeAdapter, ClaudeProcess } from "./claude-adapter.js";
import type { InboxItemPart } from "../../../client/src/types/inbox.js";

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

function singlePart(question: string, options?: string[]): InboxItemPart[] {
  const part: InboxItemPart = { question };
  if (options) part.options = options;
  return [part];
}

async function answerOne(mgr: InboxManager, id: string, text: string) {
  return mgr.answer(id, [{ index: 0, answer: text }]);
}

describe("InboxManager — iterate 14.2 parts[] schema", () => {
  it("addQuestion creates an item with a parts[] array", async () => {
    const { mgr } = setup();
    const item = await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: [{ question: "Continue?", context: "ctx", options: ["yes", "no"] }],
    });
    expect(item.id).toBeDefined();
    expect(item.projectId).toBe("p1");
    expect(item.taskId).toBe("t1");
    expect(item.parts).toHaveLength(1);
    expect(item.parts[0].question).toBe("Continue?");
    expect(item.status).toBe("pending");
    expect(item.createdAt).toBeDefined();
  });

  it("addQuestion supports multi-part items", async () => {
    const { mgr } = setup();
    const item = await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: [
        { question: "Q1?", header: "A" },
        { question: "Q2?", header: "B", options: ["x", "y"] },
        { question: "Q3?", header: "C", allowMultiple: true, options: ["a", "b"] },
      ],
      toolUseId: "toolu_multi",
    });
    expect(item.id).toBe("toolu_multi");
    expect(item.parts).toHaveLength(3);
    expect(item.parts[2].allowMultiple).toBe(true);
  });

  it("addQuestion calls onNotify", async () => {
    const { mgr, onNotify } = setup();
    const item = await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Continue?"),
    });
    expect(onNotify).toHaveBeenCalledWith(item);
  });

  it("answer delivers joined text to stdin", async () => {
    const { mgr, adapter } = setup();
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Continue?") });
    const items = mgr.getAll();
    await answerOne(mgr, items[0].id, "yes");
    expect(adapter.sendStdin).toHaveBeenCalled();
    const arg = (adapter.sendStdin as ReturnType<typeof vi.fn>).mock.calls[0][1];
    // Single part fallback header: "Question 1"
    expect(arg).toBe("## Question 1\nyes");
  });

  it("answer joins multi-part answers with markdown headers", async () => {
    const { mgr, adapter } = setup();
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: [
        { question: "Q1?", header: "Priority" },
        { question: "Q2?", header: "Owner" },
      ],
      toolUseId: "toolu_multi2",
    });
    const item = await mgr.answer("toolu_multi2", [
      { index: 0, answer: "High" },
      { index: 1, answer: "Alice" },
    ]);
    expect(item.status).toBe("answered");
    const arg = (adapter.sendStdin as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(arg).toBe("## Priority\nHigh\n\n## Owner\nAlice");
  });

  it("answer rejects when not all parts are answered", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: [{ question: "Q1?" }, { question: "Q2?" }],
      toolUseId: "toolu_partial",
    });
    await expect(
      mgr.answer("toolu_partial", [{ index: 0, answer: "only first" }]),
    ).rejects.toThrow();
  });

  it("answer marks item as answered with answeredAt", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Q?") });
    const items = mgr.getAll();
    const answered = await answerOne(mgr, items[0].id, "yes");
    expect(answered.status).toBe("answered");
    expect(answered.answeredAt).toBeDefined();
    expect(answered.parts[0].answer).toBe("yes");
  });

  it("answer on non-existent item throws 404", async () => {
    const { mgr } = setup();
    await expect(answerOne(mgr, "nonexistent", "yes")).rejects.toThrow("Inbox item not found");
  });

  it("answer on already-answered item throws 400", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Q?") });
    const items = mgr.getAll();
    await answerOne(mgr, items[0].id, "yes");
    await expect(answerOne(mgr, items[0].id, "no")).rejects.toThrow("Already answered");
  });

  it("answer when process not running throws 400", async () => {
    const { mgr } = setup("none");
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Q?") });
    const items = mgr.getAll();
    await expect(answerOne(mgr, items[0].id, "yes")).rejects.toThrow("Process no longer running");
  });

  it("getAll returns items sorted by createdAt desc", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("First?") });
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Second?") });
    expect(mgr.getAll()).toHaveLength(2);
  });

  it("getAll with status filter returns only matching", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Q1") });
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Q2") });
    const items = mgr.getAll();
    await answerOne(mgr, items[0].id, "yes");
    expect(mgr.getAll({ status: "pending" })).toHaveLength(1);
  });

  it("getByProject filters by projectId", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Q1") });
    await mgr.addQuestion({ projectId: "p2", taskId: "t2", parts: singlePart("Q2") });
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

    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Continue?") });
    expect(storageDeps.mkdirSync).toHaveBeenCalled();
    expect(storageDeps.appendFile).toHaveBeenCalled();
  });

  it("addQuestion with toolUseId uses it as the item id (stable across refresh)", async () => {
    const { mgr } = setup();
    const item = await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Which option?", ["a", "b"]),
      toolUseId: "toolu_01AskUser",
    });
    expect(item.id).toBe("toolu_01AskUser");
  });

  it("addQuestion without toolUseId still generates a random id", async () => {
    const { mgr } = setup();
    const item = await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Which?") });
    expect(item.id).toBeDefined();
    expect(item.id).not.toBe("toolu_01AskUser");
    expect(item.id.length).toBeGreaterThan(20);
  });

  it("answer(toolUseId, ...) finds the item created with that toolUseId", async () => {
    const { mgr, adapter } = setup();
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Pick one", ["x", "y"]),
      toolUseId: "toolu_02",
    });
    const answered = await answerOne(mgr, "toolu_02", "x");
    expect(answered.parts[0].answer).toBe("x");
    expect(adapter.sendStdin).toHaveBeenCalled();
  });

  // ──────────────────────────────────────────────────────────────────────
  // Iterate 11 — plain-text delivery (revert iterate 7's tool_result path)
  // ──────────────────────────────────────────────────────────────────────

  it("answer with toolu_-prefixed id sends PLAIN TEXT (joined markdown) via sendStdin", async () => {
    const { mgr, adapter } = setup();
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Pick one", ["x", "y"]),
      toolUseId: "toolu_01abc",
    });
    await answerOne(mgr, "toolu_01abc", "x");

    expect(adapter.sendStdin).toHaveBeenCalled();
    expect(adapter.sendUserMessage).not.toHaveBeenCalled();
  });

  it("answer with legacy random-UUID id also sends plain text via sendStdin", async () => {
    const { mgr, adapter } = setup();
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Legacy?") });
    const items = mgr.getAll();
    await answerOne(mgr, items[0].id, "yes");

    expect(adapter.sendStdin).toHaveBeenCalled();
    expect(adapter.sendUserMessage).not.toHaveBeenCalled();
  });

  it("answer appends a tool_result ChatMessage to chat-store for tool_use_id answers", async () => {
    const { mgr, appendChatMessage } = setup();
    mgr.registerProject("p1", "/tmp/proj");
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Pick", ["a"]),
      toolUseId: "toolu_42",
    });
    await answerOne(mgr, "toolu_42", "a");

    expect(appendChatMessage).toHaveBeenCalledTimes(1);
    const [projectDir, taskId, message] = appendChatMessage.mock.calls[0];
    expect(projectDir).toBe("/tmp/proj");
    expect(taskId).toBe("t1");
    expect(message).toMatchObject({
      type: "tool_result",
      toolUseId: "toolu_42",
    });
    // Joined-format content (header fallback for missing header)
    expect(message.content).toBe("## Question 1\na");
  });

  it("answer does NOT append chat-store entry for legacy (non-toolu_) ids", async () => {
    const { mgr, appendChatMessage } = setup();
    mgr.registerProject("p1", "/tmp/proj");
    await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Legacy?") });
    const items = mgr.getAll();
    await answerOne(mgr, items[0].id, "yes");
    expect(appendChatMessage).not.toHaveBeenCalled();
  });

  // ──────────────────────────────────────────────────────────────────────
  // Iterate 11.1 — inbox-level dedupe of Claude's same-turn duplicates
  // ──────────────────────────────────────────────────────────────────────

  it("addQuestion dedupes same-text question for the same task (returns existing)", async () => {
    const { mgr, onNotify } = setup();
    const first = await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Which option?", ["a", "b"]),
      toolUseId: "toolu_01",
    });
    const second = await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("which option ?", ["a", "b"]),
      toolUseId: "toolu_02",
    });

    expect(second.id).toBe(first.id);
    expect(mgr.getAll()).toHaveLength(1);
    expect(onNotify).toHaveBeenCalledTimes(1);
  });

  it("addQuestion does NOT dedupe different multi-part signatures", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: [{ question: "A?" }, { question: "B?" }],
      toolUseId: "toolu_01",
    });
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: [{ question: "A?" }, { question: "C?" }],
      toolUseId: "toolu_02",
    });
    expect(mgr.getAll()).toHaveLength(2);
  });

  it("addQuestion does NOT dedupe different questions for the same task", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Which framework?"),
      toolUseId: "toolu_01",
    });
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Which database?"),
      toolUseId: "toolu_02",
    });
    expect(mgr.getAll()).toHaveLength(2);
  });

  it("addQuestion does NOT dedupe the same text across different tasks", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Same question?"),
      toolUseId: "toolu_01",
    });
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t2",
      parts: singlePart("Same question?"),
      toolUseId: "toolu_02",
    });
    expect(mgr.getAll()).toHaveLength(2);
  });

  it("addQuestion with a text matching an ANSWERED item still persists as new", async () => {
    const { mgr } = setup();
    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Pick one"),
      toolUseId: "toolu_01",
    });
    await answerOne(mgr, "toolu_01", "x");
    const second = await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Pick one"),
      toolUseId: "toolu_02",
    });
    expect(second.id).toBe("toolu_02");
    expect(mgr.getAll()).toHaveLength(2);
  });

  it("addQuestion uses explicit createdAt when provided (replay path)", async () => {
    const { mgr } = setup();
    const ts = "2026-04-13T09:15:00.000Z";
    const item = await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: singlePart("Replayed?"),
      toolUseId: "toolu_replay_01",
      createdAt: ts,
    });
    expect(item.createdAt).toBe(ts);
  });

  it("addQuestion defaults createdAt to now when not provided", async () => {
    const { mgr } = setup();
    const before = Date.now();
    const item = await mgr.addQuestion({ projectId: "p1", taskId: "t1", parts: singlePart("Fresh?") });
    const after = Date.now();
    const got = new Date(item.createdAt).getTime();
    expect(got).toBeGreaterThanOrEqual(before);
    expect(got).toBeLessThanOrEqual(after);
  });

  // ──────────────────────────────────────────────────────────────────────
  // Iterate 14.2 — per-line schema validation on load
  // ──────────────────────────────────────────────────────────────────────

  it("loadFromDisk loads v2 entries (parts[]) and ignores v1 legacy entries", async () => {
    const onNotify = vi.fn();
    const governor = { getProcess: vi.fn() } as unknown as ProcessGovernor;
    const adapter = { sendStdin: vi.fn() } as unknown as ClaudeAdapter;

    // Mix: 1 valid v2 + 2 legacy v1 entries
    const v2 = JSON.stringify({
      id: "toolu_v2",
      projectId: "p1",
      taskId: "t1",
      parts: [{ question: "v2?" }],
      status: "pending",
      createdAt: new Date().toISOString(),
    });
    const v1a = JSON.stringify({
      id: "toolu_v1a",
      projectId: "p1",
      taskId: "t1",
      question: "legacy?",
      status: "pending",
      createdAt: new Date().toISOString(),
    });
    const v1b = JSON.stringify({
      id: "toolu_v1b",
      projectId: "p1",
      taskId: "t1",
      question: "legacy2?",
      options: ["a"],
      status: "pending",
      createdAt: new Date().toISOString(),
    });
    const writeFile = vi.fn().mockResolvedValue(undefined);
    const storageDeps = {
      readFile: vi.fn().mockResolvedValue([v2, v1a, v1b].join("\n") + "\n"),
      appendFile: vi.fn().mockResolvedValue(undefined),
      writeFile,
      existsSync: vi.fn().mockReturnValue(true),
      mkdirSync: vi.fn(),
    };
    const mgr = new InboxManager(governor, adapter, onNotify, storageDeps);

    await mgr.loadFromDisk("p1", "/tmp/project");
    const all = mgr.getAll();
    expect(all).toHaveLength(1);
    expect(all[0].id).toBe("toolu_v2");
    // Rewrite was triggered because we purged 2 entries
    expect(writeFile).toHaveBeenCalledTimes(1);
  });

  it("loadFromDisk does NOT rewrite when every entry is valid v2", async () => {
    const onNotify = vi.fn();
    const governor = { getProcess: vi.fn() } as unknown as ProcessGovernor;
    const adapter = { sendStdin: vi.fn() } as unknown as ClaudeAdapter;
    const v2 = JSON.stringify({
      id: "toolu_only",
      projectId: "p1",
      taskId: "t1",
      parts: [{ question: "ok?" }],
      status: "pending",
      createdAt: new Date().toISOString(),
    });
    const writeFile = vi.fn().mockResolvedValue(undefined);
    const storageDeps = {
      readFile: vi.fn().mockResolvedValue(v2 + "\n"),
      appendFile: vi.fn().mockResolvedValue(undefined),
      writeFile,
      existsSync: vi.fn().mockReturnValue(true),
      mkdirSync: vi.fn(),
    };
    const mgr = new InboxManager(governor, adapter, onNotify, storageDeps);
    await mgr.loadFromDisk("p1", "/tmp/project");
    expect(mgr.getAll()).toHaveLength(1);
    expect(writeFile).not.toHaveBeenCalled();
  });

  // ──────────────────────────────────────────────────────────────────────
  // Iterate 14.5 — `notBlocked` flag (setNotBlocked + roundtrip)
  // ──────────────────────────────────────────────────────────────────────

  it("setNotBlocked flips the flag and persists via rewrite", async () => {
    const onNotify = vi.fn();
    const governor = { getProcess: vi.fn() } as unknown as ProcessGovernor;
    const adapter = { sendStdin: vi.fn() } as unknown as ClaudeAdapter;
    const writeFile = vi.fn().mockResolvedValue(undefined);
    const storageDeps = {
      readFile: vi.fn().mockResolvedValue(""),
      appendFile: vi.fn().mockResolvedValue(undefined),
      writeFile,
      existsSync: vi.fn().mockReturnValue(false),
      mkdirSync: vi.fn(),
    };
    const mgr = new InboxManager(governor, adapter, onNotify, storageDeps);
    mgr.registerProject("p1", "/tmp/project");

    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: [{ question: "Which DB?" }],
      toolUseId: "toolu_notblocked",
    });
    writeFile.mockClear();

    const updated = await mgr.setNotBlocked("toolu_notblocked", true);
    expect(updated).toBeDefined();
    expect(updated!.notBlocked).toBe(true);
    // Rewrite triggered exactly once (persist path).
    expect(writeFile).toHaveBeenCalledTimes(1);
    // Rewritten line contains the notBlocked field.
    const writtenContent = (writeFile.mock.calls[0][1] as string).trim();
    const parsed = JSON.parse(writtenContent);
    expect(parsed.notBlocked).toBe(true);
  });

  it("setNotBlocked on missing item returns undefined (no throw)", async () => {
    const { mgr } = setup();
    const result = await mgr.setNotBlocked("toolu_does_not_exist", true);
    expect(result).toBeUndefined();
  });

  it("setNotBlocked is idempotent — already-flagged item does not rewrite", async () => {
    const onNotify = vi.fn();
    const governor = { getProcess: vi.fn() } as unknown as ProcessGovernor;
    const adapter = { sendStdin: vi.fn() } as unknown as ClaudeAdapter;
    const writeFile = vi.fn().mockResolvedValue(undefined);
    const storageDeps = {
      readFile: vi.fn().mockResolvedValue(""),
      appendFile: vi.fn().mockResolvedValue(undefined),
      writeFile,
      existsSync: vi.fn().mockReturnValue(false),
      mkdirSync: vi.fn(),
    };
    const mgr = new InboxManager(governor, adapter, onNotify, storageDeps);
    mgr.registerProject("p1", "/tmp/project");

    await mgr.addQuestion({
      projectId: "p1",
      taskId: "t1",
      parts: [{ question: "Q?" }],
      toolUseId: "toolu_idem",
    });
    await mgr.setNotBlocked("toolu_idem", true);
    writeFile.mockClear();
    await mgr.setNotBlocked("toolu_idem", true);
    expect(writeFile).not.toHaveBeenCalled();
  });

  it("loadFromDisk round-trips the notBlocked field for v2 entries", async () => {
    const onNotify = vi.fn();
    const governor = { getProcess: vi.fn() } as unknown as ProcessGovernor;
    const adapter = { sendStdin: vi.fn() } as unknown as ClaudeAdapter;
    const persisted = {
      id: "toolu_roundtrip",
      projectId: "p1",
      taskId: "t1",
      parts: [{ question: "roundtrip?" }],
      status: "pending",
      createdAt: new Date().toISOString(),
      notBlocked: true,
    };
    const storageDeps = {
      readFile: vi.fn().mockResolvedValue(JSON.stringify(persisted) + "\n"),
      appendFile: vi.fn().mockResolvedValue(undefined),
      writeFile: vi.fn().mockResolvedValue(undefined),
      existsSync: vi.fn().mockReturnValue(true),
      mkdirSync: vi.fn(),
    };
    const mgr = new InboxManager(governor, adapter, onNotify, storageDeps);
    await mgr.loadFromDisk("p1", "/tmp/project");
    const loaded = mgr.getById("toolu_roundtrip");
    expect(loaded).toBeDefined();
    expect(loaded!.notBlocked).toBe(true);
  });

  it("loadFromDisk multi-part v2 entries with all parts intact", async () => {
    const onNotify = vi.fn();
    const governor = { getProcess: vi.fn() } as unknown as ProcessGovernor;
    const adapter = { sendStdin: vi.fn() } as unknown as ClaudeAdapter;
    const item = {
      id: "toolu_multi",
      projectId: "p1",
      taskId: "t1",
      parts: [
        { question: "Q1?", header: "A" },
        { question: "Q2?", header: "B", options: ["x", "y"] },
      ],
      status: "pending",
      createdAt: new Date().toISOString(),
    };
    const storageDeps = {
      readFile: vi.fn().mockResolvedValue(JSON.stringify(item) + "\n"),
      appendFile: vi.fn().mockResolvedValue(undefined),
      writeFile: vi.fn().mockResolvedValue(undefined),
      existsSync: vi.fn().mockReturnValue(true),
      mkdirSync: vi.fn(),
    };
    const mgr = new InboxManager(governor, adapter, onNotify, storageDeps);
    await mgr.loadFromDisk("p1", "/tmp/project");
    const loaded = mgr.getAll();
    expect(loaded).toHaveLength(1);
    expect(loaded[0].parts).toHaveLength(2);
    expect(loaded[0].parts[1].options).toEqual(["x", "y"]);
  });
});
