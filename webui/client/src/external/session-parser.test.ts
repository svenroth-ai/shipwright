/*
 * Parser hardening + safe-getter tests for sub-iterate 2.2a.
 *
 * Covers:
 *   - Torn-read at the trailing line is silent (typical mid-write race).
 *   - Malformed middle-line surfaces as an unknown stub (not silently lost).
 *   - askUserQuestionSummary tolerates missing parts / wrong shapes.
 *   - toolResults extracts string + structured-block content.
 *   - userText, assistantText, toolUses survive degenerate input.
 */

import { describe, it, expect } from "vitest";
import {
  askUserQuestionSummary,
  assistantText,
  parseSessionJsonl,
  toolResults,
  toolUses,
  userText,
} from "./session-parser";

describe("parseSessionJsonl — torn-read tolerance", () => {
  it("silently swallows an unterminated trailing partial JSON line", () => {
    const partial =
      JSON.stringify({ type: "user", message: { content: "ok" } }) + "\n" +
      '{"type":"assist'; // mid-write torn read at the tail
    const r = parseSessionJsonl(partial);
    expect(r.events).toHaveLength(1);
    expect(r.events[0].kind).toBe("user");
    // Torn-read is counted but not emitted as an event.
    expect(r.malformedLines).toBe(1);
  });

  it("surfaces a malformed middle-line as an unknown stub", () => {
    const content =
      JSON.stringify({ type: "user", message: { content: "first" } }) + "\n" +
      'NOT-JSON\n' +
      JSON.stringify({ type: "assistant", message: { content: [{ type: "text", text: "ok" }] } }) + "\n";
    const r = parseSessionJsonl(content);
    expect(r.events).toHaveLength(3);
    expect(r.events[0].kind).toBe("user");
    expect(r.events[1].kind).toBe("unknown");
    if (r.events[1].kind === "unknown") {
      expect(r.events[1].originalType).toBe("(unparseable)");
    }
    expect(r.events[2].kind).toBe("assistant");
    expect(r.malformedLines).toBe(1);
  });

  it("truncates the raw text snapshot of an oversized malformed line", () => {
    const huge = "x".repeat(2000);
    const content = `${huge}\n${JSON.stringify({ type: "user", message: { content: "after" } })}\n`;
    const r = parseSessionJsonl(content);
    expect(r.events[0].kind).toBe("unknown");
    if (r.events[0].kind === "unknown") {
      const raw = r.events[0].raw as { __rawLine?: string };
      expect(typeof raw.__rawLine).toBe("string");
      // Cap is 500 chars + ellipsis.
      expect(raw.__rawLine!.length).toBeLessThan(huge.length);
      expect(raw.__rawLine).toMatch(/…$/);
    }
  });

  it("handles empty content + whitespace-only content", () => {
    expect(parseSessionJsonl("").events).toEqual([]);
    expect(parseSessionJsonl("\n\n\n").events).toEqual([]);
  });
});

describe("askUserQuestionSummary — safe getter", () => {
  it("extracts question + options from canonical shape", () => {
    const out = askUserQuestionSummary({
      parts: [
        { question: "Pick a stack?", options: ["Supabase", "Firebase"] },
      ],
    });
    expect(out.question).toBe("Pick a stack?");
    expect(out.options).toEqual(["Supabase", "Firebase"]);
    expect(out.fallback).toBe(false);
  });

  it("falls back when input is null / undefined / wrong type", () => {
    for (const bad of [null, undefined, 42, "string", true, { something: 1 }]) {
      const out = askUserQuestionSummary(bad);
      expect(out.fallback).toBe(true);
      expect(out.question).toBe("Question format unreadable");
      expect(out.options).toEqual([]);
    }
  });

  it("falls back when parts is empty / missing", () => {
    expect(askUserQuestionSummary({ parts: [] }).fallback).toBe(true);
    expect(askUserQuestionSummary({}).fallback).toBe(true);
    expect(askUserQuestionSummary({ parts: [null] }).fallback).toBe(true);
  });

  it("falls back when first part has no string question", () => {
    expect(askUserQuestionSummary({ parts: [{ question: 42 }] }).fallback).toBe(true);
    expect(askUserQuestionSummary({ parts: [{}] }).fallback).toBe(true);
  });

  it("filters non-string entries out of the options array", () => {
    const out = askUserQuestionSummary({
      parts: [{ question: "?", options: ["a", 42, null, "b"] }],
    });
    expect(out.options).toEqual(["a", "b"]);
    expect(out.fallback).toBe(false);
  });
});

describe("toolResults — extraction", () => {
  it("returns empty array for non-array content", () => {
    expect(toolResults({ kind: "user", content: "string" })).toEqual([]);
    expect(toolResults({ kind: "user", content: null as unknown })).toEqual([]);
  });

  it("extracts a tool_result block with string content", () => {
    const out = toolResults({
      kind: "user",
      content: [{ type: "tool_result", tool_use_id: "tu_1", content: "ok output" }],
    });
    expect(out).toEqual([{ tool_use_id: "tu_1", content: "ok output", is_error: false }]);
  });

  it("flags is_error=true when tagged", () => {
    const out = toolResults({
      kind: "user",
      content: [{ type: "tool_result", tool_use_id: "tu_1", content: "bad", is_error: true }],
    });
    expect(out[0].is_error).toBe(true);
  });

  it("collects text blocks when content is an array of blocks", () => {
    const out = toolResults({
      kind: "user",
      content: [
        {
          type: "tool_result",
          tool_use_id: "tu_1",
          content: [
            { type: "text", text: "line 1" },
            { type: "text", text: "line 2" },
          ],
        },
      ],
    });
    expect(out[0].content).toBe("line 1\nline 2");
  });
});

describe("userText — degenerate input handling", () => {
  it("returns empty string for null / undefined / number / object content", () => {
    expect(userText({ kind: "user", content: null as unknown })).toBe("");
    expect(userText({ kind: "user", content: undefined as unknown })).toBe("");
    expect(userText({ kind: "user", content: 42 as unknown })).toBe("");
    expect(userText({ kind: "user", content: { foo: "bar" } as unknown })).toBe("");
  });
});

describe("assistantText / toolUses — degenerate input handling", () => {
  it("survives non-array assistant content", () => {
    expect(assistantText({ kind: "assistant", content: "plain string" })).toBe("plain string");
    expect(assistantText({ kind: "assistant", content: null as unknown })).toBe("");
    expect(toolUses({ kind: "assistant", content: null as unknown })).toEqual([]);
  });

  it("ignores blocks missing required id / name", () => {
    const out = toolUses({
      kind: "assistant",
      content: [
        { type: "tool_use", id: "ok", name: "Bash", input: {} },
        { type: "tool_use", name: "missing-id" },
        { type: "tool_use", id: "missing-name" },
      ],
    });
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe("ok");
  });
});
