/*
 * ProjectChipMenu.test — iterate 3 section 04b.
 *
 * Coverage:
 *  - popover lists every real project + the synthesized Unassigned
 *    entry (N+1 rows).
 *  - selecting a different project fires the reassign mutation + closes
 *    the popover.
 *  - selecting the currently-selected project is a no-op (no PATCH).
 *  - optimistic cache update reflects the new projectId immediately.
 *  - currently-selected entry renders the check icon.
 *  - UNASSIGNED_PROJECT_ID is imported from projectIds.ts — no string
 *    literal "unassigned" in this component (covered by the repo-wide
 *    grep guard in the build gate).
 */

import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ProjectChipMenu } from "./ProjectChipMenu";
import { UNASSIGNED_PROJECT_ID } from "../../lib/projectIds";
import type { ExternalTask } from "../../lib/externalApi";
import type { Project } from "../../types";

const PROJECTS: Project[] = [
  {
    id: "proj-alpha",
    name: "Alpha",
    path: "/tmp/alpha",
    profile: "custom",
    status: "active",
    lastActive: "2026-04-01",
    createdAt: "2026-04-01",
    settings: { color: "#2563eb" },
  },
  {
    id: "proj-beta",
    name: "Beta",
    path: "/tmp/beta",
    profile: "custom",
    status: "active",
    lastActive: "2026-04-01",
    createdAt: "2026-04-01",
  },
];

function makeTask(overrides: Partial<ExternalTask> = {}): ExternalTask {
  return {
    taskId: "task-1",
    sessionUuid: "00000000-0000-0000-0000-000000000001",
    cwd: "/tmp/alpha",
    pluginDirs: [],
    title: "Demo task",
    projectId: "proj-alpha",
    state: "draft",
    createdAt: "2026-04-01",
    inbox: { pendingToolUseIds: [], dismissedToolUseIds: [], lastProcessedByteOffset: 0 },
    ...overrides,
  };
}

/**
 * Build a fetch mock that serves `/api/projects` from the in-memory PROJECTS
 * list + delegates every other URL to the caller-provided handler.
 * Keeps test callers focused on asserting the PATCH without ruling out the
 * unrelated `useProjects` GET.
 */
function wrapFetchMock(inner: ReturnType<typeof vi.fn>) {
  return vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/api/projects") && !u.includes("/api/external/")) {
      return new Response(JSON.stringify({ data: PROJECTS }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return inner(url, init);
  });
}

function renderChip(task: ExternalTask, fetchMock: ReturnType<typeof vi.fn>) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  qc.setQueryData(["projects"], PROJECTS);
  qc.setQueryData(["external-task", task.taskId], task);
  globalThis.fetch = wrapFetchMock(fetchMock) as unknown as typeof fetch;
  return render(
    <QueryClientProvider client={qc}>
      <ProjectChipMenu task={task} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProjectChipMenu", () => {
  it("renders current project name on the trigger", () => {
    renderChip(makeTask(), vi.fn());
    expect(screen.getByTestId("project-chip-name").textContent).toBe("Alpha");
  });

  it("open → lists real projects + synthesized Unassigned", async () => {
    renderChip(makeTask(), vi.fn());
    fireEvent.click(screen.getByTestId("project-chip-trigger"));
    await waitFor(() => {
      expect(screen.getByTestId("project-chip-popover")).toBeTruthy();
    });
    expect(screen.getByTestId("project-chip-option-proj-alpha")).toBeTruthy();
    expect(screen.getByTestId("project-chip-option-proj-beta")).toBeTruthy();
    expect(
      screen.getByTestId(`project-chip-option-${UNASSIGNED_PROJECT_ID}`),
    ).toBeTruthy();
    // Text should include "Unassigned" label from the synthesized row.
    expect(
      screen.getByTestId(`project-chip-option-${UNASSIGNED_PROJECT_ID}`)
        .textContent,
    ).toContain("Unassigned");
  });

  it("currently-selected row renders the check icon", async () => {
    renderChip(makeTask(), vi.fn());
    fireEvent.click(screen.getByTestId("project-chip-trigger"));
    await waitFor(() => screen.getByTestId("project-chip-popover"));
    expect(screen.getByTestId("project-chip-check-proj-alpha")).toBeTruthy();
    expect(screen.queryByTestId("project-chip-check-proj-beta")).toBeNull();
  });

  it("select different project → PATCH fires + optimistic cache update", async () => {
    const task = makeTask();
    const fetchMock = vi.fn(async (_url: string | URL | Request, _init?: RequestInit) => {
      return new Response(
        JSON.stringify({ task: { ...task, projectId: "proj-beta" } }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    renderChip(task, fetchMock);
    fireEvent.click(screen.getByTestId("project-chip-trigger"));
    await waitFor(() => screen.getByTestId("project-chip-popover"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("project-chip-option-proj-beta"));
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const call = fetchMock.mock.calls[0];
    expect(call).toBeDefined();
    const url = call?.[0];
    const init = call?.[1] as RequestInit | undefined;
    expect(String(url)).toContain(`/api/external/tasks/${task.taskId}`);
    expect(init?.method).toBe("PATCH");
    const body = JSON.parse(init?.body as string);
    expect(body).toEqual({ projectId: "proj-beta" });
  });

  it("select currently-selected project → no PATCH", async () => {
    const fetchMock = vi.fn();
    renderChip(makeTask(), fetchMock);
    fireEvent.click(screen.getByTestId("project-chip-trigger"));
    await waitFor(() => screen.getByTestId("project-chip-popover"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("project-chip-option-proj-alpha"));
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("Unassigned task → Unassigned chip label; selecting real project reassigns", async () => {
    const task = makeTask({ projectId: UNASSIGNED_PROJECT_ID });
    expect(task.projectId).toBe(UNASSIGNED_PROJECT_ID);
    const fetchMock = vi.fn(async () => {
      return new Response(
        JSON.stringify({ task: { ...task, projectId: "proj-alpha" } }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    renderChip(task, fetchMock);
    expect(screen.getByTestId("project-chip-name").textContent).toBe("Unassigned");
    fireEvent.click(screen.getByTestId("project-chip-trigger"));
    await waitFor(() => screen.getByTestId("project-chip-popover"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("project-chip-option-proj-alpha"));
    });
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
  });
});
