import { describe, it, expect } from "vitest";
import { parseNdjsonLine, isAskUserQuestion, extractContentBlocks } from "./ndjson-parser.js";

describe("parseNdjsonLine", () => {
  it("parses valid assistant message", () => {
    const msg = parseNdjsonLine(JSON.stringify({ type: "assistant", content: "Hello" }));
    expect(msg).not.toBeNull();
    expect(msg!.type).toBe("assistant");
  });

  it("returns null for malformed JSON", () => {
    expect(parseNdjsonLine("NOT JSON")).toBeNull();
  });

  it("returns null for empty line", () => {
    expect(parseNdjsonLine("")).toBeNull();
    expect(parseNdjsonLine("   ")).toBeNull();
  });

  it("returns null for JSON without type field", () => {
    expect(parseNdjsonLine(JSON.stringify({ content: "hello" }))).toBeNull();
  });

  it("parses 1000 lines in under 50ms", () => {
    const line = JSON.stringify({ type: "assistant", content: "x" });
    const start = Date.now();
    for (let i = 0; i < 1000; i++) parseNdjsonLine(line);
    expect(Date.now() - start).toBeLessThan(50);
  });
});

describe("isAskUserQuestion", () => {
  it("returns true for tool_use with AskUserQuestion", () => {
    expect(isAskUserQuestion({ type: "tool_use", tool_name: "AskUserQuestion" })).toBe(true);
  });

  it("returns false for tool_use with different name", () => {
    expect(isAskUserQuestion({ type: "tool_use", tool_name: "Bash" })).toBe(false);
  });

  it("returns false for non-tool_use type", () => {
    expect(isAskUserQuestion({ type: "assistant", content: "hello" })).toBe(false);
  });
});

