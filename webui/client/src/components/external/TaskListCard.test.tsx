import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

import {
  deriveTaskListState,
  TaskListAggregateCard,
  TaskListCardShell,
  TodoWriteCard,
  type AggregatorToolUse,
} from "./TaskListCard";

// ── Shared shell rendering ─────────────────────────────────────────

describe("TaskListCardShell — VS Code visual shape", () => {
  it("renders header label + N/M progress + 3-state icons", () => {
    render(
      <TaskListCardShell
        tasks={[
          { id: "1", subject: "Done item", status: "completed" },
          { id: "2", subject: "Running", status: "in_progress", activeForm: "Running tests" },
          { id: "3", subject: "Queued", status: "pending" },
        ]}
      />,
    );
    // Header label defaults to "Update Todos" per VS Code convention
    expect(screen.getByTestId("task-list-card-title").textContent).toBe("Update Todos");
    // Progress summary = completed/total
    expect(screen.getByTestId("task-list-card-progress").textContent).toBe("1/3");
    const rows = screen.getAllByTestId("task-list-card-item");
    expect(rows).toHaveLength(3);
    expect(rows[0].dataset.status).toBe("completed");
    expect(rows[1].dataset.status).toBe("in_progress");
    expect(rows[2].dataset.status).toBe("pending");
    // Completed items get strike-through
    expect(rows[0].querySelector('span[style*="line-through"]')).not.toBeNull();
    // in_progress uses activeForm (present-continuous) instead of subject.
    expect(rows[1].textContent).toContain("Running tests");
  });

  it("renders loading state (…) when task list is empty", () => {
    render(<TaskListCardShell tasks={[]} />);
    expect(screen.getByTestId("task-list-card-progress").textContent).toBe("…");
    expect(screen.queryByTestId("task-list-card-list")).toBeNull();
  });

  it("falls back to subject when in_progress activeForm is empty", () => {
    render(
      <TaskListCardShell
        tasks={[
          { id: "1", subject: "Raw subject", status: "in_progress", activeForm: "  " },
        ]}
      />,
    );
    expect(screen.getByTestId("task-list-card-item").textContent).toContain("Raw subject");
  });

  it("renders unknown statuses as pending with drift subtitle", () => {
    render(
      <TaskListCardShell
        tasks={[{ id: "1", subject: "Future status", status: "blocked" }]}
      />,
    );
    const row = screen.getByTestId("task-list-card-item");
    expect(row.dataset.status).toBe("pending");
    const sub = within(row).getByTestId("task-list-card-unknown-status");
    expect(sub.textContent).toContain("blocked");
  });
});

// ── TodoWrite adapter ──────────────────────────────────────────────

describe("TodoWriteCard — direct input.todos mapping", () => {
  it("renders 3 items via TaskListCardShell when input.todos is an array", () => {
    render(
      <TodoWriteCard
        id="tu_1"
        input={{
          todos: [
            { content: "First", status: "completed" },
            { content: "Second", status: "in_progress", activeForm: "Working second" },
            { content: "Third", status: "pending" },
          ],
        }}
        result={{ content: "ok", is_error: false }}
      />,
    );
    expect(screen.getByTestId("todo-write-card")).toBeInTheDocument();
    expect(screen.getAllByTestId("task-list-card-item")).toHaveLength(3);
    expect(screen.getByTestId("task-list-card-progress").textContent).toBe("1/3");
  });

  it("streaming: renders empty-loading header when input.todos is null mid-stream", () => {
    render(<TodoWriteCard id="tu_s" input={{ todos: null }} />);
    expect(screen.getByTestId("todo-write-card")).toBeInTheDocument();
    expect(screen.getByTestId("task-list-card-progress").textContent).toBe("…");
  });

  it("falls back to generic ToolCard when stream complete AND input is decisively invalid", () => {
    render(
      <TodoWriteCard
        id="tu_bad"
        input="plain string, not an object"
        result={{ content: "ok", is_error: false }}
      />,
    );
    expect(screen.queryByTestId("todo-write-card")).toBeNull();
    expect(screen.getByTestId("tool-card")).toBeInTheDocument();
  });
});

// ── TaskCreate / TaskUpdate aggregator ─────────────────────────────

