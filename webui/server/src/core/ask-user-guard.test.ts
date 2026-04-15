import { describe, it, expect } from "vitest";
import { classifyContentBlocks } from "./ask-user-guard.js";
import type { ChatMessage } from "../../../client/src/types/chat.js";

function mkMsg(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: overrides.id ?? "msg-" + Math.random(),
    taskId: overrides.taskId ?? "t1",
    type: overrides.type ?? "assistant",
    content: overrides.content ?? "",
    timestamp: overrides.timestamp ?? "2026-04-14T00:00:00Z",
    ...overrides,
  };
}

describe("ask-user-guard — classifyContentBlocks", () => {
  it("registers an AskUserQuestion tool_use", () => {
    const decision = classifyContentBlocks(
      [
        mkMsg({
          type: "tool_use",
          toolName: "AskUserQuestion",
          toolUseId: "toolu_01",
        }),
      ],
      new Set(),
    );
    expect(decision.register).toEqual(["toolu_01"]);
    expect(decision.flag).toEqual([]);
    expect(decision.turnEnded).toBe(false);
  });

  it("assistant text BEFORE AskUserQuestion in the same batch does NOT flag", () => {
    const decision = classifyContentBlocks(
      [
        mkMsg({ type: "assistant", content: "preamble text" }),
        mkMsg({
          type: "tool_use",
          toolName: "AskUserQuestion",
          toolUseId: "toolu_01",
        }),
      ],
      new Set(),
    );
    expect(decision.register).toEqual(["toolu_01"]);
    expect(decision.flag).toEqual([]);
  });

  it("assistant text AFTER AskUserQuestion in the same batch flags as continued", () => {
    const decision = classifyContentBlocks(
      [
        mkMsg({
          type: "tool_use",
          toolName: "AskUserQuestion",
          toolUseId: "toolu_01",
        }),
        mkMsg({ type: "assistant", content: "keeps talking" }),
      ],
      new Set(),
    );
    expect(decision.register).toEqual(["toolu_01"]);
    expect(decision.flag).toEqual([
      { toolUseId: "toolu_01", reason: "continued" },
    ]);
  });

  it("assistant text with AUQ already pending from previous batch flags", () => {
    const decision = classifyContentBlocks(
      [mkMsg({ type: "assistant", content: "still going" })],
      new Set(["toolu_prev"]),
    );
    expect(decision.flag).toEqual([
      { toolUseId: "toolu_prev", reason: "continued" },
    ]);
    expect(decision.register).toEqual([]);
  });

  it("non-AUQ tool_use after pending AUQ flags as continued", () => {
    const decision = classifyContentBlocks(
      [
        mkMsg({
          type: "tool_use",
          toolName: "Bash",
          toolUseId: "toolu_02",
        }),
      ],
      new Set(["toolu_01"]),
    );
    expect(decision.flag).toEqual([
      { toolUseId: "toolu_01", reason: "continued" },
    ]);
  });

  it("tool_result matching a pending AUQ removes it from pending (no flag)", () => {
    const decision = classifyContentBlocks(
      [mkMsg({ type: "tool_result", toolUseId: "toolu_01" })],
      new Set(["toolu_01"]),
    );
    expect(decision.resolve).toEqual(["toolu_01"]);
    expect(decision.flag).toEqual([]);
    expect(decision.turnEnded).toBe(false);
  });

  it("result event flags remaining pending ids with reason turn_ended", () => {
    const decision = classifyContentBlocks(
      [mkMsg({ type: "result", content: "done" })],
      new Set(["toolu_a", "toolu_b"]),
    );
    expect(decision.turnEnded).toBe(true);
    expect(decision.flag).toEqual(
      expect.arrayContaining([
        { toolUseId: "toolu_a", reason: "turn_ended" },
        { toolUseId: "toolu_b", reason: "turn_ended" },
      ]),
    );
    expect(decision.flag).toHaveLength(2);
  });

  it("result event with empty pending set only sets turnEnded", () => {
    const decision = classifyContentBlocks(
      [mkMsg({ type: "result", content: "done" })],
      new Set(),
    );
    expect(decision.flag).toEqual([]);
    expect(decision.turnEnded).toBe(true);
  });

  it("AUQ → tool_result in same batch answers cleanly without flagging", () => {
    const decision = classifyContentBlocks(
      [
        mkMsg({
          type: "tool_use",
          toolName: "AskUserQuestion",
          toolUseId: "toolu_99",
        }),
        mkMsg({ type: "tool_result", toolUseId: "toolu_99" }),
      ],
      new Set(),
    );
    expect(decision.register).toEqual(["toolu_99"]);
    expect(decision.resolve).toEqual(["toolu_99"]);
    expect(decision.flag).toEqual([]);
  });

  it("AUQ → tool_result for OTHER id leaves pending intact", () => {
    const decision = classifyContentBlocks(
      [
        mkMsg({
          type: "tool_use",
          toolName: "AskUserQuestion",
          toolUseId: "toolu_mine",
        }),
        mkMsg({ type: "tool_result", toolUseId: "toolu_different" }),
      ],
      new Set(),
    );
    expect(decision.register).toEqual(["toolu_mine"]);
    expect(decision.resolve).toEqual([]);
    expect(decision.flag).toEqual([]);
  });

  it("AUQ → assistant text → result in one batch produces continued AND turn_ended", () => {
    const decision = classifyContentBlocks(
      [
        mkMsg({
          type: "tool_use",
          toolName: "AskUserQuestion",
          toolUseId: "toolu_01",
        }),
        mkMsg({ type: "assistant", content: "here is what I think" }),
        mkMsg({ type: "result", content: "done" }),
      ],
      new Set(),
    );
    expect(decision.register).toEqual(["toolu_01"]);
    // Both flags fire — "continued" from the text block, "turn_ended"
    // from the final result event. `setNotBlocked` is idempotent so the
    // duplicate is a cheap no-op at the caller. This is defensive: if
    // the text block were misclassified we still catch the turn end.
    expect(decision.flag).toEqual([
      { toolUseId: "toolu_01", reason: "continued" },
      { toolUseId: "toolu_01", reason: "turn_ended" },
    ]);
    expect(decision.turnEnded).toBe(true);
  });

  it("input `pending` set is not mutated", () => {
    const original = new Set(["toolu_keep"]);
    classifyContentBlocks(
      [mkMsg({ type: "tool_result", toolUseId: "toolu_keep" })],
      original,
    );
    expect(original.has("toolu_keep")).toBe(true);
  });

  it("thinking block after AUQ also flags as continued", () => {
    const decision = classifyContentBlocks(
      [mkMsg({ type: "thinking", content: "..." })],
      new Set(["toolu_01"]),
    );
    expect(decision.flag).toEqual([
      { toolUseId: "toolu_01", reason: "continued" },
    ]);
  });

  it("user message type is ignored (no flag, no register, no turn end)", () => {
    const decision = classifyContentBlocks(
      [mkMsg({ type: "user", content: "hi" })],
      new Set(["toolu_01"]),
    );
    expect(decision.flag).toEqual([]);
    expect(decision.register).toEqual([]);
    expect(decision.turnEnded).toBe(false);
  });
});
