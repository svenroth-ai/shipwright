import { describe, it, expect } from "vitest";

import { deriveInbox, DEFAULT_USER_BLOCKING_TOOLS } from "./inbox-derive.js";
import { parseSessionJsonl } from "./session-parser.js";

function build(events: unknown[]): string {
  return events.map((e) => JSON.stringify(e)).join("\n") + "\n";
}

function assistantWithToolUse(id: string, name: string): Record<string, unknown> {
  return {
    type: "assistant",
    sessionId: "s",
    message: {
      content: [
        { type: "text", text: "calling tool" },
        { type: "tool_use", id, name, input: { parts: [{ question: "ok?" }] } },
      ],
    },
  };
}

function userWithToolResult(toolUseId: string): Record<string, unknown> {
  return {
    type: "user",
    sessionId: "s",
    message: { content: [{ type: "tool_result", tool_use_id: toolUseId, content: "answer" }] },
  };
}

describe("deriveInbox — allowlist filter", () => {
  it("surfaces AskUserQuestion tool_use without tool_result", () => {
    const content = build([assistantWithToolUse("t1", "AskUserQuestion")]);
    const { events } = parseSessionJsonl(content);
    const r = deriveInbox({ events });
    expect(r.pending).toHaveLength(1);
    expect(r.pending[0].toolUseId).toBe("t1");
    expect(r.pending[0].toolName).toBe("AskUserQuestion");
  });

  it("clears pending entry once matching tool_result appears", () => {
    const content = build([
      assistantWithToolUse("t1", "AskUserQuestion"),
      userWithToolResult("t1"),
    ]);
    const { events } = parseSessionJsonl(content);
    const r = deriveInbox({ events });
    expect(r.pending).toHaveLength(0);
    expect(r.resolvedToolUseIds).toContain("t1");
  });

  it("ignores Bash tool_use (not user-blocking by default)", () => {
    const content = build([assistantWithToolUse("t1", "Bash")]);
    const { events } = parseSessionJsonl(content);
    const r = deriveInbox({ events });
    expect(r.pending).toHaveLength(0);
    expect(r.allToolUseIds).toContain("t1");
  });

  it("respects custom allowlist (plugin-registered tool names)", () => {
    const content = build([assistantWithToolUse("t1", "PluginAsk_MyProjectV1")]);
    const { events } = parseSessionJsonl(content);
    const r = deriveInbox({
      events,
      allowlist: new Set([...DEFAULT_USER_BLOCKING_TOOLS, "PluginAsk_MyProjectV1"]),
    });
    expect(r.pending).toHaveLength(1);
  });

  it("respects dismissed set — never surfaces dismissed ids", () => {
    const content = build([assistantWithToolUse("t1", "AskUserQuestion")]);
    const { events } = parseSessionJsonl(content);
    const r = deriveInbox({ events, dismissed: new Set(["t1"]) });
    expect(r.pending).toHaveLength(0);
  });

  it("surfaces multiple pending entries when present", () => {
    const content = build([
      assistantWithToolUse("t1", "AskUserQuestion"),
      assistantWithToolUse("t2", "AskUserQuestion"),
      userWithToolResult("t1"),
    ]);
    const { events } = parseSessionJsonl(content);
    const r = deriveInbox({ events });
    expect(r.pending).toHaveLength(1);
    expect(r.pending[0].toolUseId).toBe("t2");
  });
});
