import { describe, it, expect } from "vitest";
import { parseNdjsonLine, isAskUserQuestion } from "./ndjson-parser.js";

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
