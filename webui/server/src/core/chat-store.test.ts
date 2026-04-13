import { describe, it, expect, vi } from "vitest";
import { ChatStore } from "./chat-store.js";
import type { ChatStoreDeps } from "./chat-store.js";
import type { ChatMessage } from "../../../client/src/types/chat.js";

function mockDeps(): ChatStoreDeps & { storage: Record<string, string> } {
  const storage: Record<string, string> = {};
  return {
    storage,
    readFile: vi.fn(async (path: string) => storage[path] ?? ""),
    appendFile: vi.fn(async (path: string, data: string) => {
      storage[path] = (storage[path] ?? "") + data;
    }),
    existsSync: vi.fn((path: string) => path in storage),
    mkdirSync: vi.fn(),
  };
}

const msg1: ChatMessage = {
  id: "m1",
  taskId: "t1",
  type: "assistant",
  content: "Hello",
  timestamp: "2026-01-01T00:00:00Z",
};

const msg2: ChatMessage = {
  id: "m2",
  taskId: "t1",
  type: "user",
  content: "Hi",
  timestamp: "2026-01-01T00:01:00Z",
};

describe("ChatStore", () => {
  it("append creates directory and writes JSON line", async () => {
    const deps = mockDeps();
    const store = new ChatStore(deps);
    await store.append("/proj", "t1", msg1);
    expect(deps.mkdirSync).toHaveBeenCalled();
    expect(deps.appendFile).toHaveBeenCalled();
  });

  it("append does not overwrite existing content", async () => {
    const deps = mockDeps();
    const store = new ChatStore(deps);
    await store.append("/proj", "t1", msg1);
    await store.append("/proj", "t1", msg2);
    const path = "/proj/.shipwright-webui/chat-history/t1.jsonl";
    const lines = deps.storage[path].trim().split("\n");
    expect(lines).toHaveLength(2);
  });

  it("load reads and parses messages sorted by timestamp", async () => {
    const deps = mockDeps();
    const path = "/proj/.shipwright-webui/chat-history/t1.jsonl";
    deps.storage[path] = [JSON.stringify(msg2), JSON.stringify(msg1)].join("\n") + "\n";
    const store = new ChatStore(deps);
    const messages = await store.load("/proj", "t1");
    expect(messages).toHaveLength(2);
    expect(messages[0].id).toBe("m1"); // earlier timestamp first
  });

  it("load on missing file returns empty array", async () => {
    const deps = mockDeps();
    const store = new ChatStore(deps);
    expect(await store.load("/proj", "t1")).toEqual([]);
  });

  it("load skips corrupt lines", async () => {
    const deps = mockDeps();
    const path = "/proj/.shipwright-webui/chat-history/t1.jsonl";
    deps.storage[path] = [JSON.stringify(msg1), "CORRUPT", JSON.stringify(msg2)].join("\n");
    const store = new ChatStore(deps);
    const messages = await store.load("/proj", "t1");
    expect(messages).toHaveLength(2);
  });

  it("exists returns correct boolean", () => {
    const deps = mockDeps();
    deps.storage["/proj/.shipwright-webui/chat-history/t1.jsonl"] = "data";
    const store = new ChatStore(deps);
    expect(store.exists("/proj", "t1")).toBe(true);
    expect(store.exists("/proj", "t2")).toBe(false);
  });

  it("migrates legacy JSON-blob assistant messages on load", async () => {
    const deps = mockDeps();
    const path = "/proj/.shipwright-webui/chat-history/t1.jsonl";
    const legacyMsg: ChatMessage = {
      id: "old-1",
      taskId: "t1",
      type: "assistant",
      content: JSON.stringify({
        model: "claude-opus-4-5-20251101",
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: "I'll create the file." },
          { type: "tool_use", id: "toolu_123", name: "Write", input: { file_path: "/test.txt", content: "Hello" } },
        ],
      }),
      timestamp: "2026-01-01T00:00:00Z",
    };
    deps.storage[path] = JSON.stringify(legacyMsg) + "\n";
    const store = new ChatStore(deps);
    const messages = await store.load("/proj", "t1");
    expect(messages).toHaveLength(2);
    expect(messages[0].type).toBe("assistant");
    expect(messages[0].content).toBe("I'll create the file.");
    expect(messages[0].model).toBe("claude-opus-4-5-20251101");
    expect(messages[1].type).toBe("tool_use");
    expect(messages[1].toolName).toBe("Write");
    expect(messages[1].toolInput).toEqual({ file_path: "/test.txt", content: "Hello" });
  });

  // Regression: chat-store must reject exact-duplicate appends within a short
  // time window. Claude CLI's stream-json has occasionally been observed
  // emitting near-identical tool_use events seconds apart (see ADR-016). The
  // parser now drops content_block_* events that were one source of dupes,
  // but this defense in depth also catches future quirks.
  it("append skips an exact structural duplicate within the dedupe window", async () => {
    const deps = mockDeps();
    const store = new ChatStore(deps);
    await store.append("/proj", "t1", msg1);
    await store.append("/proj", "t1", { ...msg1, id: "different-id" }); // same content/type, new id
    const path = "/proj/.shipwright-webui/chat-history/t1.jsonl";
    const lines = deps.storage[path].trim().split("\n");
    expect(lines).toHaveLength(1);
  });

  it("append keeps a message that differs only in content (not a dup)", async () => {
    const deps = mockDeps();
    const store = new ChatStore(deps);
    await store.append("/proj", "t1", msg1);
    await store.append("/proj", "t1", { ...msg1, id: "m1b", content: "Hello!" });
    const path = "/proj/.shipwright-webui/chat-history/t1.jsonl";
    const lines = deps.storage[path].trim().split("\n");
    expect(lines).toHaveLength(2);
  });

  it("append dedupes tool_use with identical toolName+toolInput", async () => {
    const deps = mockDeps();
    const store = new ChatStore(deps);
    const toolMsg: ChatMessage = {
      id: "tu1",
      taskId: "t1",
      type: "tool_use",
      content: "",
      toolName: "AskUserQuestion",
      toolInput: { questions: [{ question: "pick one", options: ["a", "b"] }] },
      timestamp: "2026-01-01T00:00:00Z",
    };
    await store.append("/proj", "t1", toolMsg);
    await store.append("/proj", "t1", { ...toolMsg, id: "tu2" });
    const path = "/proj/.shipwright-webui/chat-history/t1.jsonl";
    const lines = deps.storage[path].trim().split("\n");
    expect(lines).toHaveLength(1);
  });

  it("append keeps tool_use entries that differ by toolInput suffix (Claude refinement)", async () => {
    const deps = mockDeps();
    const store = new ChatStore(deps);
    const toolMsg1: ChatMessage = {
      id: "tu1",
      taskId: "t1",
      type: "tool_use",
      content: "",
      toolName: "AskUserQuestion",
      toolInput: { questions: [{ options: ["todoappdemo/planning"] }] },
      timestamp: "2026-01-01T00:00:00Z",
    };
    const toolMsg2 = {
      ...toolMsg1,
      id: "tu2",
      toolInput: { questions: [{ options: ["todoappdemo/planning (Recommended)"] }] },
    };
    await store.append("/proj", "t1", toolMsg1);
    await store.append("/proj", "t1", toolMsg2);
    const path = "/proj/.shipwright-webui/chat-history/t1.jsonl";
    const lines = deps.storage[path].trim().split("\n");
    // Different content → both kept. (Bug A parser fix is what prevents the
    // partial-from-content_block version from even reaching the store; this
    // test documents that IF two non-identical variants do reach us, we
    // don't conflate them.)
    expect(lines).toHaveLength(2);
  });

  it("does not migrate non-JSON assistant content", async () => {
    const deps = mockDeps();
    const path = "/proj/.shipwright-webui/chat-history/t1.jsonl";
    const normalMsg: ChatMessage = {
      id: "new-1",
      taskId: "t1",
      type: "assistant",
      content: "This is plain text",
      timestamp: "2026-01-01T00:00:00Z",
    };
    deps.storage[path] = JSON.stringify(normalMsg) + "\n";
    const store = new ChatStore(deps);
    const messages = await store.load("/proj", "t1");
    expect(messages).toHaveLength(1);
    expect(messages[0].content).toBe("This is plain text");
  });
});