describe("deriveTaskListState — aggregator", () => {
  it("seeds pending task from TaskCreate and assigns sequential ids", () => {
    const toolUses: AggregatorToolUse[] = [
      { id: "a", name: "TaskCreate", input: { subject: "First", activeForm: "Doing first" } },
      { id: "b", name: "TaskCreate", input: { subject: "Second", activeForm: "Doing second" } },
    ];
    const tasks = deriveTaskListState(toolUses);
    expect(tasks).toHaveLength(2);
    expect(tasks[0]).toEqual({
      id: "1",
      subject: "First",
      status: "pending",
      activeForm: "Doing first",
    });
    expect(tasks[1].id).toBe("2");
    expect(tasks[1].subject).toBe("Second");
  });

  it("flips status via TaskUpdate matching the sequential taskId", () => {
    const toolUses: AggregatorToolUse[] = [
      { id: "a", name: "TaskCreate", input: { subject: "First" } },
      { id: "b", name: "TaskCreate", input: { subject: "Second" } },
      { id: "c", name: "TaskUpdate", input: { taskId: "1", status: "in_progress" } },
      { id: "d", name: "TaskUpdate", input: { taskId: "1", status: "completed" } },
      { id: "e", name: "TaskUpdate", input: { taskId: "2", status: "in_progress" } },
    ];
    const tasks = deriveTaskListState(toolUses);
    expect(tasks[0].status).toBe("completed");
    expect(tasks[1].status).toBe("in_progress");
  });

  it("walks only up to and including uptoToolUseId (snapshot per event)", () => {
    const toolUses: AggregatorToolUse[] = [
      { id: "a", name: "TaskCreate", input: { subject: "First" } },
      { id: "b", name: "TaskUpdate", input: { taskId: "1", status: "in_progress" } },
      { id: "c", name: "TaskCreate", input: { subject: "Second" } },
      { id: "d", name: "TaskUpdate", input: { taskId: "1", status: "completed" } },
    ];
    // Snapshot at event b: task 1 exists + in_progress, task 2 not created yet.
    const atB = deriveTaskListState(toolUses, "b");
    expect(atB).toHaveLength(1);
    expect(atB[0].status).toBe("in_progress");
    // Snapshot at event c: task 1 still in_progress, task 2 newly created.
    const atC = deriveTaskListState(toolUses, "c");
    expect(atC).toHaveLength(2);
    expect(atC[0].status).toBe("in_progress");
    expect(atC[1].status).toBe("pending");
    // Snapshot at event d: task 1 completed, task 2 pending.
    const atD = deriveTaskListState(toolUses, "d");
    expect(atD[0].status).toBe("completed");
    expect(atD[1].status).toBe("pending");
  });

  it("ignores non-Task tool_uses during the walk (Bash, Read, etc.)", () => {
    const toolUses: AggregatorToolUse[] = [
      { id: "a", name: "TaskCreate", input: { subject: "First" } },
      { id: "b", name: "Bash", input: { command: "ls" } },
      { id: "c", name: "TaskUpdate", input: { taskId: "1", status: "completed" } },
    ];
    const tasks = deriveTaskListState(toolUses);
    expect(tasks).toHaveLength(1);
    expect(tasks[0].status).toBe("completed");
  });

  it("drops TaskUpdate when taskId refers to a non-existent task (defensive)", () => {
    const toolUses: AggregatorToolUse[] = [
      { id: "a", name: "TaskUpdate", input: { taskId: "1", status: "completed" } },
    ];
    const tasks = deriveTaskListState(toolUses);
    expect(tasks).toHaveLength(0);
  });

  it("gives TaskCreate a fallback subject when input.subject is missing", () => {
    const toolUses: AggregatorToolUse[] = [
      { id: "a", name: "TaskCreate", input: {} },
    ];
    const tasks = deriveTaskListState(toolUses);
    expect(tasks[0].subject).toBe("Task 1");
  });
});

describe("TaskListAggregateCard", () => {
  it("renders the accumulated list via TaskListCardShell", () => {
    const all: AggregatorToolUse[] = [
      { id: "a", name: "TaskCreate", input: { subject: "First" } },
      { id: "b", name: "TaskCreate", input: { subject: "Second" } },
      { id: "c", name: "TaskUpdate", input: { taskId: "1", status: "in_progress" } },
    ];
    render(
      <TaskListAggregateCard id="c" allToolUses={all} streamComplete={true} />,
    );
    const rows = screen.getAllByTestId("task-list-card-item");
    expect(rows).toHaveLength(2);
    expect(rows[0].dataset.status).toBe("in_progress");
    expect(rows[1].dataset.status).toBe("pending");
    expect(screen.getByTestId("task-list-card-progress").textContent).toBe("0/2");
  });
});
