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
import { render, screen, within } from "@testing-library/react";
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
    // 2026-04-23 — iterate-20260423-chat-rendering-polish AC-1/AC-2:
    // tool_use now renders as ToolCard (collapsed by default) instead
    // of the simple "tool_use {name}" text chip. The card's title shows
    // the tool name; body is collapsed so no "tool_use" prose literal.
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
    expect(tu.dataset.toolUseId).toBe("tu_bash_1");
    // Tool name visible in the card title.
    const title = tu.querySelector('[data-testid="tool-card-title"]');
    expect(title?.textContent).toBe("Bash");
    // Card starts collapsed — body not in DOM.
    expect(tu.querySelector('[data-testid="tool-card-body"]')).toBeNull();
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
  // These chips are now treated as system-message noise and hidden by
  // default; the tests below opt-in via the system-visibility toggle.
  beforeEach(() => {
    window.localStorage.setItem(SYSTEM_VISIBILITY_KEY, "true");
  });
  afterEach(() => {
    window.localStorage.removeItem(SYSTEM_VISIBILITY_KEY);
  });

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

  it("hides custom-title / agent-name / permission-mode pills by default", () => {
    const content = jsonl([
      { type: "custom-title", customTitle: "Hidden by default" },
      { type: "agent-name", agentName: "Claude" },
      { type: "permission-mode", permissionMode: "auto" },
      { type: "user", message: { content: "visible" } },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.queryByTestId("bubble-custom-title")).toBeNull();
    expect(screen.queryByTestId("bubble-agent-name")).toBeNull();
    expect(screen.queryByTestId("bubble-permission-mode")).toBeNull();
    expect(screen.getByTestId("bubble-user")).toBeInTheDocument();
  });

  it("counts custom-title / agent-name / permission-mode in the toolbar systemCount", () => {
    const content = jsonl([
      { type: "system", subtype: "init", content: "cwd=/tmp" },
      { type: "custom-title", customTitle: "X" },
      { type: "agent-name", agentName: "Y" },
      { type: "permission-mode", permissionMode: "Z" },
    ]);
    render(<BubbleTranscript content={content} />);
    const toggle = screen.getByTestId("system-toggle");
    expect(toggle.getAttribute("data-system-count")).toBe("4");
    expect(toggle.textContent).toContain("(4)");
  });

  it("drops last-prompt events entirely (data-array filter, not toggle-gated)", () => {
    const content = jsonl([
      { type: "last-prompt", prompt: "internal context not for the chat" },
      { type: "user", message: { content: "real user message" } },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.queryByTestId("bubble-unknown")).toBeNull();
    expect(screen.getByTestId("bubble-user")).toBeInTheDocument();
    // Even with system visibility on, last-prompt stays hidden.
    window.localStorage.setItem(SYSTEM_VISIBILITY_KEY, "true");
    const second = jsonl([
      { type: "last-prompt", prompt: "still hidden" },
      { type: "user", message: { content: "msg" } },
    ]);
    const { container } = render(<BubbleTranscript content={second} />);
    expect(within(container).queryByTestId("bubble-unknown")).toBeNull();
  });

  it("toggling system visibility reveals all four pill kinds together", async () => {
    const content = jsonl([
      { type: "custom-title", customTitle: "T" },
      { type: "agent-name", agentName: "A" },
      { type: "permission-mode", permissionMode: "M" },
      { type: "system", subtype: "init", content: "S" },
    ]);
    render(<BubbleTranscript content={content} />);
    await userEvent.click(screen.getByTestId("system-toggle"));
    expect(screen.getByTestId("bubble-custom-title")).toBeInTheDocument();
    expect(screen.getByTestId("bubble-agent-name")).toBeInTheDocument();
    expect(screen.getByTestId("bubble-permission-mode")).toBeInTheDocument();
    expect(screen.getByTestId("bubble-system")).toBeInTheDocument();
  });
});

