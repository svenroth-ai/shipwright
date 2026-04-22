import { describe, it, expect } from "vitest";
import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  parseSessionJsonl,
  extractToolUses,
  extractToolResults,
} from "./session-parser.js";

const FIXTURE_DIR = path.resolve(__dirname, "../../src/test/fixtures/jsonl");

async function loadFixture(name: string): Promise<string> {
  return readFile(path.join(FIXTURE_DIR, name), "utf-8");
}

describe("session-parser — captured fixtures", () => {
  it("parses the plain Q+A fixture without malformed lines", async () => {
    const content = await loadFixture("01-plain-qa.session.jsonl");
    const r = parseSessionJsonl(content);
    expect(r.malformedLines).toBe(0);
    expect(r.events.length).toBeGreaterThan(0);
    const kinds = new Set(r.events.map((e) => e.kind));
    expect(kinds.has("user")).toBe(true);
    expect(kinds.has("assistant")).toBe(true);
  });

  it("parses the tool sequence fixture and surfaces assistant events", async () => {
    const content = await loadFixture("02-tool-read-bash.session.jsonl");
    const r = parseSessionJsonl(content);
    expect(r.malformedLines).toBe(0);
    const assistants = r.events.filter((e) => e.kind === "assistant");
    expect(assistants.length).toBeGreaterThanOrEqual(1);
  });

  it("parses the plan-mode fixture cleanly", async () => {
    const content = await loadFixture("03-plan-mode.session.jsonl");
    const r = parseSessionJsonl(content);
    expect(r.malformedLines).toBe(0);
  });

  it("parses the error-induction fixture without throwing", async () => {
    const content = await loadFixture("05-error-induction.session.jsonl");
    const r = parseSessionJsonl(content);
    expect(r.malformedLines).toBe(0);
  });
});

describe("session-parser — mutation corpus", () => {
  it("counts truncated final line as malformed, keeps prior events", () => {
    const jsonl =
      `{"type":"user","sessionId":"s","message":{"content":"hi"}}\n` +
      `{"type":"assistant","sessionId":"s","message"`;
    const r = parseSessionJsonl(jsonl);
    expect(r.malformedLines).toBe(1);
    expect(r.events.length).toBe(1);
    expect(r.events[0].kind).toBe("user");
  });

  it("tolerates duplicated lines", () => {
    const line = `{"type":"assistant","sessionId":"s","message":{"content":[{"type":"text","text":"ok"}]}}`;
    const r = parseSessionJsonl(`${line}\n${line}\n`);
    expect(r.events.length).toBe(2);
    expect(r.events.every((e) => e.kind === "assistant")).toBe(true);
  });

  it("falls through unknown top-level types with kind='unknown'", () => {
    const r = parseSessionJsonl(
      `{"type":"plugin_askuser_cool_feature","sessionId":"s","foo":"bar"}\n`,
    );
    expect(r.events.length).toBe(1);
    const ev = r.events[0];
    expect(ev.kind).toBe("unknown");
    if (ev.kind === "unknown") {
      expect(ev.originalType).toBe("plugin_askuser_cool_feature");
      expect(ev.raw.foo).toBe("bar");
    }
  });

  it("falls through missing-type lines with originalType '(no-type)'", () => {
    const r = parseSessionJsonl(`{"sessionId":"s","foo":"bar"}\n`);
    expect(r.events[0].kind).toBe("unknown");
    if (r.events[0].kind === "unknown") {
      expect(r.events[0].originalType).toBe("(no-type)");
    }
  });

  it("handles empty input without throwing", () => {
    const r = parseSessionJsonl("");
    expect(r.events).toEqual([]);
    expect(r.malformedLines).toBe(0);
  });

  it("handles malformed first line followed by valid data", () => {
    const jsonl =
      `not json at all\n` +
      `{"type":"user","sessionId":"s","message":{"content":"hi"}}\n`;
    const r = parseSessionJsonl(jsonl);
    expect(r.malformedLines).toBe(1);
    expect(r.events.length).toBe(1);
    expect(r.events[0].kind).toBe("user");
  });
});

describe("session-parser — iterate-3 new variants (FR-03.50)", () => {
  it("parses system event as kind='system' with content + subtype", () => {
    const raw = {
      type: "system",
      sessionId: "s",
      subtype: "local_command",
      content: "<local-command-stdout>Status dialog dismissed</local-command-stdout>",
      level: "info",
    };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events).toHaveLength(1);
    const ev = r.events[0];
    expect(ev.kind).toBe("system");
    if (ev.kind === "system") {
      expect(ev.text).toContain("Status dialog dismissed");
      expect(ev.subtype).toBe("local_command");
    }
  });

  it("parses custom-title event with customTitle field", () => {
    const raw = {
      type: "custom-title",
      sessionId: "s",
      customTitle: "shipwright-audit",
    };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events).toHaveLength(1);
    const ev = r.events[0];
    expect(ev.kind).toBe("custom-title");
    if (ev.kind === "custom-title") {
      expect(ev.title).toBe("shipwright-audit");
    }
  });

  it("parses agent-name event with agentName field", () => {
    const raw = {
      type: "agent-name",
      sessionId: "s",
      agentName: "Webui Title Alpha",
    };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events).toHaveLength(1);
    const ev = r.events[0];
    expect(ev.kind).toBe("agent-name");
    if (ev.kind === "agent-name") {
      expect(ev.name).toBe("Webui Title Alpha");
    }
  });

  it("parses permission-mode event with permissionMode field", () => {
    const raw = {
      type: "permission-mode",
      sessionId: "s",
      permissionMode: "acceptEdits",
    };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events).toHaveLength(1);
    const ev = r.events[0];
    expect(ev.kind).toBe("permission-mode");
    if (ev.kind === "permission-mode") {
      expect(ev.mode).toBe("acceptEdits");
    }
  });

  it("still falls through an invented future type to kind='unknown' (regression guard)", () => {
    const raw = {
      type: "plugin-hook-v2",
      sessionId: "s",
      whatever: { foo: "bar" },
    };
    const r = parseSessionJsonl(JSON.stringify(raw) + "\n");
    expect(r.events[0].kind).toBe("unknown");
    if (r.events[0].kind === "unknown") {
      expect(r.events[0].originalType).toBe("plugin-hook-v2");
    }
  });
});

describe("session-parser — tool use / result correlation", () => {
  it("extracts tool_use blocks from assistant content array", () => {
    const jsonl = JSON.stringify({
      type: "assistant",
      sessionId: "s",
      message: {
        content: [
          { type: "text", text: "Reading file" },
          { type: "tool_use", id: "t1", name: "Read", input: { path: "/etc/hosts" } },
        ],
      },
    });
    const r = parseSessionJsonl(jsonl + "\n");
    const uses = extractToolUses(r.events);
    expect(uses).toHaveLength(1);
    expect(uses[0].id).toBe("t1");
    expect(uses[0].name).toBe("Read");
  });

  it("extracts tool_result blocks from user content array", () => {
    const jsonl = JSON.stringify({
      type: "user",
      sessionId: "s",
      message: {
        content: [{ type: "tool_result", tool_use_id: "t1", content: "127.0.0.1 localhost" }],
      },
    });
    const r = parseSessionJsonl(jsonl + "\n");
    const res = extractToolResults(r.events);
    expect(res).toHaveLength(1);
    expect(res[0].toolUseId).toBe("t1");
  });
});
