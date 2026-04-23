import { describe, it, expect, beforeEach, vi } from "vitest";
import { join } from "node:path";

import {
  loadActionsForProject,
  loadBundledDefault,
  clearActionsCache,
  type ResolvedActions,
  type LoaderDeps,
} from "./project-actions-loader.js";

// Helper — the loader uses node:path.join which on Windows yields `\`
// separators. Tests need to mirror that so the fake fs map keys match.
function actionsPath(projectPath: string): string {
  return join(projectPath, ".webui", "actions.json");
}

interface FakeFs {
  files: Map<string, { content: string; mtimeMs: number }>;
}

function fakeDeps(fs: FakeFs): LoaderDeps {
  return {
    readFileSync: (path: string) => {
      const entry = fs.files.get(path);
      if (!entry) {
        const err: NodeJS.ErrnoException = new Error("ENOENT");
        err.code = "ENOENT";
        throw err;
      }
      return entry.content;
    },
    statSync: (path: string) => {
      const entry = fs.files.get(path);
      if (!entry) {
        const err: NodeJS.ErrnoException = new Error("ENOENT");
        err.code = "ENOENT";
        throw err;
      }
      return { mtimeMs: entry.mtimeMs };
    },
  };
}

beforeEach(() => {
  clearActionsCache();
});

describe("project-actions-loader — bundled default fallback", () => {
  it("loads bundled default when .webui/actions.json is missing", () => {
    const fs: FakeFs = { files: new Map() };
    const r = loadActionsForProject("/fake/project", fakeDeps(fs));
    expect(r.fromUser).toBe(false);
    expect(r.diagnostics).toHaveLength(0);
    expect(typeof r.actions.defaults.autonomy).toBe("string");
    expect(r.actions.phases.length).toBeGreaterThan(0);
    expect(r.actions.actions.length).toBeGreaterThanOrEqual(3);
  });

  it("bundled default has the three Shipwright actions with external_launch kind", () => {
    const fs: FakeFs = { files: new Map() };
    const r = loadActionsForProject("/fake", fakeDeps(fs));
    const ids = r.actions.actions.map((a) => a.id).sort();
    expect(ids).toEqual(["new-iterate", "new-pipeline", "new-task"]);
    for (const a of r.actions.actions) {
      expect(a.kind).toBe("external_launch");
      expect(typeof a.command_template).toBe("string");
      expect(a.command_template.length).toBeGreaterThan(0);
    }
  });

  it("bundled default.preview is `auto` (ADR-036 — profile is the gate)", () => {
    const fs: FakeFs = { files: new Map() };
    const r = loadActionsForProject("/fake", fakeDeps(fs));
    expect(r.actions.preview.enabled).toBe("auto");
  });
});

describe("project-actions-loader — user file path", () => {
  it("returns parsed user-side actions when present", () => {
    const custom: ResolvedActions = {
      schemaVersion: 1,
      defaults: { autonomy: "autonomous" },
      actions: [
        {
          id: "new-task",
          label: "Task",
          kind: "external_launch",
          command_template: "echo {task.uuid}",
        },
      ],
      phases: [
        { id: "implement", label: "Implement", color: "#F59E0B" },
        { id: "verify", label: "Verify", color: "#059669" },
      ],
      preview: { enabled: true },
    };
    const fs: FakeFs = {
      files: new Map([
        [
          actionsPath("/my/proj"),
          { content: JSON.stringify(custom), mtimeMs: 100 },
        ],
      ]),
    };
    const r = loadActionsForProject("/my/proj", fakeDeps(fs));
    expect(r.fromUser).toBe(true);
    expect(r.diagnostics).toHaveLength(0);
    expect(r.actions.defaults.autonomy).toBe("autonomous");
    expect(r.actions.phases.map((p) => p.id)).toEqual(["implement", "verify"]);
  });

  it("preserves non-Shipwright phase ids (loader does not reject unknown ids)", () => {
    const custom: ResolvedActions = {
      schemaVersion: 1,
      defaults: { autonomy: "guided" },
      actions: [
        {
          id: "new-task",
          label: "Task",
          kind: "external_launch",
          command_template: "echo {task.uuid}",
        },
      ],
      phases: [{ id: "weirdphase", label: "Weird", color: "#fff" }],
      preview: { enabled: "auto" },
    };
    const fs: FakeFs = {
      files: new Map([
        [
          actionsPath("/proj"),
          { content: JSON.stringify(custom), mtimeMs: 1 },
        ],
      ]),
    };
    const r = loadActionsForProject("/proj", fakeDeps(fs));
    expect(r.actions.phases[0].id).toBe("weirdphase");
  });
});