describe("extractContentBlocks", () => {
  // Real Claude CLI format: { type: "assistant", message: { model, content: [...] } }
  it("extracts text from real Claude CLI assistant message", () => {
    const msgs = extractContentBlocks("t1", {
      type: "assistant",
      message: {
        model: "claude-opus-4-5-20251101",
        type: "message",
        role: "assistant",
        content: [{ type: "text", text: "I'll create the file." }],
      },
    });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].type).toBe("assistant");
    expect(msgs[0].content).toBe("I'll create the file.");
    expect(msgs[0].model).toBe("claude-opus-4-5-20251101");
  });

  it("extracts tool_use from real Claude CLI assistant message", () => {
    const msgs = extractContentBlocks("t1", {
      type: "assistant",
      message: {
        model: "claude-opus-4-5-20251101",
        type: "message",
        role: "assistant",
        content: [{
          type: "tool_use",
          id: "toolu_123",
          name: "Write",
          input: { file_path: "/hello.txt", content: "Hello" },
        }],
      },
    });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].type).toBe("tool_use");
    expect(msgs[0].toolName).toBe("Write");
    expect(msgs[0].toolInput).toEqual({ file_path: "/hello.txt", content: "Hello" });
    expect(msgs[0].toolUseId).toBe("toolu_123");
  });

  it("extracts mixed content blocks (text + tool_use + thinking)", () => {
    const msgs = extractContentBlocks("t1", {
      type: "assistant",
      message: {
        model: "claude-opus-4-5-20251101",
        type: "message",
        content: [
          { type: "thinking", thinking: "Let me think..." },
          { type: "text", text: "I will read the file." },
          { type: "tool_use", name: "Read", input: { file_path: "/foo.ts" } },
        ],
      },
    });
    expect(msgs).toHaveLength(3);
    expect(msgs[0].type).toBe("thinking");
    expect(msgs[0].content).toBe("Let me think...");
    expect(msgs[1].type).toBe("assistant");
    expect(msgs[1].content).toBe("I will read the file.");
    expect(msgs[2].type).toBe("tool_use");
    expect(msgs[2].toolName).toBe("Read");
  });

  it("extracts simple assistant string message", () => {
    const msgs = extractContentBlocks("t1", { type: "assistant", message: "Hello world" });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].type).toBe("assistant");
    expect(msgs[0].content).toBe("Hello world");
  });

  it("handles message.content as plain string", () => {
    const msgs = extractContentBlocks("t1", {
      type: "assistant",
      message: { content: "nested text" },
    });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].content).toBe("nested text");
  });

  it("extracts tool_use event", () => {
    const msgs = extractContentBlocks("t1", {
      type: "tool_use",
      tool_name: "Bash",
      tool_input: { command: "ls" },
    });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].type).toBe("tool_use");
    expect(msgs[0].toolName).toBe("Bash");
    expect(msgs[0].toolInput).toEqual({ command: "ls" });
  });

  it("extracts tool_result event", () => {
    const msgs = extractContentBlocks("t1", {
      type: "tool_result",
      content: "file1.ts\nfile2.ts",
      tool_use_id: "toolu_abc",
    });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].type).toBe("tool_result");
    expect(msgs[0].content).toBe("file1.ts\nfile2.ts");
    expect(msgs[0].isError).toBeFalsy();
    expect(msgs[0].toolUseId).toBe("toolu_abc");
  });

  it("marks error tool_result with isError flag", () => {
    const msgs = extractContentBlocks("t1", {
      type: "tool_result",
      content: "Command failed",
      is_error: true,
    });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].isError).toBe(true);
  });

  it("extracts result event", () => {
    const msgs = extractContentBlocks("t1", {
      type: "result",
      result: "Task completed successfully",
    });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].type).toBe("result");
    expect(msgs[0].content).toBe("Task completed successfully");
  });

  it("extracts system/init event with model", () => {
    const msgs = extractContentBlocks("t1", {
      type: "system",
      message: "Session started",
      model: "claude-opus-4-6",
    });
    expect(msgs).toHaveLength(1);
    expect(msgs[0].type).toBe("system");
    expect(msgs[0].model).toBe("claude-opus-4-6");
  });

  it("returns empty array for unknown types", () => {
    const msgs = extractContentBlocks("t1", { type: "unknown_event" });
    expect(msgs).toHaveLength(0);
  });

  // Regression: content_block_start/delta must NOT produce ChatMessages.
  // Claude CLI's stream-json mode emits these events with partial state while
  // the tool_input JSON is being generated token-by-token, and then the full
  // `assistant` event with the complete content[] array. If both paths persist,
  // we get duplicate ChatMessages for the same logical tool call with
  // slightly-different content (the partial version vs the final version).
  // Only the `assistant` event should drive persistence.
  it("returns empty for content_block_start with a tool_use block (not persisted)", () => {
    const msgs = extractContentBlocks("t1", {
      type: "content_block_start",
      content_block: {
        type: "tool_use",
        name: "AskUserQuestion",
        input: { questions: [{ question: "partial" }] },
      },
    });
    expect(msgs).toHaveLength(0);
  });

  it("returns empty for content_block_delta with a text block (not persisted)", () => {
    const msgs = extractContentBlocks("t1", {
      type: "content_block_delta",
      content_block: { type: "text", text: "partial streaming token" },
    });
    expect(msgs).toHaveLength(0);
  });

  it("returns empty for content_block_start with a thinking block (not persisted)", () => {
    const msgs = extractContentBlocks("t1", {
      type: "content_block_start",
      content_block: { type: "thinking", thinking: "partial thought..." },
    });
    expect(msgs).toHaveLength(0);
  });

  it("returns empty for assistant with no message", () => {
    const msgs = extractContentBlocks("t1", { type: "assistant" });
    expect(msgs).toHaveLength(0);
  });

  it("generates unique IDs for each message", () => {
    const msgs = extractContentBlocks("t1", {
      type: "assistant",
      message: {
        content: [
          { type: "text", text: "a" },
          { type: "text", text: "b" },
        ],
      },
    });
    expect(msgs[0].id).not.toBe(msgs[1].id);
  });

  it("handles empty content array gracefully", () => {
    const msgs = extractContentBlocks("t1", {
      type: "assistant",
      message: { content: [] },
    });
    expect(msgs).toHaveLength(0);
  });
});
