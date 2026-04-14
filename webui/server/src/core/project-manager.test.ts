import { describe, it, expect, vi } from "vitest";
import { ProjectManager } from "./project-manager.js";
import type { ProjectManagerDeps } from "./project-manager.js";

function mockDeps(initialData: string = "[]"): ProjectManagerDeps {
  const store: Record<string, string> = {};
  return {
    readFile: vi.fn(async (path: string) => store[path] ?? initialData),
    writeFile: vi.fn(async (path: string, data: string) => { store[path] = data; }),
    existsSync: vi.fn(() => true),
    mkdirSync: vi.fn(),
    readdirSync: vi.fn(() => []),
  };
}

describe("ProjectManager", () => {
  it("create assigns UUID, sets timestamps, persists", () => {
    const deps = mockDeps();
    const pm = new ProjectManager("/tmp/projects.json", deps);
    const p = pm.create({ name: "Test", path: "/tmp/proj", profile: "default", status: "active" });
    expect(p.id).toBeDefined();
    expect(p.createdAt).toBeDefined();
    expect(p.lastActive).toBeDefined();
    expect(deps.writeFile).toHaveBeenCalled();
  });

  it("getAll returns projects sorted by lastActive desc", async () => {
    const projects = [
      { id: "p1", name: "Old", path: "/tmp/a", profile: "default", status: "active" as const, createdAt: "2026-01-01T00:00:00Z", lastActive: "2026-01-01T00:00:00Z" },
      { id: "p2", name: "New", path: "/tmp/b", profile: "default", status: "active" as const, createdAt: "2026-01-02T00:00:00Z", lastActive: "2026-01-02T00:00:00Z" },
    ];
    const deps = mockDeps(JSON.stringify(projects));
    const pm = new ProjectManager("/tmp/projects.json", deps);
    await pm.load();
    const all = pm.getAll();
    expect(all[0].name).toBe("New");
    expect(all[1].name).toBe("Old");
  });

  it("update merges patch and updates lastActive", () => {
    const deps = mockDeps();
    const pm = new ProjectManager("/tmp/projects.json", deps);
    const p = pm.create({ name: "Test", path: "/tmp/proj", profile: "default", status: "active" });
    const updated = pm.update(p.id, { name: "Updated" });
    expect(updated.name).toBe("Updated");
    expect(new Date(updated.lastActive).getTime()).toBeGreaterThanOrEqual(new Date(p.lastActive).getTime());
  });

  it("delete removes from map and persists", () => {
    const deps = mockDeps();
    const pm = new ProjectManager("/tmp/projects.json", deps);
    const p = pm.create({ name: "Test", path: "/tmp/proj", profile: "default", status: "active" });
    pm.delete(p.id);
    expect(pm.getById(p.id)).toBeUndefined();
  });

  it("load with non-existent file creates directory and empty registry", async () => {
    const deps = mockDeps();
    (deps.existsSync as any).mockReturnValue(false);
    const pm = new ProjectManager("/tmp/.shipwright-webui/projects.json", deps);
    await pm.load();
    expect(deps.mkdirSync).toHaveBeenCalled();
    expect(deps.writeFile).toHaveBeenCalledWith("/tmp/.shipwright-webui/projects.json", "[]");
  });

  it("load with existing file populates map", async () => {
    const projects = [{ id: "p1", name: "Test", path: "/tmp", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" }];
    const deps = mockDeps(JSON.stringify(projects));
    const pm = new ProjectManager("/tmp/projects.json", deps);
    await pm.load();
    expect(pm.getById("p1")).toBeDefined();
  });

  it("discover finds directories with config files", () => {
    const deps = mockDeps();
    (deps.readdirSync as any).mockReturnValue([
      { name: "proj1", isDirectory: () => true },
      { name: "proj2", isDirectory: () => true },
      { name: "file.txt", isDirectory: () => false },
    ]);
    (deps.existsSync as any).mockImplementation((p: string) =>
      p.includes("proj1/shipwright_run_config.json") || p.includes("proj2/shipwright_project_config.json")
    );
    const pm = new ProjectManager("/tmp/projects.json", deps);
    const found = pm.discover("/projects");
    expect(found).toHaveLength(2);
  });

  it("discover ignores dirs without config", () => {
    const deps = mockDeps();
    (deps.readdirSync as any).mockReturnValue([{ name: "noconfig", isDirectory: () => true }]);
    (deps.existsSync as any).mockReturnValue(false);
    const pm = new ProjectManager("/tmp/projects.json", deps);
    expect(pm.discover("/projects")).toHaveLength(0);
  });

  it("getById returns undefined for non-existent", () => {
    const deps = mockDeps();
    const pm = new ProjectManager("/tmp/projects.json", deps);
    expect(pm.getById("nonexistent")).toBeUndefined();
  });

  it("create with non-existent path throws 400", () => {
    const deps = mockDeps();
    (deps.existsSync as any).mockReturnValue(false);
    const pm = new ProjectManager("/tmp/projects.json", deps);
    expect(() => pm.create({ name: "Test", path: "/nope", profile: "default", status: "active" })).toThrow();
  });

  // Iterate 10 — autonomy sync to shipwright_run_config.json so the plugin
  // chain (shipwright-project etc.) actually sees per-project autonomy
  // set via the webui. Previously only stored in projects.json, which
  // the plugins never read.
  it("update with settings.autonomy writes merged shipwright_run_config.json", async () => {
    const store: Record<string, string> = {
      "/tmp/projects.json": "[]",
      "/tmp/proj/shipwright_run_config.json": JSON.stringify({
        pipeline: ["project", "build"],
        status: "complete",
        other_field: "preserved",
      }),
    };
    const deps: ProjectManagerDeps = {
      readFile: vi.fn(async (path: string) => store[path] ?? ""),
      writeFile: vi.fn(async (path: string, data: string) => { store[path] = data; }),
      existsSync: vi.fn((path: string) => path in store || path === "/tmp/proj"),
      mkdirSync: vi.fn(),
      readdirSync: vi.fn(() => []),
    };
    const pm = new ProjectManager("/tmp/projects.json", deps);
    const p = pm.create({ name: "Test", path: "/tmp/proj", profile: "default", status: "active" });

    await pm.updateAutonomy(p.id, "autonomous");

    // Merged JSON: original fields preserved + autonomy added
    const runCfg = JSON.parse(store["/tmp/proj/shipwright_run_config.json"]);
    expect(runCfg.autonomy).toBe("autonomous");
    expect(runCfg.pipeline).toEqual(["project", "build"]);
    expect(runCfg.status).toBe("complete");
    expect(runCfg.other_field).toBe("preserved");
  });

  it("updateAutonomy creates shipwright_run_config.json when missing (non-fatal)", async () => {
    const store: Record<string, string> = { "/tmp/projects.json": "[]" };
    const deps: ProjectManagerDeps = {
      readFile: vi.fn(async (path: string) => store[path] ?? ""),
      writeFile: vi.fn(async (path: string, data: string) => { store[path] = data; }),
      existsSync: vi.fn((path: string) => path in store || path === "/tmp/proj"),
      mkdirSync: vi.fn(),
      readdirSync: vi.fn(() => []),
    };
    const pm = new ProjectManager("/tmp/projects.json", deps);
    const p = pm.create({ name: "Test", path: "/tmp/proj", profile: "default", status: "active" });

    await pm.updateAutonomy(p.id, "guided");

    const runCfg = JSON.parse(store["/tmp/proj/shipwright_run_config.json"]);
    expect(runCfg.autonomy).toBe("guided");
  });

  it("updateAutonomy also writes autonomy into project.settings in memory + projects.json", async () => {
    const deps = mockDeps();
    const pm = new ProjectManager("/tmp/projects.json", deps);
    const p = pm.create({ name: "Test", path: "/tmp/proj", profile: "default", status: "active" });

    await pm.updateAutonomy(p.id, "autonomous");

    const reloaded = pm.getById(p.id);
    expect(reloaded?.settings?.autonomy).toBe("autonomous");
  });

  // Iterate 14.1 — hasPreviewCapability derives from
  // shipwright_run_config.json.profile → shared/profiles/{name}.json.dev_server.command
  // Cache keyed on run_config mtime so /api/projects list calls stay cheap.
  describe("hasPreviewCapability (iterate 14.1)", () => {
    function depsWithRunConfig(runConfig: unknown | null, profile: unknown | null): ProjectManagerDeps {
      const runCfgPath = "/tmp/proj/shipwright_run_config.json";
      const runCfgContent = runConfig === null ? null : JSON.stringify(runConfig);
      return {
        readFile: vi.fn(async () => "[]"),
        writeFile: vi.fn(async () => {}),
        existsSync: vi.fn((p: string) => {
          if (p === runCfgPath) return runCfgContent !== null;
          return true;
        }),
        mkdirSync: vi.fn(),
        readdirSync: vi.fn(() => []),
        statSync: vi.fn(() => ({ mtimeMs: 1000 })),
        readFileSync: vi.fn(() => runCfgContent ?? ""),
        loadProfile: vi.fn(() => profile as never),
      };
    }

    it("returns false when run_config is missing", () => {
      const deps = depsWithRunConfig(null, null);
      const pm = new ProjectManager("/tmp/projects.json", deps);
      expect(pm.hasPreviewCapability("/tmp/proj")).toBe(false);
    });

    it("returns false when run_config has no profile field", () => {
      const deps = depsWithRunConfig({ status: "in_progress" }, null);
      const pm = new ProjectManager("/tmp/projects.json", deps);
      expect(pm.hasPreviewCapability("/tmp/proj")).toBe(false);
    });

    it("returns false when profile loads but has no dev_server.command", () => {
      const deps = depsWithRunConfig(
        { profile: "supabase-nextjs" },
        { name: "supabase-nextjs" },
      );
      const pm = new ProjectManager("/tmp/projects.json", deps);
      expect(pm.hasPreviewCapability("/tmp/proj")).toBe(false);
    });

    it("returns true when profile has dev_server.command", () => {
      const deps = depsWithRunConfig(
        { profile: "supabase-nextjs" },
        { name: "supabase-nextjs", dev_server: { command: "npm run dev", port: 3000 } },
      );
      const pm = new ProjectManager("/tmp/projects.json", deps);
      expect(pm.hasPreviewCapability("/tmp/proj")).toBe(true);
    });

    it("caches by mtime — second call does not re-read file", () => {
      const deps = depsWithRunConfig(
        { profile: "supabase-nextjs" },
        { name: "supabase-nextjs", dev_server: { command: "npm run dev", port: 3000 } },
      );
      const pm = new ProjectManager("/tmp/projects.json", deps);
      pm.hasPreviewCapability("/tmp/proj");
      pm.hasPreviewCapability("/tmp/proj");
      pm.hasPreviewCapability("/tmp/proj");
      // Three calls, but readFileSync should only hit once (cache hit on 2 + 3).
      expect((deps.readFileSync as any).mock.calls.length).toBe(1);
    });

    it("re-reads when mtime changes", () => {
      const deps = depsWithRunConfig(
        { profile: "supabase-nextjs" },
        { name: "supabase-nextjs", dev_server: { command: "npm run dev", port: 3000 } },
      );
      let mtime = 1000;
      (deps.statSync as any) = vi.fn(() => ({ mtimeMs: mtime }));
      const pm = new ProjectManager("/tmp/projects.json", deps);
      pm.hasPreviewCapability("/tmp/proj");
      mtime = 2000;
      pm.hasPreviewCapability("/tmp/proj");
      expect((deps.readFileSync as any).mock.calls.length).toBe(2);
    });

    it("returns false on malformed run_config JSON", () => {
      const deps = depsWithRunConfig({}, null);
      (deps.readFileSync as any) = vi.fn(() => "{not json");
      const pm = new ProjectManager("/tmp/projects.json", deps);
      expect(pm.hasPreviewCapability("/tmp/proj")).toBe(false);
    });
  });

  // Iterate 14.1 — Project serialization includes hasPreview.
  it("getById returns Project with hasPreview from profile", () => {
    const store: Record<string, string> = {
      "/tmp/projects.json": "[]",
    };
    const deps: ProjectManagerDeps = {
      readFile: vi.fn(async (path: string) => store[path] ?? ""),
      writeFile: vi.fn(async (path: string, data: string) => { store[path] = data; }),
      existsSync: vi.fn((path: string) => path in store || path === "/tmp/proj" || path === "/tmp/proj/shipwright_run_config.json"),
      mkdirSync: vi.fn(),
      readdirSync: vi.fn(() => []),
      statSync: vi.fn(() => ({ mtimeMs: 1 })),
      readFileSync: vi.fn(() => JSON.stringify({ profile: "supabase-nextjs" })),
      loadProfile: vi.fn(() => ({ name: "supabase-nextjs", dev_server: { command: "npm run dev", port: 3000 } } as never)),
    };
    const pm = new ProjectManager("/tmp/projects.json", deps);
    const p = pm.create({ name: "Test", path: "/tmp/proj", profile: "default", status: "active" });
    const reloaded = pm.getById(p.id);
    expect(reloaded?.hasPreview).toBe(true);
  });
});