describe("BubbleTranscript — attachment rendering (FR-03.53)", () => {
  it("renders filename via AttachmentCard when attachment payload provides one", () => {
    // 2026-04-23 — iterate-20260423-chat-rendering-polish AC-4: the inline
    // thumbnail <img> was replaced with a lucide mime-icon. We assert on
    // the basename being visible via AttachmentCard's testid and on the
    // outer bubble wrapper still carrying its data-testid for back-compat.
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
    const card = bubble.querySelector('[data-testid="attachment-card"]');
    expect(card).not.toBeNull();
    const basename = bubble.querySelector('[data-testid="attachment-basename"]');
    expect(basename?.textContent).toBe("login-mockup-final.png");
  });

  it("suppresses attachment events with no filename (deferred_tools_delta / skill_listing noise)", () => {
    // 2026-04-23 — AC-4: Claude Code emits `attachment` events with
    // internal payloads (deferred_tools_delta, skill_listing, etc.) that
    // have no filename. These previously showed as a bare "attachment"
    // chip — now they render nothing, so the transcript stays clean.
    const content = jsonl([
      { type: "attachment", attachment: { someOtherField: 1 } },
    ]);
    render(<BubbleTranscript content={content} />);
    const bubble = screen.queryByTestId("attachment-card");
    expect(bubble).toBeNull();
  });
});

describe("BubbleTranscript — empty state", () => {
  it("renders the empty hint when there is no content", () => {
    render(<BubbleTranscript content="" />);
    expect(screen.getByTestId("transcript-empty")).toBeInTheDocument();
  });
});

