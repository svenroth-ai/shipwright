import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { TodoWriteCard } from "./TodoWriteCard";

function makeInput(
  todos: Array<{ content: string; status: string; activeForm?: string }>,
) {
  return { todos };
}

describe("TodoWriteCard — ADR-056 AC-D rendering", () => {
  it("renders a 3-state checklist with the right icons + strike-through", () => {
    render(
      <TodoWriteCard
        id="tu_1"
        name="TodoWrite"
        input={makeInput([
          { content: "First item", status: "completed" },
          { content: "Second item", status: "in_progress", activeForm: "Working on second" },
          { content: "Third item", status: "pending" },
        ])}
        result={{ content: "ok", is_error: false }}
      />,
    );
    const rows = screen.getAllByTestId("todo-write-card-item");
    expect(rows).toHaveLength(3);
    expect(rows[0].dataset.status).toBe("completed");
    expect(rows[1].dataset.status).toBe("in_progress");
    expect(rows[2].dataset.status).toBe("pending");
    // Completed item has strike-through styling.
    expect(rows[0].textContent).toContain("First item");
    expect(rows[0].querySelector("span[style*='line-through']")).not.toBeNull();
    // in_progress displays activeForm (present-continuous).
    expect(rows[1].textContent).toContain("Working on second");
    expect(rows[1].textContent).not.toContain("Second item");
  });

  it("falls back to content when activeForm is empty on in_progress item", () => {
    render(
      <TodoWriteCard
        id="tu_2"
        name="TodoWrite"
        input={makeInput([
          { content: "Raw content", status: "in_progress", activeForm: "   " },
        ])}
      />,
    );
    const row = screen.getByTestId("todo-write-card-item");
    expect(row.textContent).toContain("Raw content");
  });

  it("renders the progress summary N/M matching rendered rows (filtered-valid count)", () => {
    render(
      <TodoWriteCard
        id="tu_3"
        name="TodoWrite"
        input={makeInput([
          { content: "Done 1", status: "completed" },
          { content: "Done 2", status: "completed" },
          { content: "In flight", status: "in_progress" },
          { content: "Todo", status: "pending" },
        ])}
      />,
    );
    const progress = screen.getByTestId("todo-write-card-progress");
    expect(progress.textContent).toBe("2/4");
    // Row count matches the denominator.
    expect(screen.getAllByTestId("todo-write-card-item")).toHaveLength(4);
  });

  it("silently drops items missing content; progress denominator matches rendered count", () => {
    render(
      <TodoWriteCard
        id="tu_4"
        name="TodoWrite"
        input={makeInput([
          { content: "Valid 1", status: "completed" },
          { content: "", status: "pending" }, // skipped
          { content: "Valid 2", status: "pending" },
        ])}
      />,
    );
    expect(screen.getAllByTestId("todo-write-card-item")).toHaveLength(2);
    expect(screen.getByTestId("todo-write-card-progress").textContent).toBe("1/2");
  });

  it("renders unknown status values as pending with a drift subtitle", () => {
    render(
      <TodoWriteCard
        id="tu_5"
        name="TodoWrite"
        input={makeInput([
          { content: "future-status", status: "blocked" },
        ])}
      />,
    );
    const row = screen.getByTestId("todo-write-card-item");
    // unknown → rendered as pending
    expect(row.dataset.status).toBe("pending");
    const subtitle = within(row).getByTestId("todo-write-card-unknown-status");
    expect(subtitle.textContent).toContain("blocked");
  });
});

describe("TodoWriteCard — streaming tolerance (Gemini review #1 HIGH)", () => {
  it("renders empty checklist with loading progress when input.todos is null (mid-stream)", () => {
    render(
      <TodoWriteCard
        id="tu_s1"
        name="TodoWrite"
        input={{ todos: null }}
        // stream still in progress — no tool_result yet
      />,
    );
    // Card renders, no fallback to generic ToolCard
    expect(screen.getByTestId("todo-write-card")).toBeInTheDocument();
    expect(screen.queryByTestId("tool-card")).toBeNull();
    // Progress shows loading indicator
    expect(screen.getByTestId("todo-write-card-progress").textContent).toBe("…");
    expect(screen.queryByTestId("todo-write-card-list")).toBeNull();
  });

  it("renders one item when input.todos arrives partial during streaming", () => {
    render(
      <TodoWriteCard
        id="tu_s2"
        name="TodoWrite"
        input={makeInput([{ content: "partial first", status: "pending" }])}
        // no tool_result yet
      />,
    );
    expect(screen.getByTestId("todo-write-card")).toBeInTheDocument();
    expect(screen.getAllByTestId("todo-write-card-item")).toHaveLength(1);
    expect(screen.getByTestId("todo-write-card-progress").textContent).toBe("0/1");
  });

  it("renders empty-loading header when input is {} during streaming (no todos key yet)", () => {
    render(
      <TodoWriteCard
        id="tu_s3"
        name="TodoWrite"
        input={{}}
      />,
    );
    expect(screen.getByTestId("todo-write-card")).toBeInTheDocument();
    expect(screen.getByTestId("todo-write-card-progress").textContent).toBe("…");
  });

  it("falls back to generic ToolCard when stream is complete AND input is decisively invalid", () => {
    render(
      <TodoWriteCard
        id="tu_s4"
        name="TodoWrite"
        input="not an object at all"
        result={{ content: "ok", is_error: false }}
      />,
    );
    // Decisive fallback — ToolCard renders instead.
    expect(screen.queryByTestId("todo-write-card")).toBeNull();
    expect(screen.getByTestId("tool-card")).toBeInTheDocument();
  });
});