describe("project-actions-loader — malformed file handling", () => {
  it("falls through to bundled default + diagnostics side-channel when JSON is invalid", () => {
    const fs: FakeFs = {
      files: new Map([
        [
          actionsPath("/proj"),
          { content: "not json at all {{{ >>>", mtimeMs: 10 },
        ],
      ]),
    };
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const r = loadActionsForProject("/proj", fakeDeps(fs));
    warnSpy.mockRestore();
    expect(r.fromUser).toBe(false);
    expect(r.diagnostics).toHaveLength(1);
    expect(r.diagnostics[0].code).toBe("actions_file_malformed");
    expect(r.diagnostics[0].path).toContain(".webui");
    // Still returns usable defaults:
    expect(r.actions.actions.length).toBeGreaterThan(0);
  });
});

describe("project-actions-loader — mtime cache", () => {
  it("reads once, then returns cached within same mtime", () => {
    const custom: ResolvedActions = {
      schemaVersion: 1,
      defaults: { autonomy: "guided" },
      actions: [
        {
          id: "new-task",
          label: "Task",
          kind: "external_launch",
          command_template: "x",
        },
      ],
      phases: [{ id: "a", label: "A" }],
      preview: { enabled: "auto" },
    };
    const fs: FakeFs = {
      files: new Map([
        [
          actionsPath("/proj"),
          { content: JSON.stringify(custom), mtimeMs: 42 },
        ],
      ]),
    };
    const deps = fakeDeps(fs);
    const readSpy = vi.spyOn(deps, "readFileSync");
    const r1 = loadActionsForProject("/proj", deps);
    const r2 = loadActionsForProject("/proj", deps);
    expect(r1.actions).toEqual(r2.actions);
    // One user-file read, two stat calls.
    expect(readSpy).toHaveBeenCalledTimes(1);
  });

  it("invalidates cache when mtime changes", () => {
    const customV1: ResolvedActions = {
      schemaVersion: 1,
      defaults: { autonomy: "guided" },
      actions: [{ id: "a", label: "A", kind: "external_launch", command_template: "v1" }],
      phases: [{ id: "a", label: "A" }],
      preview: { enabled: "auto" },
    };
    const customV2: ResolvedActions = {
      ...customV1,
      actions: [{ id: "a", label: "A", kind: "external_launch", command_template: "v2" }],
    };
    const fs: FakeFs = {
      files: new Map([
        [
          actionsPath("/proj"),
          { content: JSON.stringify(customV1), mtimeMs: 100 },
        ],
      ]),
    };
    const deps = fakeDeps(fs);
    const r1 = loadActionsForProject("/proj", deps);
    expect(r1.actions.actions[0].command_template).toBe("v1");

    // Touch the file — newer mtime + new content.
    fs.files.set(actionsPath("/proj"), {
      content: JSON.stringify(customV2),
      mtimeMs: 200,
    });
    const r2 = loadActionsForProject("/proj", deps);
    expect(r2.actions.actions[0].command_template).toBe("v2");
  });
});

describe("project-actions-loader — loadBundledDefault (pure)", () => {
  it("parses the shipped default-actions.json without throwing", () => {
    const d = loadBundledDefault();
    expect(d.defaults.autonomy).toBe("guided");
    // 2026-04-23 — `adopt` phase added; bundle now ships 10 phases (was 9).
    expect(d.phases.length).toBe(10);
    expect(d.actions.length).toBe(3);
    expect(d.phases.some((p) => p.id === "adopt")).toBe(true);
  });

  // 2026-04-23 — iterate-20260423-cli-flag-fix. Regression guard: the
  // bundled command templates MUST use `--add-dir` (a real Claude CLI flag,
  // verified via `claude --help`) rather than `--project-root` (which does
  // not exist and causes `error: unknown option '--project-root'` when the
  // user pastes the copied command).
  it("command_templates use --add-dir, not --project-root", () => {
    const d = loadBundledDefault();
    for (const action of d.actions) {
      const tpl = action.command_template ?? "";
      expect(tpl, `action ${action.id} must not use --project-root`).not.toContain(
        "--project-root",
      );
      expect(tpl, `action ${action.id} must use --add-dir`).toContain(
        "--add-dir",
      );
    }
  });
});