// 2026-04-23 — iterate-20260423-chat-followups AC-1: fold tool_result into
// the matching ToolCard. The separate tool_result bubble is suppressed
// when every tool_use_id has a visible parent tool_use. Orphans and
// mixed-content events still render the existing bubble so data is
// never silently dropped.
describe("BubbleTranscript — AC-1 tool_result folding into ToolCard", () => {
  it("suppresses the separate tool_result bubble when every id has a visible tool_use", () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            { type: "tool_use", id: "tu_bash_1", name: "Bash", input: { command: "ls" } },
          ],
        },
      },
      {
        type: "user",
        message: {
          content: [{ type: "tool_result", tool_use_id: "tu_bash_1", content: "file1\nfile2" }],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    // Tool_use card renders, tool_result-only bubble is gone.
    expect(screen.getByTestId("bubble-tool-use")).toBeInTheDocument();
    expect(screen.queryByTestId("bubble-tool-result")).toBeNull();
  });

  it("still renders the bubble when content has MIXED text + tool_result (never drop data)", () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            { type: "tool_use", id: "tu_bash_2", name: "Bash", input: {} },
          ],
        },
      },
      {
        type: "user",
        message: {
          content: [
            { type: "text", text: "Context note from Claude's user message" },
            { type: "tool_result", tool_use_id: "tu_bash_2", content: "ok" },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    // Mixed content → bubble still visible so the text isn't lost.
    expect(screen.getByTestId("bubble-tool-result")).toBeInTheDocument();
  });

  it("still renders the bubble when the matching tool_use is not in the visible window (orphan)", () => {
    // tool_use "tu_old" is outside the initial tail of 2; the tool_result
    // arrives later so its parent is scrolled out → no ToolCard renders
    // → DON'T suppress, the user needs to see the output somewhere.
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            { type: "tool_use", id: "tu_old", name: "Bash", input: {} },
          ],
        },
      },
      { type: "user", message: { content: "distraction 1" } },
      { type: "user", message: { content: "distraction 2" } },
      {
        type: "user",
        message: {
          content: [{ type: "tool_result", tool_use_id: "tu_old", content: "orphan out" }],
        },
      },
    ]);
    render(<BubbleTranscript content={content} initialTail={2} />);
    // Only the two most recent events visible. Neither includes the
    // tool_use block, so the tool_result can't fold — the bubble must
    // render to expose the output.
    expect(screen.queryByTestId("bubble-tool-use")).toBeNull();
    const bubble = screen.getByTestId("bubble-tool-result");
    // Lock in the fold-from-full-scope contract: even though the tool_use
    // is outside the window, the orphan tool_result content (`orphan out`)
    // is still visible in the tool_result bubble, so data is never lost.
    expect(bubble.textContent).toContain("orphan out");
  });

  it("prefers non-error result when duplicate tool_result_ids stream in (error-then-success)", async () => {
    // tool_use arrives once; tool_result arrives twice (first as error,
    // then as success on retry). The ToolCard must surface the successful
    // outcome, not the stale failure.
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [{ type: "tool_use", id: "tu_retry", name: "Bash", input: {} }],
        },
      },
      {
        type: "user",
        message: {
          content: [
            {
              type: "tool_result",
              tool_use_id: "tu_retry",
              content: "transient failure",
              is_error: true,
            },
          ],
        },
      },
      {
        type: "user",
        message: {
          content: [
            {
              type: "tool_result",
              tool_use_id: "tu_retry",
              content: "final success",
              is_error: false,
            },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    await userEvent.click(screen.getByTestId("tool-card-header"));
    const output = screen.getByTestId("tool-card-output");
    // Non-error result wins over the earlier error.
    expect(output.textContent).toContain("final success");
    expect(output.textContent).not.toContain("transient failure");
    // And the output is NOT rendered with error styling.
    const errBlock = output.querySelector('[data-is-error="true"]');
    expect(errBlock).toBeNull();
  });

  it("keeps last-write-wins for two non-error results (streaming delta)", async () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [{ type: "tool_use", id: "tu_stream", name: "Bash", input: {} }],
        },
      },
      {
        type: "user",
        message: {
          content: [
            { type: "tool_result", tool_use_id: "tu_stream", content: "partial" },
          ],
        },
      },
      {
        type: "user",
        message: {
          content: [
            { type: "tool_result", tool_use_id: "tu_stream", content: "complete" },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    await userEvent.click(screen.getByTestId("tool-card-header"));
    const output = screen.getByTestId("tool-card-output");
    expect(output.textContent).toContain("complete");
    expect(output.textContent).not.toContain("partial");
  });

  it("reflects the full-filtered (not windowed) scope when fold targets span the tail boundary", () => {
    // Window = 2; total events = 5. The tool_use + its tool_result both
    // sit inside the visible window (positions 3 + 4 of 5), BUT the first
    // event (unrelated assistant text) is outside. This checks that the
    // toolResultsById map build uses the full filtered scope rather than
    // the narrower visible slice — if it narrowed, this case would still
    // fold correctly, but a sibling regression (tool_use in window,
    // tool_result OLDER than the window) would break. We cover that
    // shape directly in the 'orphan' test above; this is the
    // corresponding fold-INSIDE-window smoke.
    const content = jsonl([
      { type: "assistant", message: { content: [{ type: "text", text: "scroll-out" }] } },
      { type: "assistant", message: { content: [{ type: "text", text: "scroll-out 2" }] } },
      { type: "assistant", message: { content: [{ type: "text", text: "scroll-out 3" }] } },
      {
        type: "assistant",
        message: {
          content: [{ type: "tool_use", id: "tu_inside", name: "Bash", input: {} }],
        },
      },
      {
        type: "user",
        message: {
          content: [{ type: "tool_result", tool_use_id: "tu_inside", content: "inside output" }],
        },
      },
    ]);
    render(<BubbleTranscript content={content} initialTail={2} />);
    // Visible = last 2 events (tool_use + tool_result). The tool_result
    // bubble is suppressed (fold success); the ToolCard carries the
    // output when expanded.
    expect(screen.queryByTestId("bubble-tool-result")).toBeNull();
    expect(screen.getByTestId("bubble-tool-use")).toBeInTheDocument();
  });

  it("passes the tool_result content into the ToolCard output (expand shows it)", async () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            { type: "tool_use", id: "tu_read_1", name: "Read", input: { file_path: "/a" } },
          ],
        },
      },
      {
        type: "user",
        message: {
          content: [{ type: "tool_result", tool_use_id: "tu_read_1", content: "contents of a" }],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    // Expand the tool card to reveal the folded output.
    await userEvent.click(screen.getByTestId("tool-card-header"));
    const output = screen.getByTestId("tool-card-output");
    expect(output.textContent).toContain("contents of a");
  });
});

