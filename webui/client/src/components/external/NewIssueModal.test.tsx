import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { NewIssueModal } from "./NewIssueModal";
import type {
  ActionDefinition,
  ResolvedProjectActions,
} from "../../lib/externalApi";

const PIPELINE_ACTION: ActionDefinition = {
  id: "new-pipeline",
  label: "New pipeline",
  kind: "external_launch",
  command_template: "claude /shipwright-run",
};
const TASK_ACTION: ActionDefinition = {
  id: "new-task",
  label: "New task",
  kind: "external_launch",
  command_template: "claude /shipwright-{task.phase}",
};

const SAMPLE_ACTIONS: ResolvedProjectActions = {
  actions: [TASK_ACTION, PIPELINE_ACTION],
  phases: [
    { id: "build", label: "Build" },
    { id: "design", label: "Design" },
  ],
  defaults: { autonomy: "guided" },
  preview: {
    enabled: false,
    command: null,
    port: null,
    ready_path: null,
    ready_timeout_seconds: null,
  },
  diagnostics: [],
};

interface RenderModalOpts {
  /** Optional override for seeded projects[] in the React Query cache. */
  projectsOverride?: Array<Record<string, unknown>>;
}

function renderModal(
  overrides: Partial<React.ComponentProps<typeof NewIssueModal>> & RenderModalOpts = {},
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const { projectsOverride, ...props_ } = overrides;
  // Mock useProjects list via the fetch layer — but useProjects queries
  // `/projects`. Seed the query cache directly so we skip the network.
  qc.setQueryData(
    ["projects"],
    projectsOverride ?? [
      {
        id: "proj-1",
        name: "demo",
        path: "/tmp/demo",
        profile: "supabase-nextjs",
        status: "active",
        createdAt: "2026-04-01",
        lastActive: "2026-04-20",
      },
    ],
  );
  const props = {
    open: true,
    onOpenChange: vi.fn(),
    action: TASK_ACTION,
    projectActions: SAMPLE_ACTIONS,
    ...props_,
  };
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <NewIssueModal {...props} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("NewIssueModal", () => {
  it("renders with mode=new-task by default", () => {
    renderModal();
    expect(screen.getByTestId("new-issue-modal-new-task")).toBeTruthy();
    expect(screen.getByText("New Task")).toBeTruthy();
  });

  it("renders mode=new-pipeline with the AutonomyToggle", () => {
    renderModal({ action: PIPELINE_ACTION });
    expect(screen.getByTestId("new-issue-modal-new-pipeline")).toBeTruthy();
    expect(screen.getByTestId("autonomy-toggle")).toBeTruthy();
  });

  it("Task mode does NOT render the AutonomyToggle (FR-03.72)", () => {
    renderModal({ action: TASK_ACTION });
    expect(screen.queryByTestId("autonomy-toggle")).toBeNull();
  });

  it("footer is exactly 'Esc to cancel' (FR-03.92)", () => {
    renderModal();
    const hint = screen.getByTestId("new-issue-footer-hint");
    expect(hint.textContent?.replace(/\s+/g, " ").trim()).toBe("Esc to cancel");
  });

  it("has NO priority field anywhere (FR-03.21 regression)", () => {
    renderModal();
    expect(screen.queryByText(/priority/i)).toBeNull();
  });

  it("returns null when action is null (closed dropdown state)", () => {
    const { container } = renderModal({ action: null });
    expect(container.firstChild).toBeNull();
  });

  it("Save-to-Backlog path closes modal without navigation + writes no clipboard", async () => {
    const write = vi.fn(async () => undefined);
    const onOpenChange = vi.fn();
    renderModal({
      writeToClipboard: write,
      onOpenChange,
      onToast: () => {},
    });

    // Stub createTask + launchExternalTask by mocking the global fetch.
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes("/api/external/tasks") && !String(url).includes("/launch")) {
        return new Response(
          JSON.stringify({
            task: {
              taskId: "task-1",
              sessionUuid: "00000000-0000-0000-0000-000000000001",
              cwd: "/tmp/demo",
              pluginDirs: [],
              title: "x",
              projectId: "proj-1",
              state: "draft",
              createdAt: "",
              inbox: { pendingToolUseIds: [], dismissedToolUseIds: [], lastProcessedByteOffset: 0 },
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await act(async () => {
      fireEvent.change(screen.getByTestId("new-issue-title-input"), {
        target: { value: "Save test" },
      });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("new-issue-save-btn"));
    });

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(write).not.toHaveBeenCalled();
  });

  // 2026-04-23 — Adopt phase gate. `/shipwright-adopt` is one-shot; once
  // a project is adopted (shipwright_run_config.json exists) the phase
  // option disappears so users can't re-trigger it. We assert on the
  // trigger's visible label (which reflects phases[0] via the reset
  // effect) because Radix DropdownMenu.Content only mounts under a real
  // pointer event; JSDOM + fireEvent.click doesn't open it. The existing
  // Playwright spec `70-h-actions-endpoint.spec.ts` exercises the open
  // menu path.
  describe("adopt phase gating (2026-04-23)", () => {
    const ACTIONS_WITH_ADOPT: ResolvedProjectActions = {
      ...SAMPLE_ACTIONS,
      phases: [
        { id: "adopt", label: "Adopt", color: "#64748B" },
        { id: "build", label: "Build", color: "#F59E0B" },
        { id: "design", label: "Design", color: "#A855F7" },
      ],
    };

    const baseProject = {
      id: "proj-1",
      name: "demo",
      path: "/tmp/demo",
      profile: "supabase-nextjs",
      status: "active",
      createdAt: "2026-04-01",
      lastActive: "2026-04-20",
    };

    it("hides the Adopt phase when selected project is already adopted", () => {
      renderModal({
        projectActions: ACTIONS_WITH_ADOPT,
        projectsOverride: [{ ...baseProject, adopted: true }],
      });
      // Trigger shows the first visible phase. Adopt was first in the
      // source list; with the gate active it's filtered out, so the
      // trigger reflects "Build" (next phase in the array).
      const trigger = screen.getByTestId("new-issue-phase-select");
      expect(trigger.textContent).toContain("Build");
      expect(trigger.textContent).not.toContain("Adopt");
    });

    it("shows the Adopt phase when selected project is NOT adopted", () => {
      renderModal({
        projectActions: ACTIONS_WITH_ADOPT,
        projectsOverride: [{ ...baseProject, adopted: false }],
      });
      const trigger = screen.getByTestId("new-issue-phase-select");
      expect(trigger.textContent).toContain("Adopt");
    });

    it("treats missing adopted field as not-adopted (legacy API shape)", () => {
      // A server that hasn't been upgraded yet may omit the field. Showing
      // Adopt in that ambiguous case is safer than hiding it — the skill's
      // own pre-flight check will refuse to run if run_config is already
      // present, so false positives are recoverable.
      renderModal({
        projectActions: ACTIONS_WITH_ADOPT,
        projectsOverride: [baseProject], // no `adopted` field
      });
      const trigger = screen.getByTestId("new-issue-phase-select");
      expect(trigger.textContent).toContain("Adopt");
    });
  });
});
