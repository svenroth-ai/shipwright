/*
 * TaskDetailHeader.test — iterate 3 section 04b, spec § 5.6.
 *
 * Coverage:
 *  - CTA state machine (O31): pending/draft/awaiting_external_start →
 *    Launch; active/idle → Resume; done → no CTA.
 *  - State transitions re-render CTA without remount.
 *  - 3-dots menu surfaces ONLY Close + Delete (+ debug toggle) — fork is
 *    NOT present (deferred to iterate 4).
 *  - Resume CTA copies to clipboard, never spawns (DO-NOT #5 guard).
 *  - SessionMetadata is accessible via the "Show session details" menu
 *    item, not rendered unconditionally.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  act,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TaskDetailHeader } from "./TaskDetailHeader";
import type { ExternalTask } from "../../lib/externalApi";

const PROJECTS = [
  {
    id: "proj-alpha",
    name: "Alpha",
    path: "/tmp/alpha",
    profile: "custom",
    status: "active" as const,
    lastActive: "2026-04-01",
    createdAt: "2026-04-01",
  },
];

function makeTask(overrides: Partial<ExternalTask> = {}): ExternalTask {
  return {
    taskId: "task-42",
    sessionUuid: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    cwd: "C:/tmp/demo",
    pluginDirs: [],
    title: "CTA header demo",
    projectId: "proj-alpha",
    state: "draft",
    createdAt: "2026-04-20",
    inbox: {
      pendingToolUseIds: [],
      dismissedToolUseIds: [],
      lastProcessedByteOffset: 0,
    },
    ...overrides,
  };
}

function renderHeader(task: ExternalTask, fetchMock?: ReturnType<typeof vi.fn>) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  qc.setQueryData(["projects"], PROJECTS);
  qc.setQueryData(["external-task", task.taskId], task);
  const wrap = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = String(url);
    if (u.includes("/api/projects") && !u.includes("/api/external/")) {
      return new Response(JSON.stringify({ data: PROJECTS }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return fetchMock ? fetchMock(url, init) : new Response("{}", { status: 200 });
  });
  globalThis.fetch = wrap as unknown as typeof fetch;
  return {
    ...render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <TaskDetailHeader task={task} />
        </QueryClientProvider>
      </MemoryRouter>,
    ),
    qc,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  const writeText = vi.fn(async () => {});
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
    writable: true,
  });
});

describe("TaskDetailHeader — CTA state machine (O31)", () => {
  it("draft → renders 'Launch' CTA", () => {
    renderHeader(makeTask({ state: "draft" }));
    expect(screen.getByTestId("cta-launch-in-terminal")).toBeTruthy();
    expect(screen.queryByTestId("cta-copy-resume-command")).toBeNull();
  });

  it("awaiting_external_start → 'Terminal' CTA (iterate 3.7f — Sven UAT)", () => {
    // Command already copied to clipboard; user should switch to terminal.
    renderHeader(makeTask({ state: "awaiting_external_start" }));
    expect(screen.getByTestId("cta-terminal")).toBeTruthy();
    expect(screen.queryByTestId("cta-launch-in-terminal")).toBeNull();
  });

  it("active → 'Terminal' CTA (iterate 3.7f — Sven UAT)", () => {
    renderHeader(makeTask({ state: "active" }));
    expect(screen.getByTestId("cta-terminal")).toBeTruthy();
    expect(screen.queryByTestId("cta-copy-resume-command")).toBeNull();
    expect(screen.queryByTestId("cta-launch-in-terminal")).toBeNull();
  });

  it("idle → 'Resume' CTA", () => {
    renderHeader(makeTask({ state: "idle" }));
    expect(screen.getByTestId("cta-copy-resume-command")).toBeTruthy();
  });

  it("done → NO CTA", () => {
    renderHeader(makeTask({ state: "done" }));
    expect(screen.queryByTestId("cta-launch-in-terminal")).toBeNull();
    expect(screen.queryByTestId("cta-copy-resume-command")).toBeNull();
  });

  it("launch_failed → NO CTA", () => {
    renderHeader(makeTask({ state: "launch_failed" }));
    expect(screen.queryByTestId("cta-launch-in-terminal")).toBeNull();
    expect(screen.queryByTestId("cta-copy-resume-command")).toBeNull();
  });
});

describe("TaskDetailHeader — behavior", () => {
  it("Launch CTA posts /launch with resume=false + copies command (clipboard, NOT spawn)", async () => {
    const writeText = vi.fn(async (_text: string) => {});
    Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
    writable: true,
  });
    const fetchInner = vi.fn(async (url: string | URL | Request, _init?: RequestInit) => {
      const u = String(url);
      if (u.includes("/launch")) {
        return new Response(
          JSON.stringify({
            task: { ...makeTask(), state: "awaiting_external_start" },
            commands: {
              powershell: "& claude /launch PS",
              cmd: "claude /launch CMD",
              posix: "claude /launch POSIX",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 200 });
    });
    renderHeader(makeTask({ state: "draft" }), fetchInner);

    await act(async () => {
      fireEvent.click(screen.getByTestId("cta-launch-in-terminal"));
    });

    await waitFor(() => {
      expect(fetchInner).toHaveBeenCalled();
    });
    const launchCall = fetchInner.mock.calls.find(
      (c) => c[0] !== undefined && String(c[0]).includes("/launch"),
    );
    expect(launchCall).toBeDefined();
    const launchInit = launchCall?.[1] as RequestInit | undefined;
    const body = JSON.parse(launchInit?.body as string);
    expect(body.resume).toBe(false);
    expect(writeText).toHaveBeenCalled();
    // Sanity: we copied the command string, not any "claude --resume" spawn.
    const copied = writeText.mock.calls[0]?.[0];
    expect(copied).toContain("claude");
  });

  it("Terminal CTA (active) posts /launch with resume=true + writes to clipboard (never spawns)", async () => {
    const writeText = vi.fn(async (_text: string) => {});
    Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
    writable: true,
  });
    const fetchInner = vi.fn(async (url: string | URL | Request, _init?: RequestInit) => {
      if (String(url).includes("/launch")) {
        return new Response(
          JSON.stringify({
            task: { ...makeTask({ state: "active" }) },
            commands: {
              powershell: "& claude --resume 'abc' --name 'demo'",
              cmd: "claude --resume abc --name demo",
              posix: "claude --resume 'abc' --name 'demo'",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 200 });
    });
    renderHeader(makeTask({ state: "active" }), fetchInner);

    await act(async () => {
      fireEvent.click(screen.getByTestId("cta-terminal"));
    });
    await waitFor(() => {
      expect(writeText).toHaveBeenCalled();
    });
    const launchCall = fetchInner.mock.calls.find(
      (c) => c[0] !== undefined && String(c[0]).includes("/launch"),
    );
    const launchInit = launchCall?.[1] as RequestInit | undefined;
    const body = JSON.parse(launchInit?.body as string);
    expect(body.resume).toBe(true);
    // No `--resume` was spawned — we only copied the command.
    const copied = writeText.mock.calls[0]?.[0];
    expect(copied).toContain("--resume");
  });

  it("3-dots menu surfaces Close + Delete (+ debug toggle), no Fork", async () => {
    const user = userEvent.setup();
    renderHeader(makeTask({ state: "active" }));
    await user.click(screen.getByTestId("task-detail-menu-trigger"));
    await waitFor(() => screen.getByTestId("task-detail-menu"));
    expect(screen.getByTestId("task-detail-menu-close")).toBeTruthy();
    expect(screen.getByTestId("task-detail-menu-delete")).toBeTruthy();
    expect(screen.getByTestId("task-detail-menu-toggle-debug")).toBeTruthy();
    const menu = screen.getByTestId("task-detail-menu");
    expect(menu.textContent?.toLowerCase()).not.toContain("fork");
  });

  it("debug toggle reveals SessionMetadata (via menu, not permanently)", async () => {
    const user = userEvent.setup();
    renderHeader(makeTask({ state: "active" }));
    expect(screen.queryByTestId("task-detail-session-metadata")).toBeNull();
    await user.click(screen.getByTestId("task-detail-menu-trigger"));
    await waitFor(() => screen.getByTestId("task-detail-menu"));
    await user.click(screen.getByTestId("task-detail-menu-toggle-debug"));
    await waitFor(() => {
      expect(screen.getByTestId("task-detail-session-metadata")).toBeTruthy();
    });
  });

  it("state transitions re-render CTA without remount", () => {
    const { rerender, qc } = renderHeader(makeTask({ state: "draft" }));
    expect(screen.getByTestId("cta-launch-in-terminal")).toBeTruthy();
    // Simulate state transition via cache. iterate 3.7f: active → Terminal
    // (not Resume). Idle → Resume remains.
    const updated = makeTask({ state: "active" });
    qc.setQueryData(["external-task", updated.taskId], updated);
    rerender(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <TaskDetailHeader task={updated} />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("cta-terminal")).toBeTruthy();
    expect(screen.queryByTestId("cta-launch-in-terminal")).toBeNull();
    expect(screen.queryByTestId("cta-copy-resume-command")).toBeNull();
  });
});

// ── 2026-04-23 — iterate-20260423-launch-command-wiring ──
//
// Phase badge must prefer the server-persisted `task.phase` /
// `task.phaseLabel` over the title-regex fallback. The title-regex path
// produces wrong badges for tasks whose title doesn't echo the chosen
// phase (e.g. phase="compliance" + title="audit drift" → regex matches
// "audit" → nothing → badge shows nothing; phase="test" + title="Testing
// the test phase" → regex matches "test" → accidental correct match).
describe("TaskDetailHeader — phase badge source (2026-04-23)", () => {
  it("uses task.phaseLabel when present, not the title regex", () => {
    renderHeader(
      makeTask({
        title: "audit drift report", // title alone would not yield a phase
        phase: "compliance",
        phaseLabel: "Compliance",
      }),
    );
    // The badge label is rendered as visible text.
    expect(screen.getByText("Compliance")).toBeTruthy();
  });

  it("prefers task.phase over a misleading title regex match", () => {
    // Title says "test" but user picked compliance — honor the user.
    renderHeader(
      makeTask({
        title: "Testing the compliance workflow",
        phase: "compliance",
        phaseLabel: "Compliance",
      }),
    );
    expect(screen.getByText("Compliance")).toBeTruthy();
    expect(screen.queryByText("Test")).toBeNull();
  });

  it("falls back to title regex only when task.phase is missing", () => {
    renderHeader(
      makeTask({
        title: "Plan the rollout",
        // no phase on task
      }),
    );
    // Regex still catches "plan" → renders "Plan" badge as before.
    expect(screen.getByText("Plan")).toBeTruthy();
  });
});
