/*
 * InboxPage — project-grouping test (iterate 3 remediation v2 / S4).
 *
 * In v2 the Inbox page no longer mounts `ProjectFilterDropdown`. Instead it
 * groups session cards by project into collapsible `<details>` sections.
 * These tests pin the grouping behavior plus the critical UI invariants:
 *   - every project-group wrapper carries the correct testid,
 *   - cards from two different projects land in separate sections,
 *   - unassigned tasks fall into the "Unassigned" bucket,
 *   - the Answer/Dismiss/best-effort UI from v1 is GONE.
 *
 * Hooks consumed by InboxPage (and therefore mocked here):
 *   useExternalInbox, useExternalTasks, useProjects, useLaunchTask.
 *
 * Load-bearing testids (also used by iterate-2 Playwright specs):
 *   - inbox-page
 *   - inbox-empty
 *   - inbox-session-<uuid>
 *   - inbox-item-<toolUseId>
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import InboxPage from "./InboxPage";
import type { ExternalTask, InboxItem } from "../lib/externalApi";
import type { Project } from "../types";

// Hoisted mocks must be declared before the imports that consume them.
// Vitest lifts vi.mock to the top of the file so these factories run
// before the real hook modules resolve.
vi.mock("../hooks/useExternalInbox", () => ({
  useExternalInbox: vi.fn(),
}));

vi.mock("../hooks/useExternalTasks", () => ({
  useExternalTasks: vi.fn(),
}));

vi.mock("../hooks/useProjects", () => ({
  useProjects: vi.fn(),
}));

vi.mock("../hooks/useLaunchTask", () => ({
  useLaunchTask: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false })),
}));

import { useExternalInbox } from "../hooks/useExternalInbox";
import { useExternalTasks } from "../hooks/useExternalTasks";
import { useProjects } from "../hooks/useProjects";

const mockedInbox = vi.mocked(useExternalInbox);
const mockedTasks = vi.mocked(useExternalTasks);
const mockedProjects = vi.mocked(useProjects);

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

function makeProject(overrides: Partial<Project>): Project {
  return {
    id: "proj-a",
    name: "Project A",
    path: "/tmp/proj-a",
    profile: "generic",
    status: "active",
    lastActive: "2026-04-20T00:00:00Z",
    createdAt: "2026-04-20T00:00:00Z",
    ...overrides,
  };
}

function wireHooks(opts: {
  items: InboxItem[];
  tasks: ExternalTask[];
  projects: Project[];
}) {
  mockedInbox.mockReturnValue({
    data: opts.items,
    isLoading: false,
  } as unknown as ReturnType<typeof useExternalInbox>);
  mockedTasks.mockReturnValue({
    data: opts.tasks,
    isLoading: false,
  } as unknown as ReturnType<typeof useExternalTasks>);
  mockedProjects.mockReturnValue({
    data: opts.projects,
    isLoading: false,
  } as unknown as ReturnType<typeof useProjects>);
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
// grouping.
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

const PROJECT_A = makeProject({ id: "proj-a", name: "Project A" });
const PROJECT_B = makeProject({ id: "proj-b", name: "Project B" });

describe("InboxPage project grouping (iterate 3 remediation v2 / S4)", () => {
  beforeEach(() => {
    mockedInbox.mockReset();
    mockedTasks.mockReset();
    mockedProjects.mockReset();
  });

  it("renders sessions under their project group + preserves existing session testids", () => {
    wireHooks({
      items: [ITEM_A, ITEM_B],
      tasks: [TASK_A, TASK_B],
      projects: [PROJECT_A, PROJECT_B],
    });
    renderPage();

    expect(screen.getByTestId("inbox-page")).toBeInTheDocument();

    // One collapsible group per project.
    expect(screen.getByTestId("inbox-project-group-proj-a")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-project-group-proj-b")).toBeInTheDocument();

    // Sessions render under their projects (load-bearing testid from
    // iterate-2 Playwright specs).
    expect(screen.getByTestId("inbox-session-sess-A")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-session-sess-B")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-item-tu-A")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-item-tu-B")).toBeInTheDocument();

    // Project names render in the summary rows.
    expect(screen.getByText("Project A")).toBeInTheDocument();
    expect(screen.getByText("Project B")).toBeInTheDocument();
  });

  it("tasks with no matching project land in an Unassigned bucket", () => {
    const ORPHAN_ITEM = makeItem({
      taskId: "task-orphan",
      sessionUuid: "sess-orphan",
      toolUseId: "tu-orphan",
    });
    // No matching task at all — derives to the Unassigned bucket.
    wireHooks({
      items: [ORPHAN_ITEM],
      tasks: [],
      projects: [],
    });
    renderPage();

    expect(
      screen.getByTestId("inbox-project-group-unassigned"),
    ).toBeInTheDocument();
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-session-sess-orphan")).toBeInTheDocument();
  });

  it("renders the empty-state when there are no items", () => {
    wireHooks({ items: [], tasks: [], projects: [] });
    renderPage();

    expect(screen.getByTestId("inbox-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("inbox-session-sess-A")).not.toBeInTheDocument();
  });

  it("does NOT render the ProjectFilterDropdown anywhere on the page", () => {
    // v2 decision #1: dropdown removed from Inbox; grouping replaces it.
    wireHooks({
      items: [ITEM_A],
      tasks: [TASK_A],
      projects: [PROJECT_A],
    });
    renderPage();

    // The old v1 testid — must NOT be present.
    expect(
      screen.queryByTestId("inbox-project-filter-dropdown"),
    ).not.toBeInTheDocument();
    // And the shared primitive has no mount of its own on this page.
    expect(
      screen.queryByText(/All projects/i),
    ).not.toBeInTheDocument();
  });

  it("does NOT render the Answer / Dismiss / best-effort UI", () => {
    // v2 decision #2: answer POST + dismiss removed; best-effort pill gone.
    wireHooks({
      items: [ITEM_A],
      tasks: [TASK_A],
      projects: [PROJECT_A],
    });
    renderPage();

    expect(screen.queryByTestId("answer-tu-A")).not.toBeInTheDocument();
    expect(screen.queryByTestId("dismiss-tu-A")).not.toBeInTheDocument();
    expect(screen.queryByText(/best-effort/i)).not.toBeInTheDocument();
  });

  it("renders Launch + Copy-Resume buttons per card", () => {
    wireHooks({
      items: [ITEM_A],
      tasks: [TASK_A],
      projects: [PROJECT_A],
    });
    renderPage();

    expect(screen.getByTestId("inbox-launch-tu-A")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-copy-resume-tu-A")).toBeInTheDocument();
  });
});
