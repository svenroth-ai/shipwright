import { describe, it, expect, vi } from "vitest";
import { broadcastAndPersistChat } from "./chat-broadcast.js";
import type { ChatMessage, NdjsonMessage } from "../../../client/src/types/chat.js";
import type { SSEEvent } from "../../../client/src/types/sse.js";

function makeDeps() {
  const broadcast = vi.fn<[SSEEvent], void>();
  const append = vi.fn<[string, string, ChatMessage], Promise<void>>(() => Promise.resolve());
  return { deps: { sseManager: { broadcast }, chatStore: { append } }, broadcast, append };
}

const ndjson: NdjsonMessage = { type: "assistant", message: { content: [{ type: "text", text: "hi" }] } };

function chatMsg(id: string, type: ChatMessage["type"] = "assistant", content = ""): ChatMessage {
  return { id, taskId: "t1", type, content, timestamp: "2026-04-14T10:00:00.000Z" };
}

describe("broadcastAndPersistChat", () => {
  it("broadcasts one SSE event per extracted ChatMessage with matching id", () => {
    const { deps, broadcast, append } = makeDeps();
    const messages = [chatMsg("m-1", "assistant", "hi"), chatMsg("m-2", "tool_use"), chatMsg("m-3", "assistant", "bye")];

    broadcastAndPersistChat(
      { taskId: "t1", projectId: "p1", projectPath: "/tmp/p", msg: ndjson, chatMessages: messages },
      deps,
    );

    expect(broadcast).toHaveBeenCalledTimes(3);
    expect(append).toHaveBeenCalledTimes(3);

    for (let i = 0; i < 3; i++) {
      const event = broadcast.mock.calls[i]![0] as SSEEvent<{ taskId: string; projectId: string; message: ChatMessage }>;
      expect(event.type).toBe("chat:message");
      expect(event.payload.message.id).toBe(messages[i]!.id);
      expect(event.payload.message).toBe(messages[i]);
      expect(event.payload.taskId).toBe("t1");
      expect(event.timestamp).toBe(messages[i]!.timestamp);
    }
  });

  it("preserves broadcast order matching persistence order", () => {
    const { deps, broadcast, append } = makeDeps();
    const messages = [chatMsg("a"), chatMsg("b"), chatMsg("c")];

    broadcastAndPersistChat(
      { taskId: "t1", projectId: "p1", projectPath: "/tmp/p", msg: ndjson, chatMessages: messages },
      deps,
    );

    const broadcastIds = broadcast.mock.calls.map(
      (c) => (c[0] as SSEEvent<{ message: ChatMessage }>).payload.message.id,
    );
    const persistIds = append.mock.calls.map((c) => c[2].id);
    expect(broadcastIds).toEqual(["a", "b", "c"]);
    expect(persistIds).toEqual(["a", "b", "c"]);
  });

  it("does nothing when chatMessages is empty", () => {
    const { deps, broadcast, append } = makeDeps();
    broadcastAndPersistChat(
      { taskId: "t1", projectId: "p1", projectPath: "/tmp/p", msg: ndjson, chatMessages: [] },
      deps,
    );
    expect(broadcast).not.toHaveBeenCalled();
    expect(append).not.toHaveBeenCalled();
  });

  it("broadcasts but skips persistence when projectPath is undefined", () => {
    const { deps, broadcast, append } = makeDeps();
    broadcastAndPersistChat(
      { taskId: "t1", projectId: "p1", projectPath: undefined, msg: ndjson, chatMessages: [chatMsg("a")] },
      deps,
    );
    expect(broadcast).toHaveBeenCalledTimes(1);
    expect(append).not.toHaveBeenCalled();
  });
});
