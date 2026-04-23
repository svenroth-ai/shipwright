/*
 * TaskCard unit coverage — 2026-04-23 iterate-20260423-chat-livetest-2 AC-B.
 *
 * Kanban card renders a phase badge (small colored dot + phase label)
 * when the task has `phaseLabel` + `phase` set. Color derived from the
 * shared `lib/phaseStyle.ts` palette so TaskCard + TaskDetailHeader stay
 * in sync. No badge when phase is null/undefined — pre-iterate tasks
 * and unassigned projects don't render a silent-default chip.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";

import { TaskCard } from "./TaskCard";
import type { ExternalTask } from "../../lib/externalApi";

function baseTask(overrides: Partial<ExternalTask> = {}): ExternalTask {
  return {
    taskId: "task-1",
    sessionUuid: "11111111-1111-1111-1111-111111111111",
    title: "Audit drift",
    cwd: "/tmp/project",
    pluginDirs: [],
    projectId: "project-001",
    state: "draft",
    createdAt: "2026-04-23T15:00:00Z",
    inbox: {
      pendingToolUseIds: [],
      dismissedToolUseIds: [],
      lastProcessedByteOffset: 0,
    },
    ...overrides,
  };
}

function renderCard(task: ExternalTask) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TaskCard task={task} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TaskCard — phase badge (AC-B)", () => {
  it("renders phase badge when task.phaseLabel and task.phase are set", () => {
    renderCard(baseTask({ phase: "compliance", phaseLabel: "Compliance" }));
    const badge = screen.getByTestId("task-card-phase-task-1");
    expect(badge.textContent).toContain("Compliance");
    expect(badge.dataset.phase).toBe("compliance");
  });

  it("does NOT render a phase badge when phase is missing (pre-iterate task)", () => {
    renderCard(baseTask());
    expect(screen.queryByTestId("task-card-phase-task-1")).toBeNull();
  });

  it("does NOT render a phase badge when only phase (no label) is set", () => {
    // Defensive — the server persists them together, but if a corrupt row
    // has only phase, we prefer no badge over a badge with an empty label.
    renderCard(baseTask({ phase: "build" }));
    expect(screen.queryByTestId("task-card-phase-task-1")).toBeNull();
  });

  it("falls back to build palette for unknown phase ids (render-safe)", () => {
    // We render the label verbatim but the dot + chip color fall back
    // to the `build` palette via getPhaseStyle. Just assert the badge
    // renders — the fallback is covered in phaseStyle unit tests.
    renderCard(baseTask({ phase: "future-unknown", phaseLabel: "Future" }));
    const badge = screen.getByTestId("task-card-phase-task-1");
    expect(badge.textContent).toContain("Future");
  });
});
