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

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BubbleTranscript } from "./BubbleTranscript";

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
    expect(bubble.textContent).toContain("assistant");
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

describe("BubbleTranscript — empty state", () => {
  it("renders the empty hint when there is no content", () => {
    render(<BubbleTranscript content="" />);
    expect(screen.getByTestId("transcript-empty")).toBeInTheDocument();
  });
});
