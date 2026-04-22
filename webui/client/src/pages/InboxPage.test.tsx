/*
 * InboxPage — project-grouping + read-only Ask-bubble test.
 *
 * Iterate 3.7d-b3 rebuild:
 *   - Project grouping + (N open) counts from 3.7c-4 are preserved.
 *   - Cards are read-only: no `<textarea>`, no clickable option pills, no
 *     Launch button.
 *   - Single brown `Resume` button per card.
 *   - Whole-card click-through → `/tasks/<taskId>` via useNavigate.
 *
 * Hooks consumed by InboxPage (and therefore mocked here):
 *   useExternalInbox, useExternalTasks, useProjects, useLaunchTask.
 *
 * Load-bearing testids (also used by iterate-2/3 Playwright specs):
 *   - inbox-page
 *   - inbox-empty
 *   - inbox-session-<uuid>
 *   - inbox-item-<toolUseId> (legacy, retained on a hidden inner node)
 *   - inbox-card-<toolUseId> (new 3.7d-b3)
 *   - inbox-resume-<toolUseId> (new 3.7d-b3)
 *   - inbox-copy-resume-<toolUseId> (legacy, retained)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

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
      <MemoryRouter initialEntries={["/inbox"]}>
        <Routes>
          <Route path="/inbox" element={<InboxPage />} />
          <Route
            path="/tasks/:id"
            element={<div data-testid="task-detail-stub" />}
          />
        </Routes>
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

  it("renders a single Resume button per card (no Launch, no textarea)", () => {
    wireHooks({
      items: [ITEM_A],
      tasks: [TASK_A],
      projects: [PROJECT_A],
    });
    renderPage();

    // Primary Resume button (new 3.7d-b3 testid + legacy v2 testid both
    // render — back-compat wrapper).
    expect(screen.getByTestId("inbox-resume-tu-A")).toBeInTheDocument();
    expect(screen.getByTestId("inbox-copy-resume-tu-A")).toBeInTheDocument();

    // Launch-in-Terminal button from v2 is GONE.
    expect(screen.queryByTestId("inbox-launch-tu-A")).not.toBeInTheDocument();

    // Freetext input + send button from v2 are GONE (no answer POST,
    // webui never answers Claude — external-launch invariant).
    expect(screen.queryByTestId("inbox-freetext-input")).not.toBeInTheDocument();
    expect(screen.queryByTestId("inbox-freetext-send")).not.toBeInTheDocument();
  });

  it("renders option chips as display-only (no button / onclick)", () => {
    const ITEM_WITH_OPTIONS = makeItem({
      toolUseId: "tu-opts",
      taskId: "task-A",
      sessionUuid: "sess-A",
      taskTitle: "Task in project A",
      input: {
        questions: [
          {
            question: "JWT or Session?",
            options: [{ label: "JWT" }, { label: "Session" }],
          },
        ],
      },
    });
    wireHooks({
      items: [ITEM_WITH_OPTIONS],
      tasks: [TASK_A],
      projects: [PROJECT_A],
    });
    const { container } = renderPage();

    // Chips must be rendered but NOT as buttons — they're read-only.
    const chip0 = screen.getByTestId("inbox-option-chip-0");
    const chip1 = screen.getByTestId("inbox-option-chip-1");
    expect(chip0).toBeInTheDocument();
    expect(chip1).toBeInTheDocument();
    expect(chip0.tagName.toLowerCase()).not.toBe("button");
    expect(chip1.tagName.toLowerCase()).not.toBe("button");
    expect(chip0).toHaveTextContent("JWT");
    expect(chip1).toHaveTextContent("Session");

    // No <button> elements should wrap the option labels.
    const buttons = Array.from(container.querySelectorAll("button"));
    for (const b of buttons) {
      const txt = b.textContent ?? "";
      expect(txt).not.toMatch(/^\s*JWT\s*$/);
      expect(txt).not.toMatch(/^\s*Session\s*$/);
    }
  });

  it("whole-card click navigates to /tasks/<taskId>", () => {
    wireHooks({
      items: [ITEM_A],
      tasks: [TASK_A],
      projects: [PROJECT_A],
    });
    renderPage();

    expect(screen.queryByTestId("task-detail-stub")).not.toBeInTheDocument();
    const card = screen.getByTestId("inbox-card-tu-A");
    expect(card).toHaveAttribute("role", "button");
    expect(card).toHaveAttribute("tabIndex", "0");
    fireEvent.click(card);
    expect(screen.getByTestId("task-detail-stub")).toBeInTheDocument();
  });

  it("Enter key on the card navigates to /tasks/<taskId>", () => {
    wireHooks({
      items: [ITEM_A],
      tasks: [TASK_A],
      projects: [PROJECT_A],
    });
    renderPage();

    const card = screen.getByTestId("inbox-card-tu-A");
    fireEvent.keyDown(card, { key: "Enter" });
    expect(screen.getByTestId("task-detail-stub")).toBeInTheDocument();
  });

  it("clicking the Resume button does NOT navigate (stops propagation)", () => {
    wireHooks({
      items: [ITEM_A],
      tasks: [TASK_A],
      projects: [PROJECT_A],
    });
    renderPage();

    const resumeBtn = screen.getByTestId("inbox-resume-tu-A");
    fireEvent.click(resumeBtn);
    // Navigation should NOT have fired — we're still on /inbox.
    expect(screen.queryByTestId("task-detail-stub")).not.toBeInTheDocument();
    // Page marker still present.
    expect(screen.getByTestId("inbox-page")).toBeInTheDocument();
  });
});