// 2026-04-23 — ADR-056 AC-D: TodoWrite tool_use dispatches to the
// specialized TodoWriteCard renderer; non-TodoWrite tools still render
// through the generic ToolCard path (regression guard).
describe("BubbleTranscript — ADR-056 AC-D TodoWrite dispatch", () => {
  it("renders TodoWrite tool_use as TodoWriteCard (not generic ToolCard)", () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            {
              type: "tool_use",
              id: "tu_todos",
              name: "TodoWrite",
              input: {
                todos: [
                  { content: "Task one", status: "completed" },
                  { content: "Task two", status: "in_progress", activeForm: "Working on two" },
                  { content: "Task three", status: "pending" },
                ],
              },
            },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    // ADR-057: TodoWriteCard now uses the shared TaskListCardShell; outer
    // testid is still `todo-write-card` for back-compat but inner items
    // use the `task-list-card-*` prefix.
    expect(screen.getByTestId("todo-write-card")).toBeInTheDocument();
    expect(screen.queryByTestId("tool-card")).toBeNull();
    expect(screen.getByTestId("task-list-card-progress").textContent).toBe("1/3");
    expect(screen.getAllByTestId("task-list-card-item")).toHaveLength(3);
  });

  it("renders TaskCreate tool_use as TaskListCard with aggregated state (ADR-057)", () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            {
              type: "tool_use",
              id: "tu_create_1",
              name: "TaskCreate",
              input: { subject: "First task", activeForm: "Doing first" },
            },
          ],
        },
      },
      {
        type: "assistant",
        message: {
          content: [
            {
              type: "tool_use",
              id: "tu_create_2",
              name: "TaskCreate",
              input: { subject: "Second task", activeForm: "Doing second" },
            },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    // Two separate TaskListCard cards — one snapshot per TaskCreate.
    const cards = screen.getAllByTestId("task-list-card");
    expect(cards).toHaveLength(2);
    // First card: 1 task pending.
    expect(within(cards[0]).getByTestId("task-list-card-progress").textContent).toBe("0/1");
    // Second card: 2 tasks pending (cumulative).
    expect(within(cards[1]).getByTestId("task-list-card-progress").textContent).toBe("0/2");
  });

  it("renders TaskUpdate with accumulated status flips at each event (ADR-057)", () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            { type: "tool_use", id: "tu1", name: "TaskCreate", input: { subject: "First" } },
            { type: "tool_use", id: "tu2", name: "TaskCreate", input: { subject: "Second" } },
          ],
        },
      },
      {
        type: "assistant",
        message: {
          content: [
            {
              type: "tool_use",
              id: "tu3",
              name: "TaskUpdate",
              input: { taskId: "1", status: "in_progress" },
            },
          ],
        },
      },
      {
        type: "assistant",
        message: {
          content: [
            {
              type: "tool_use",
              id: "tu4",
              name: "TaskUpdate",
              input: { taskId: "1", status: "completed" },
            },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    const cards = screen.getAllByTestId("task-list-card");
    // 4 task-related tool_uses → 4 snapshot cards.
    expect(cards).toHaveLength(4);
    // Last card reflects task 1 completed + task 2 pending.
    const lastCard = cards[cards.length - 1];
    expect(within(lastCard).getByTestId("task-list-card-progress").textContent).toBe("1/2");
    const rows = within(lastCard).getAllByTestId("task-list-card-item");
    expect(rows[0].dataset.status).toBe("completed");
    expect(rows[1].dataset.status).toBe("pending");
  });

  it("still routes non-TodoWrite tool_use through the generic ToolCard (regression)", () => {
    const content = jsonl([
      {
        type: "assistant",
        message: {
          content: [
            { type: "tool_use", id: "tu_bash", name: "Bash", input: { command: "ls" } },
          ],
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.getByTestId("tool-card")).toBeInTheDocument();
    expect(screen.queryByTestId("todo-write-card")).toBeNull();
  });
});

// 2026-04-23 — ADR-056 AC-A + external-review #8: verify transcript-level
// key stability. Inserting an event ABOVE an expanded SkillCard must NOT
// collapse it — this exercises the stableEventKey helper.
describe("BubbleTranscript — ADR-056 AC-A expansion stability across inserts", () => {
  it("preserves SkillCard expanded state when a new event arrives at the top", async () => {
    const skillBody =
      "Base directory for this skill: /some/plugins/cache/path\n" +
      "\n" +
      "# Example Skill\n" +
      "\n" +
      "Manual body long enough to clear the 100-char fingerprint length guard " +
      "so the parser reclassifies this content as skill-body.";
    const skillLine = {
      type: "user",
      uuid: "event-uuid-skill-0001",
      timestamp: "2026-04-23T10:00:00.000Z",
      message: { role: "user", content: skillBody },
    };
    const initial = jsonl([skillLine]);
    const { rerender } = render(<BubbleTranscript content={initial} />);

    // User expands the SkillCard.
    await userEvent.click(screen.getByTestId("skill-card-header"));
    expect(screen.getByTestId("skill-card-body")).toBeInTheDocument();

    // New event arrives at the top of the transcript (lowest position).
    // If the key was array-index prefixed, this would shift the SkillCard's
    // key and collapse it. With the stableEventKey helper the SkillCard's
    // key is still `event-uuid-skill-0001` so React keeps the instance.
    const newTop = {
      type: "user",
      uuid: "event-uuid-newtop-0002",
      timestamp: "2026-04-23T09:00:00.000Z",
      message: { role: "user", content: "a prepended user message" },
    };
    rerender(<BubbleTranscript content={jsonl([newTop, skillLine])} />);

    // The SkillCard body is STILL rendered — expansion state survived.
    expect(screen.getByTestId("skill-card-body")).toBeInTheDocument();
  });
});

// 2026-04-23 — ADR-056 AC-A: skill-loader body renders as SkillCard
// (collapsed-by-default, expandable with Markdown body). Replaces the
// ADR-055 SkillChip which was too aggressive at hiding the manual.
describe("BubbleTranscript — ADR-056 AC-A skill-body renders as SkillCard", () => {
  it("collapses a skill-loader user event into a SkillCard with extracted name", () => {
    const skillBody =
      "Base directory for this skill: /some/plugins/cache/path\n" +
      "\n" +
      "# Example Skill\n" +
      "\n" +
      "A long manual body that comfortably exceeds the 100-char length guard, " +
      "so the parser's skill-body fingerprint matches and the renderer swaps " +
      "the raw user bubble for a compact card that says 'Skill: Example Skill'.";
    const content = jsonl([
      { type: "user", message: { role: "user", content: skillBody } },
    ]);
    render(<BubbleTranscript content={content} />);
    const card = screen.getByTestId("skill-card");
    expect(card.textContent).toContain("Skill");
    expect(card.textContent).toContain("Example Skill");
    // No plain user bubble rendered for this event.
    expect(screen.queryByTestId("bubble-user")).toBeNull();
  });

  it("keeps legit user messages containing the phrase as a normal user bubble", () => {
    const content = jsonl([
      {
        type: "user",
        message: {
          role: "user",
          content: "hey, what is this Base directory for this skill: thing?",
        },
      },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.getByTestId("bubble-user")).toBeInTheDocument();
    expect(screen.queryByTestId("skill-card")).toBeNull();
  });
});

// 2026-04-23 — iterate-20260423-chat-followups AC-4: file-history-snapshot
// events are redundant with Edit/Write ToolCards. Filter them OUT of the
// rendered list (pre-virtualizer) — not a renderBubble null-return, which
// Gemini's external review flagged as a virtualization layout risk.
describe("BubbleTranscript — AC-4 file-history-snapshot filtering", () => {
  it("drops file-history-snapshot events from the rendered transcript", () => {
    const content = jsonl([
      { type: "user", message: { content: "before" } },
      {
        type: "file-history-snapshot",
        snapshot: { trackedFileBackups: { "/a.py": "v1", "/b.py": "v2" } },
      },
      { type: "user", message: { content: "after" } },
    ]);
    render(<BubbleTranscript content={content} />);
    // No snapshot bubble in the DOM at all.
    expect(screen.queryByTestId("bubble-file-snapshot")).toBeNull();
    // Toolbar count reflects the filter (2 user events, not 3).
    expect(screen.getByTestId("transcript-event-count").textContent).toMatch(/2 of 2/);
  });

  it("still renders user + assistant events around dropped snapshots", () => {
    const content = jsonl([
      { type: "user", message: { content: "A" } },
      { type: "file-history-snapshot", snapshot: { trackedFileBackups: { "/x": "v" } } },
      { type: "assistant", message: { content: [{ type: "text", text: "B" }] } },
      { type: "file-history-snapshot", snapshot: { trackedFileBackups: { "/y": "v" } } },
      { type: "user", message: { content: "C" } },
    ]);
    render(<BubbleTranscript content={content} />);
    expect(screen.queryAllByTestId("bubble-file-snapshot")).toHaveLength(0);
    expect(screen.queryAllByTestId("bubble-user")).toHaveLength(2);
    expect(screen.queryByTestId("bubble-assistant")).toBeInTheDocument();
  });
});
