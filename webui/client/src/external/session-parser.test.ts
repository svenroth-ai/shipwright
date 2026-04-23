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
  extractSkillBody,
  fileSnapshotBasenames,
  hasVisibleBubbleContent,
  isThinkingOnly,
  parseSessionJsonl,
  toolResults,
  toolUses,
  userText,
  type AssistantEvent,
  type FileSnapshotEvent,
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

describe("parseSessionJsonl — iterate-3 new variants (FR-03.50)", () => {
  it("parses system event as kind='system' with content + subtype", () => {
    const raw = {
      type: "system",
      sessionId: "s",
      subtype: "local_command",
      content: "<local-command-stdout>ok</local-command-stdout>",
    };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events[0].kind).toBe("system");
    if (r.events[0].kind === "system") {
      expect(r.events[0].text).toContain("ok");
      expect(r.events[0].subtype).toBe("local_command");
    }
  });

  it("parses custom-title event with customTitle field", () => {
    const raw = { type: "custom-title", sessionId: "s", customTitle: "Task Alpha" };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events[0].kind).toBe("custom-title");
    if (r.events[0].kind === "custom-title") {
      expect(r.events[0].title).toBe("Task Alpha");
    }
  });

  it("parses agent-name event with agentName field", () => {
    const raw = { type: "agent-name", sessionId: "s", agentName: "Claude Sonnet 4.6" };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events[0].kind).toBe("agent-name");
    if (r.events[0].kind === "agent-name") {
      expect(r.events[0].name).toBe("Claude Sonnet 4.6");
    }
  });

  it("parses permission-mode event with permissionMode field", () => {
    const raw = { type: "permission-mode", sessionId: "s", permissionMode: "acceptEdits" };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events[0].kind).toBe("permission-mode");
    if (r.events[0].kind === "permission-mode") {
      expect(r.events[0].mode).toBe("acceptEdits");
    }
  });

  it("still falls through invented future types to kind='unknown' (regression guard)", () => {
    const raw = { type: "plugin-hook-v2", sessionId: "s", whatever: 1 };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events[0].kind).toBe("unknown");
    if (r.events[0].kind === "unknown") {
      expect(r.events[0].originalType).toBe("plugin-hook-v2");
    }
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

// ── 2026-04-23 — iterate-20260423-chat-rendering-polish ──

describe("parseSessionJsonl — slash-command detection (AC-3)", () => {
  it("reclassifies user event with only <command-message>+<command-name> as slash-command", () => {
    const content =
      "<command-message>shipwright-compliance:compliance</command-message>\n" +
      "<command-name>/shipwright-compliance:compliance</command-name>";
    const line = JSON.stringify({
      type: "user",
      message: { role: "user", content },
    });
    const r = parseSessionJsonl(line);
    expect(r.events).toHaveLength(1);
    expect(r.events[0].kind).toBe("slash-command");
    if (r.events[0].kind === "slash-command") {
      expect(r.events[0].commandName).toBe("/shipwright-compliance:compliance");
    }
  });

  it("leaves mixed content (text + command tags) as plain user event", () => {
    const content =
      "Can you explain this <command-message>foo</command-message><command-name>/foo</command-name>";
    const line = JSON.stringify({
      type: "user",
      message: { role: "user", content },
    });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("user");
  });

  it("leaves command tags with mismatched names as plain user event", () => {
    const content =
      "<command-message>foo</command-message>\n<command-name>/bar</command-name>";
    const line = JSON.stringify({
      type: "user",
      message: { role: "user", content },
    });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("user");
  });

  it("leaves missing command-name tag as plain user event", () => {
    const content = "<command-message>foo</command-message>";
    const line = JSON.stringify({
      type: "user",
      message: { role: "user", content },
    });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("user");
  });

  it("tolerates leading/trailing whitespace around the paired tags", () => {
    const content =
      "  <command-message>shipwright-compliance:compliance</command-message>\n" +
      "<command-name>/shipwright-compliance:compliance</command-name>  ";
    const line = JSON.stringify({
      type: "user",
      message: { role: "user", content },
    });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("slash-command");
  });
});

describe("fileSnapshotBasenames — AC-4 basename extraction", () => {
  it("returns basenames stripped of full paths (no user-fs leak)", () => {
    const e: FileSnapshotEvent = {
      kind: "file-history-snapshot",
      snapshot: {
        trackedFileBackups: {
          "C:/Users/secret/project/src/app.ts": "backup1",
          "/home/sven/docs/spec.md": "backup2",
        },
      },
    };
    expect(fileSnapshotBasenames(e)).toEqual(["app.ts", "spec.md"]);
  });

  it("returns empty array for empty trackedFileBackups", () => {
    const e: FileSnapshotEvent = {
      kind: "file-history-snapshot",
      snapshot: { trackedFileBackups: {} },
    };
    expect(fileSnapshotBasenames(e)).toEqual([]);
  });

  it("returns empty array when snapshot is null or missing backups", () => {
    expect(
      fileSnapshotBasenames({ kind: "file-history-snapshot", snapshot: null }),
    ).toEqual([]);
    expect(
      fileSnapshotBasenames({ kind: "file-history-snapshot", snapshot: {} }),
    ).toEqual([]);
  });
});

describe("hasVisibleBubbleContent — AC-5 empty-assistant detection", () => {
  it("returns true for non-empty text block", () => {
    const e: AssistantEvent = {
      kind: "assistant",
      content: [{ type: "text", text: "Hello" }],
    };
    expect(hasVisibleBubbleContent(e)).toBe(true);
  });

  it("returns FALSE for tool_use-only turns — sibling ToolCards carry the content, no speech bubble", () => {
    // 2026-04-23 — post-review fix: the earlier definition returned true
    // here, which caused the empty-bubble-with-CLAUDE-header defect that
    // triggered this iterate. Tool-only turns now render ONLY their
    // sibling tool cards.
    const e: AssistantEvent = {
      kind: "assistant",
      content: [{ type: "tool_use", id: "t1", name: "Read", input: {} }],
    };
    expect(hasVisibleBubbleContent(e)).toBe(false);
  });

  it("returns TRUE for text + tool_use mix (the text warrants a bubble)", () => {
    const e: AssistantEvent = {
      kind: "assistant",
      content: [
        { type: "text", text: "Reading the file..." },
        { type: "tool_use", id: "t1", name: "Read", input: {} },
      ],
    };
    expect(hasVisibleBubbleContent(e)).toBe(true);
  });

  it("returns false for whitespace-only text (trim check)", () => {
    const e: AssistantEvent = {
      kind: "assistant",
      content: [{ type: "text", text: "   \n\n  " }],
    };
    expect(hasVisibleBubbleContent(e)).toBe(false);
  });

  it("returns false for empty content array", () => {
    expect(hasVisibleBubbleContent({ kind: "assistant", content: [] })).toBe(false);
  });

  it("returns false for thinking-only content (caller renders thinking-card)", () => {
    const e: AssistantEvent = {
      kind: "assistant",
      content: [{ type: "thinking", thinking: "reasoning..." }],
    };
    expect(hasVisibleBubbleContent(e)).toBe(false);
  });
});

// ── 2026-04-23 — iterate-20260423-chat-followups AC-3 ──

describe("parseSessionJsonl — skill-body detection (chat-followups AC-3)", () => {
  const skillBodySample =
    "Base directory for this skill: C:\\Users\\sven\\.claude\\plugins\\cache\\shipwright\\shipwright-compliance\\0.3.0\\skills\\compliance\n" +
    "\n" +
    "# Shipwright Compliance Skill\n" +
    "\n" +
    "Detective cross-artifact audit for consistency drift.\n" +
    "\n" +
    "## Status\n" +
    "Green.\n" +
    "...(a very long manual body with many more sections to pad past the 100-char minimum length guard)...";

  it("reclassifies a user event whose content matches the skill fingerprint as skill-body", () => {
    const line = JSON.stringify({
      type: "user",
      message: { role: "user", content: skillBodySample },
    });
    const r = parseSessionJsonl(line);
    expect(r.events).toHaveLength(1);
    expect(r.events[0].kind).toBe("skill-body");
    if (r.events[0].kind === "skill-body") {
      expect(r.events[0].skillName).toBe("Shipwright Compliance Skill");
    }
  });

  it("falls through to plain user when fingerprint present but no heading after the preamble", () => {
    const content =
      "Base directory for this skill: /some/path\n\nthis is a long user message that just happens to mention the fingerprint but has no markdown heading after it at all, padding past the 100-char minimum...";
    const line = JSON.stringify({ type: "user", message: { role: "user", content } });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("user");
  });

  it("leaves plain user content containing the literal phrase mid-message as user kind", () => {
    const content =
      "Hey, I was reading that Base directory for this skill: text and wanted to check something — how do we handle this case?";
    const line = JSON.stringify({ type: "user", message: { role: "user", content } });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("user");
  });

  it("normalizes CRLF line endings before fingerprint detection", () => {
    const crlfContent = skillBodySample.replace(/\n/g, "\r\n");
    const line = JSON.stringify({
      type: "user",
      message: { role: "user", content: crlfContent },
    });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("skill-body");
    if (r.events[0].kind === "skill-body") {
      expect(r.events[0].skillName).toBe("Shipwright Compliance Skill");
    }
  });

  it("strips leading whitespace and trailing punctuation from extracted skill name", () => {
    const content =
      "Base directory for this skill: /path\n\n   # My Skill Name  \n\n" +
      "Lorem ipsum dolor sit amet padding text so the content exceeds the length guard minimum.";
    const line = JSON.stringify({
      type: "user",
      message: { role: "user", content },
    });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("skill-body");
    if (r.events[0].kind === "skill-body") {
      expect(r.events[0].skillName).toBe("My Skill Name");
    }
  });

  it("short-circuits messages shorter than the length guard (100 chars)", () => {
    // A paranoid-short message that starts with the fingerprint but has no
    // plausible body. Should stay user so we don't misclassify.
    const content = "Base directory for this skill: /x\n\n# Hi";
    const line = JSON.stringify({ type: "user", message: { role: "user", content } });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("user");
  });

  it("emits skill-body with skillName when the heading is not the FIRST line after preamble (scans forward)", () => {
    // Real skill manuals may include a preamble blurb before the H1.
    const content =
      "Base directory for this skill: /skills/x\n\n" +
      "> Auto-generated preamble line.\n\n" +
      "# Example Skill\n\n" +
      "Body text long enough to exceed the 100-char length guard pads out the remainder of this sample.";
    const line = JSON.stringify({ type: "user", message: { role: "user", content } });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("skill-body");
    if (r.events[0].kind === "skill-body") {
      expect(r.events[0].skillName).toBe("Example Skill");
    }
  });
});

// ── 2026-04-23 — iterate-20260423-chat-livetest-2 AC-A / ADR-056 ──

describe("extractSkillBody — helper (ADR-056 AC-A)", () => {
  const skillSample =
    "Base directory for this skill: C:\\skills\\compliance\n" +
    "\n" +
    "# Shipwright Compliance Skill\n" +
    "\n" +
    "Detective cross-artifact audit for consistency drift.\n" +
    "\n" +
    "## Status\n" +
    "Green.\n" +
    "...(body continues, padding past 100 chars for length guard)...";

  it("returns skillName + body for a valid fingerprint", () => {
    const r = extractSkillBody(skillSample);
    expect(r).not.toBeNull();
    expect(r!.skillName).toBe("Shipwright Compliance Skill");
    // Body starts at the H1 line and keeps all subsequent content.
    expect(r!.body.startsWith("# Shipwright Compliance Skill")).toBe(true);
    expect(r!.body).toContain("## Status");
    expect(r!.body).toContain("Green.");
    // Preamble is NOT in the body (only from H1 onward).
    expect(r!.body).not.toContain("Base directory for this skill:");
  });

  it("preserves Markdown markers in the body (code blocks, tables)", () => {
    const content =
      "Base directory for this skill: /p\n" +
      "\n" +
      "# Skill With Code\n" +
      "\n" +
      "```js\n" +
      "const x = 1;\n" +
      "```\n" +
      "\n" +
      "Padding text to exceed the 100-char length guard minimum...";
    const r = extractSkillBody(content);
    expect(r).not.toBeNull();
    expect(r!.body).toContain("```js");
    expect(r!.body).toContain("const x = 1;");
  });

  it("normalizes CRLF line endings before fingerprint detection", () => {
    const crlf = skillSample.replace(/\n/g, "\r\n");
    const r = extractSkillBody(crlf);
    expect(r).not.toBeNull();
    expect(r!.skillName).toBe("Shipwright Compliance Skill");
    // body is LF-normalized (we split on \n after the CRLF→LF conversion)
    expect(r!.body).not.toContain("\r");
  });

  it("returns null for length < 100 (guards against false positives)", () => {
    const tooShort = "Base directory for this skill: /x\n\n# Hi";
    expect(extractSkillBody(tooShort)).toBeNull();
  });

  it("returns null when content doesn't start with fingerprint (mid-message mention)", () => {
    const mid =
      "Hey, I was reading that Base directory for this skill: text" +
      " and wanted to check something mid-message with enough padding to exceed the length guard.";
    expect(extractSkillBody(mid)).toBeNull();
  });

  it("returns null for non-string / non-array / empty content", () => {
    expect(extractSkillBody(null)).toBeNull();
    expect(extractSkillBody(42)).toBeNull();
    expect(extractSkillBody({ foo: "bar" })).toBeNull();
    expect(extractSkillBody([])).toBeNull();
  });

  it("unwraps array-of-blocks content (realistic Claude JSONL shape)", () => {
    // Real skill-loader events come as `[{type:"text", text:"..."}]` —
    // not as a plain string. Post-ship fix discovered during live-test
    // of ADR-056: extractSkillBody must handle both shapes, or SkillCard
    // never fires in production.
    const blockText = skillSample;
    const r = extractSkillBody([{ type: "text", text: blockText }]);
    expect(r).not.toBeNull();
    expect(r!.skillName).toBe("Shipwright Compliance Skill");
    expect(r!.body.startsWith("# Shipwright Compliance Skill")).toBe(true);
  });

  it("concatenates multiple text blocks when content is a multi-block array", () => {
    // Defensive: if the CLI ever emits the skill body across multiple
    // text blocks, concat them before matching. Single-block real shape
    // is the common case; multi-block is a forward-compat guard.
    const r = extractSkillBody([
      { type: "text", text: "Base directory for this skill: /p\n\n" },
      { type: "text", text: "# Skill\n\nPadding text long enough to exceed the 100-char length guard minimum for the skill fingerprint." },
    ]);
    expect(r).not.toBeNull();
    expect(r!.skillName).toBe("Skill");
  });

  it("skips ## sub-headings before the H1 and finds the real title (H1-only guard)", () => {
    const content =
      "Base directory for this skill: /x\n\n" +
      "## Not the title\n\n" +
      "# Real Skill Title\n\n" +
      "Body padding text to exceed the 100-char length guard minimum for the extractor.";
    const r = extractSkillBody(content);
    expect(r).not.toBeNull();
    expect(r!.skillName).toBe("Real Skill Title");
  });
});

describe("parseOne — skill-body kind populates body (ADR-056 AC-A)", () => {
  it("emits SkillBodyEvent with body captured from the H1 onward", () => {
    const content =
      "Base directory for this skill: /path\n" +
      "\n" +
      "# Example Skill\n" +
      "\n" +
      "Manual body long enough to exceed the fingerprint length guard — this keeps " +
      "the test from tripping the 100-char minimum guard accidentally.";
    const line = JSON.stringify({
      type: "user",
      message: { role: "user", content },
    });
    const r = parseSessionJsonl(line);
    expect(r.events[0].kind).toBe("skill-body");
    if (r.events[0].kind === "skill-body") {
      expect(r.events[0].skillName).toBe("Example Skill");
      expect(r.events[0].body).toBeDefined();
      expect(r.events[0].body!.startsWith("# Example Skill")).toBe(true);
    }
  });
});

describe("isThinkingOnly — AC-5 thinking-card classifier", () => {
  it("returns true when content is only thinking blocks", () => {
    const e: AssistantEvent = {
      kind: "assistant",
      content: [{ type: "thinking", thinking: "..." }],
    };
    expect(isThinkingOnly(e)).toBe(true);
  });

  it("returns false when any non-thinking block is present", () => {
    const e: AssistantEvent = {
      kind: "assistant",
      content: [
        { type: "thinking", thinking: "..." },
        { type: "text", text: "hi" },
      ],
    };
    expect(isThinkingOnly(e)).toBe(false);
  });

  it("returns false for empty content (not 'thinking-only', just empty)", () => {
    expect(isThinkingOnly({ kind: "assistant", content: [] })).toBe(false);
  });
});
