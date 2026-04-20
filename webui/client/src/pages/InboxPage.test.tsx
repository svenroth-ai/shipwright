/*
 * InboxPage — project-filter integration + stale-useMemo regression guard.
 *
 * Section 05 (iterate 3). Consumes the shared `useProjectFilter` hook from
 * section 02 and filters session groups by the active project. Tests mock
 * the three hooks used by the page so we can rerender with a fresh
 * `activeProjectId` without routing gymnastics.
 *
 * Load-bearing testids (also used by iterate-2 Playwright specs):
 *   - inbox-page
 *   - inbox-empty
 *   - inbox-session-<uuid>
 *   - inbox-item-<toolUseId>
 *   - dismiss-<toolUseId>
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import InboxPage from "./InboxPage";
import type { ExternalTask, InboxItem } from "../lib/externalApi";

// Hoisted mocks must be declared before the imports that consume them.
// Vitest lifts vi.mock to the top of the file so these factories run
// before the real hook modules resolve.
vi.mock("../hooks/useExternalInbox", () => ({
  useExternalInbox: vi.fn(),
  useDismissInboxItem: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

vi.mock("../hooks/useExternalTasks", () => ({
  useExternalTasks: vi.fn(),
}));

vi.mock("../hooks/useProjectFilter", () => ({
  useProjectFilter: vi.fn(),
}));

import { useExternalInbox } from "../hooks/useExternalInbox";
import { useExternalTasks } from "../hooks/useExternalTasks";
import { useProjectFilter } from "../hooks/useProjectFilter";

const mockedInbox = vi.mocked(useExternalInbox);
const mockedTasks = vi.mocked(useExternalTasks);
const mockedFilter = vi.mocked(useProjectFilter);

function makeTask(overrides: Partial<ExternalTask>): ExternalTask {
  return {
    taskId: "task-1",
    sessionUuid: "sess-1",
    cwd: "/tmp/cwd",
    pluginDirs: [],
    title: "task-1",
    projectId: "proj-a",
    state: "active",
    createdAt: "2026-04-20T00:00:00Z",
    inbox: {
      pendingToolUseIds: [],
      dismissedToolUseIds: [],
      lastProcessedByteOffset: 0,
    },
    ...overrides,
  };
}

function makeItem(overrides: Partial<InboxItem>): InboxItem {
  return {
    taskId: "task-1",
    sessionUuid: "sess-1",
    taskTitle: "task-1",
    toolUseId: "tu-1",
    toolName: "AskUserQuestion",
    input: { parts: [{ question: "proceed?" }] },
    bestEffort: true,
    ...overrides,
  };
}

// The mocked useExternalInbox/useExternalTasks only need the narrow shape
// InboxPage reads: { data, isLoading }.
function wireHooks(opts: {
  items: InboxItem[];
  tasks: ExternalTask[];
  activeProjectId: string | null;
}) {
  mockedInbox.mockReturnValue({
    data: opts.items,
    isLoading: false,
  } as unknown as ReturnType<typeof useExternalInbox>);
  mockedTasks.mockReturnValue({
    data: opts.tasks,
    isLoading: false,
  } as unknown as ReturnType<typeof useExternalTasks>);
  mockedFilter.mockReturnValue({
    activeProjectId: opts.activeProjectId,
    setActiveProjectId: vi.fn(),
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <InboxPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Two tasks across two projects, each with one pending item in its own
// session. Keeps the fixtures small while still proving cross-project
// isolation.
const TASK_A = makeTask({
  taskId: "task-A",
  sessionUuid: "sess-A",
  title: "Task in project A",
  projectId: "proj-a",
});
const TASK_B = makeTask({
  taskId: "task-B",
  sessionUuid: "sess-B",
  title: "Task in project B",
  projectId: "proj-b",
});

const ITEM_A = makeItem({
  taskId: "task-A",
  sessionUuid: "sess-A",
  taskTitle: "Task in project A",
  toolUseId: "tu-A",
});
const ITEM_B = makeItem({
  taskId: "task-B",
  sessionUuid: "sess-B",
  taskTitle: "Task in project B",
  toolUseId: "tu-B",
});

describe("InboxPage project filter (iterate 3 section 05)", () => {
  beforeEach(() => {
    mockedInbox.mockReset();
    mockedTasks.mockReset();
    mockedFilter.mockReset();
  });

  it("All Projects (activeProjectId = null) renders every session group", () => {
    wireHooks({
      items: [ITEM_A, ITEM_B],
      tasks: [TASK_A, TASK_B],
      activeProjectId: null,
    });
    renderPage();

    expect(screen.getByTestId("inbox-page")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-session-sess-A")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-session-sess-B")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-item-tu-A")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-item-tu-B")).toBeInTheDocument();
    // No empty state when items exist.
    expect(screen.queryByTestId("inbox-empty")).not.toBeInTheDocument();
  });

  it("specific project hides groups whose task belongs to a different project", () => {
    wireHooks({
      items: [ITEM_A, ITEM_B],
      tasks: [TASK_A, TASK_B],
      activeProjectId: "proj-a",
    });
    renderPage();

    expect(screen.getByTestId("inbox-session-sess-A")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-item-tu-A")).toBeInTheDocument();
    // Project B group filtered out.
    expect(screen.queryByTestId("inbox-session-sess-B")).not.toBeInTheDocument();
    expect(screen.queryByTestId("inbox-item-tu-B")).not.toBeInTheDocument();
  });

  it("project with zero matching tasks renders the empty state", () => {
    wireHooks({
      items: [ITEM_A, ITEM_B],
      tasks: [TASK_A, TASK_B],
      activeProjectId: "proj-nonexistent",
    });
    renderPage();

    expect(screen.getByTestId("inbox-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("inbox-session-sess-A")).not.toBeInTheDocument();
    expect(screen.queryByTestId("inbox-session-sess-B")).not.toBeInTheDocument();
  });

  it("project switch re-renders deterministically (stale useMemo guard)", () => {
    // First render in project A — only group A visible.
    wireHooks({
      items: [ITEM_A, ITEM_B],
      tasks: [TASK_A, TASK_B],
      activeProjectId: "proj-a",
    });
    const { rerender } = renderPage();
    expect(screen.getByTestId("inbox-session-sess-A")).toBeInTheDocument();
    expect(screen.queryByTestId("inbox-session-sess-B")).not.toBeInTheDocument();

    // Flip the active project → useMemo must see the new activeProjectId
    // in its dep array and recompute. If a future refactor drops
    // activeProjectId from the memo deps, group A would stay visible and
    // B would stay hidden → this test catches that regression.
    wireHooks({
      items: [ITEM_A, ITEM_B],
      tasks: [TASK_A, TASK_B],
      activeProjectId: "proj-b",
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <InboxPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.queryByTestId("inbox-session-sess-A")).not.toBeInTheDocument();
    expect(screen.getByTestId("inbox-session-sess-B")).toBeInTheDocument();
  });
});
