/*
 * BubbleTranscript unit coverage.
 *
 * Covers:
 *   - Layout fixtures: user (right), assistant (left), tool_use, tool_result,
 *     AskUserQuestion pending → resolved transition.
 *   - "Load older" pagination — state expands the visible window.
 *   - Virtualization toggle: ≥ 200 events renders the virtual list,
 *     < 200 renders the plain list.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BubbleTranscript } from "./BubbleTranscript";

const SYSTEM_VISIBILITY_KEY = "webui.transcript.showSystem";

function jsonl(events: object[]): string {
  return events.map((e) => JSON.stringify(e)).join("\n") + "\n";
}

describe("BubbleTranscript — bubble layout fixtures", () => {
  it("renders user content as a right-aligned bubble with role + timestamp", () => {
    const content = jsonl([
      {
        type: "user",
        timestamp: "2026-04-19T08:30:00.000Z",
        message: { content: "hi from user" },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    const bubble = screen.getByTestId("bubble-user");
    expect(bubble.textContent).toContain("user");
    expect(bubble.textContent).toContain("hi from user");
    // Right alignment via parent flex container.
    expect(bubble.className).toMatch(/justify-end/);
  });

  it("renders assistant text as a left-aligned bubble with markdown body", () => {
    const content = jsonl([
      {
        type: "assistant",
        timestamp: "2026-04-19T08:30:01.000Z",
        message: { content: [{ type: "text", text: "Hello **world**" }] },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    const bubble = screen.getByTestId("bubble-assistant");
    // R4 (iterate 3.7e-a): role label renders as "claude" (displayed as
    // "CLAUDE" via CSS uppercase) instead of "assistant". The testid on
    // the bubble wrapper is still `bubble-assistant` — renaming it would
    // break ~5 other tests that assert on the wrapper. Only the visible
    // role text flipped.
    expect(bubble.textContent).toContain("claude");
    expect(bubble.textContent).not.toContain("assistant");
    expect(bubble.querySelector("strong")?.textContent).toBe("world");
  });

  it("renders tool_use Bash as a sibling card under the assistant bubble", () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            { type: "text", text: "running" },
            { type: "tool_use", id: "tu_bash_1", name: "Bash", input: {} },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    const tu = screen.getByTestId("bubble-tool-use");
    expect(tu.textContent).toContain("tool_use");
    expect(tu.textContent).toContain("Bash");
    expect(tu.dataset.toolUseId).toBe("tu_bash_1");
  });

  it("renders tool_result as a left card with ANSI-stripped content", () => {
    const content = jsonl([
      {
        type: "user",
        message: {
          content: [
            {
              type: "tool_result",
              tool_use_id: "tu_x",
              content: "\u001b[31merror\u001b[0m line",
            },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    const block = screen.getByTestId("bubble-tool-result");
    expect(block.textContent).toContain("error line");
    expect(block.textContent).not.toMatch(/\u001b\[/);
  });

  it("renders AskUserQuestion as pending amber when no matching tool_result exists", () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            {
              type: "tool_use",
              id: "tu_q1",
              name: "AskUserQuestion",
              input: { parts: [{ question: "Pick a stack?", options: ["A", "B"] }] },
            },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    const pending = screen.getByTestId("askuser-pending");
    expect(pending.textContent).toContain("Pick a stack?");
    expect(pending.textContent).toContain("Answer in your terminal");
    expect(pending.dataset.toolUseId).toBe("tu_q1");
    expect(screen.queryByTestId("askuser-resolved")).toBeNull();
  });

  it("flips AskUserQuestion to resolved green when a matching tool_result appears", () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            {
              type: "tool_use",
              id: "tu_q1",
              name: "AskUserQuestion",
              input: { parts: [{ question: "Pick?", options: ["A"] }] },
            },
          ],
        },
      },
      {
        type: "user",
        message: {
          content: [{ type: "tool_result", tool_use_id: "tu_q1", content: "A" }],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    const resolved = screen.getByTestId("askuser-resolved");
    expect(resolved.textContent).toContain("Answered");
    expect(resolved.dataset.toolUseId).toBe("tu_q1");
    expect(screen.queryByTestId("askuser-pending")).toBeNull();
  });
});

describe("BubbleTranscript — pagination", () => {
  it('shows "Load older" only when total exceeds visible tail', async () => {
    // 3 events, tail of 2 → load-older button shows.
    const content = jsonl([
      { type: "user", message: { content: "a" } },
      { type: "user", message: { content: "b" } },
      { type: "user", message: { content: "c" } },
    ]);
    render(<BubbleTranscript content={content} initialTail={2} />);
    expect(screen.getByTestId("transcript-event-count").textContent).toMatch(/2 of 3/);
    const btn = screen.getByTestId("load-older-btn");
    await userEvent.click(btn);
    expect(screen.getByTestId("transcript-event-count").textContent).toMatch(/3 of 3/);
    expect(screen.queryByTestId("load-older-btn")).toBeNull();
  });

  it("hides Load older when total <= visible tail", () => {
    const content = jsonl([
      { type: "user", message: { content: "a" } },
      { type: "user", message: { content: "b" } },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.queryByTestId("load-older-btn")).toBeNull();
  });
});

describe("BubbleTranscript — virtualization toggle", () => {
  it("renders the plain list when fewer than 200 events", () => {
    const events = Array.from({ length: 50 }, (_, i) => ({
      type: "user",
      message: { content: `e${i}` },
    }));
    render(<BubbleTranscript content={jsonl(events)} />);
    expect(screen.getByTestId("bubble-list-plain")).toBeInTheDocument();
    expect(screen.queryByTestId("bubble-list-virtual")).toBeNull();
  });

  it("renders the virtual list when >= 200 events", () => {
    const events = Array.from({ length: 250 }, (_, i) => ({
      type: "user",
      message: { content: `e${i}` },
    }));
    render(<BubbleTranscript content={jsonl(events)} />);
    expect(screen.getByTestId("bubble-list-virtual")).toBeInTheDocument();
    expect(screen.queryByTestId("bubble-list-plain")).toBeNull();
  });
});

describe("BubbleTranscript — iterate-3 chip variants (FR-03.52)", () => {
  it("renders custom-title as a muted one-line chip (no card border)", () => {
    const content = jsonl([
      { type: "custom-title", customTitle: "Implement user auth" },
    ]);
    render(<BubbleTranscript content={content} />);
    const chip = screen.getByTestId("bubble-custom-title");
    expect(chip.textContent).toContain("Implement user auth");
  });

  it("renders agent-name as a muted one-line chip", () => {
    const content = jsonl([
      { type: "agent-name", agentName: "Claude Sonnet 4.6" },
    ]);
    render(<BubbleTranscript content={content} />);
    const chip = screen.getByTestId("bubble-agent-name");
    expect(chip.textContent).toContain("Claude Sonnet 4.6");
  });

  it("renders permission-mode as a muted one-line chip", () => {
    const content = jsonl([
      { type: "permission-mode", permissionMode: "acceptEdits" },
    ]);
    render(<BubbleTranscript content={content} />);
    const chip = screen.getByTestId("bubble-permission-mode");
    expect(chip.textContent).toContain("acceptEdits");
  });

  it("does NOT render these variants as unknown fallback", () => {
    const content = jsonl([
      { type: "custom-title", customTitle: "X" },
      { type: "agent-name", agentName: "Y" },
      { type: "permission-mode", permissionMode: "Z" },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.queryByTestId("bubble-unknown")).toBeNull();
  });
});

describe("BubbleTranscript — system visibility toggle (FR-03.51)", () => {
  beforeEach(() => {
    window.localStorage.removeItem(SYSTEM_VISIBILITY_KEY);
  });
  afterEach(() => {
    window.localStorage.removeItem(SYSTEM_VISIBILITY_KEY);
  });

  it("hides system events by default (localStorage key absent)", () => {
    const content = jsonl([
      { type: "system", subtype: "init", content: "cwd=/tmp" },
      { type: "user", message: { content: "hello" } },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.queryByTestId("bubble-system")).toBeNull();
    expect(screen.getByTestId("bubble-user")).toBeInTheDocument();
  });

  it("shows system events when localStorage key is 'true'", () => {
    window.localStorage.setItem(SYSTEM_VISIBILITY_KEY, "true");
    const content = jsonl([
      { type: "system", subtype: "init", content: "cwd=/tmp" },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.getByTestId("bubble-system")).toBeInTheDocument();
  });

  it("hides when localStorage key is explicitly 'false'", () => {
    window.localStorage.setItem(SYSTEM_VISIBILITY_KEY, "false");
    const content = jsonl([
      { type: "system", subtype: "init", content: "cwd=/tmp" },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.queryByTestId("bubble-system")).toBeNull();
  });

  it("toolbar toggle writes localStorage and re-renders to reveal system bubbles", async () => {
    const content = jsonl([
      { type: "system", subtype: "init", content: "cwd=/tmp" },
      { type: "user", message: { content: "hello" } },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.queryByTestId("bubble-system")).toBeNull();

    const toggle = screen.getByTestId("system-toggle");
    await userEvent.click(toggle);

    expect(window.localStorage.getItem(SYSTEM_VISIBILITY_KEY)).toBe("true");
    expect(screen.getByTestId("bubble-system")).toBeInTheDocument();
  });

  it("toggle state round-trips across unmount/remount", async () => {
    const content = jsonl([
      { type: "system", subtype: "init", content: "cwd=/tmp" },
    ]);
    const first = render(<BubbleTranscript content={content} />);
    await userEvent.click(screen.getByTestId("system-toggle"));
    expect(screen.getByTestId("bubble-system")).toBeInTheDocument();
    first.unmount();

    // Fresh mount should read localStorage and still show system events.
    render(<BubbleTranscript content={content} />);
    expect(screen.getByTestId("bubble-system")).toBeInTheDocument();
  });
});

describe("BubbleTranscript — attachment rendering (FR-03.53)", () => {
  it("renders filename + thumbnail when attachment payload provides them", () => {
    const content = jsonl([
      {
        type: "attachment",
        attachment: {
          filename: "login-mockup-final.png",
          thumbnailUrl: "data:image/png;base64,AAAA",
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    const bubble = screen.getByTestId("bubble-attachment");
    expect(bubble.textContent).toContain("login-mockup-final.png");
    const img = bubble.querySelector("img");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("src")).toBe("data:image/png;base64,AAAA");
  });

  it("falls back to generic chip when payload has no filename/thumbnail", () => {
    const content = jsonl([
      { type: "attachment", attachment: { someOtherField: 1 } },
    ]);
    render(<BubbleTranscript content={content} />);
    const bubble = screen.getByTestId("bubble-attachment");
    expect(bubble.textContent).toMatch(/attachment/i);
    expect(bubble.querySelector("img")).toBeNull();
  });
});

describe("BubbleTranscript — empty state", () => {
  it("renders the empty hint when there is no content", () => {
    render(<BubbleTranscript content="" />);
    expect(screen.getByTestId("transcript-empty")).toBeInTheDocument();
  });
});
