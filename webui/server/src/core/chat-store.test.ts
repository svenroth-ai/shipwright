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
});
