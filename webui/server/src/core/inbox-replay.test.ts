import { describe, it, expect } from "vitest";
import { findOrphanAskUserQuestions } from "./inbox-replay.js";
import type { ChatMessage } from "../../../client/src/types/chat.js";

function makeMessage(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: "m1",
    taskId: "t1",
    type: "assistant",
    content: "",
    timestamp: "2026-04-13T00:00:00Z",
    ...overrides,
  } as ChatMessage;
}

function askUserQuestion(toolUseId: string, question = "Which option?"): ChatMessage {
  return makeMessage({
    id: `ask-${toolUseId}`,
    type: "tool_use",
    toolName: "AskUserQuestion",
    toolUseId,
    toolInput: {
      questions: [
        {
          question,
          options: [{ label: "Yes" }, { label: "No" }],
          multiSelect: false,
        },
      ],
    },
  });
}

function toolResult(toolUseId: string, content = "Yes"): ChatMessage {
  return makeMessage({
    id: `res-${toolUseId}`,
    type: "tool_result",
    toolUseId,
    content,
  });
}

describe("findOrphanAskUserQuestions", () => {
  it("returns orphan AskUserQuestion with toolUseId and extracted payload", () => {
    const orphans = findOrphanAskUserQuestions([askUserQuestion("toolu_1", "Pick?")]);
    expect(orphans).toHaveLength(1);
    expect(orphans[0].toolUseId).toBe("toolu_1");
    expect(orphans[0].question).toBe("Pick?");
    expect(orphans[0].options).toEqual(["Yes", "No"]);
    expect(orphans[0].taskId).toBe("t1");
  });

  it("skips AskUserQuestions that already have a matching tool_result", () => {
    const msgs = [askUserQuestion("toolu_1"), toolResult("toolu_1")];
    expect(findOrphanAskUserQuestions(msgs)).toEqual([]);
  });

  it("returns multiple orphans in chronological order", () => {
    const msgs = [
      askUserQuestion("toolu_1", "First?"),
      askUserQuestion("toolu_2", "Second?"),
    ];
    const orphans = findOrphanAskUserQuestions(msgs);
    expect(orphans).toHaveLength(2);
    expect(orphans[0].toolUseId).toBe("toolu_1");
    expect(orphans[1].toolUseId).toBe("toolu_2");
  });

  it("mixes orphan + answered: only the orphan is returned", () => {
    const msgs = [
      askUserQuestion("toolu_1", "Answered?"),
      toolResult("toolu_1"),
      askUserQuestion("toolu_2", "Still pending?"),
    ];
    const orphans = findOrphanAskUserQuestions(msgs);
    expect(orphans).toHaveLength(1);
    expect(orphans[0].toolUseId).toBe("toolu_2");
  });

  it("skips tool_use AskUserQuestion without toolUseId (legacy)", () => {
    const msg = makeMessage({
      type: "tool_use",
      toolName: "AskUserQuestion",
      toolInput: { questions: [{ question: "no id?" }] },
    });
    expect(findOrphanAskUserQuestions([msg])).toEqual([]);
  });

  it("ignores non-AskUserQuestion tool_use entries", () => {
    const msg = makeMessage({
      type: "tool_use",
      toolName: "Bash",
      toolUseId: "toolu_bash",
      toolInput: { command: "ls" },
    });
    expect(findOrphanAskUserQuestions([msg])).toEqual([]);
  });

  it("returns empty list when no messages", () => {
    expect(findOrphanAskUserQuestions([])).toEqual([]);
  });
});
