import { Hono } from "hono";
import { resolve as pathResolve } from "node:path";
import { statSync as fsStatSync } from "node:fs";
import type { ProjectManager } from "../core/project-manager.js";
import type { FileWatcher } from "../core/file-watcher.js";
import type { EventStore } from "../core/event-store.js";
import type { SSEManager } from "../core/sse-manager.js";
import { AppError } from "../middleware/error-handler.js";
import { loadProfile, getProfilesDir, type ProfileConfig } from "../core/profile-loader.js";

export interface ProjectRouteDeps {
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
  writeFileSync: (path: string, data: string) => void;
  /** Iterate 14.4 — overrides for the pipeline endpoint. Defaulted in
   *  index.ts to real fs / profile-loader; overridden in unit tests. */
  statSync?: (path: string) => { isDirectory: () => boolean };
  loadProfile?: (name: string, dir: string) => ProfileConfig | null;
  profilesDir?: string;
  /** Iterate 14.4 — spawns the initial `project` phase task for a freshly
   *  registered pipeline project. Returns the new task id. */
  spawnInitialProjectPhase?: (project: { id: string; path: string }) => Promise<{ taskId: string }>;
}

export function createProjectRoutes(
  projectManager: ProjectManager,
  fileWatcher: FileWatcher,
  eventStore: EventStore,
  sseManager: SSEManager,
  fsDeps?: ProjectRouteDeps
): Hono {
  const app = new Hono();

  app.get("/api/projects", (c) => {
    return c.json({ data: projectManager.getAll() });
  });

  app.post("/api/projects", async (c) => {
    const body = await c.req.json();
    if (!body.name || !body.path) {
      throw new AppError("name and path are required", 400);
    }

    // Iterate 14.9 — Bug C: this generic endpoint is used by the wizard
    // to register ANY directory (including plain standalone folders with
    // no Shipwright pipeline). Previously we auto-wrote a fresh
    // shipwright_run_config.json with status "not_started", which forced
    // getProjectMode() to return "pipeline" for every project — breaking
    // the Standalone affordance (no "Standalone" badge, no hint in
    // NewIssueModal).
    //
    // Now we only create the directory (if missing) and the
    // `.shipwright-webui` workspace dir. Projects that need a real
    // pipeline use `POST /api/projects/pipeline` which writes a
    // proper run_config. Generic-register stays standalone.
    if (fsDeps) {
      if (!fsDeps.existsSync(body.path)) {
        fsDeps.mkdirSync(body.path, { recursive: true });
      }
      // Ensure .shipwright-webui dir exists for chat/inbox
      const webuiDir = `${body.path}/.shipwright-webui`;
      if (!fsDeps.existsSync(webuiDir)) {
        fsDeps.mkdirSync(webuiDir, { recursive: true });
      }
    }

    const project = projectManager.create(body);

    // Start watching the new project for events
    fileWatcher.watchProject(project.id, project.path, (type) => {
      if (type === "event") {
        sseManager.broadcast({ type: "task:updated", payload: { projectId: project.id }, timestamp: new Date().toISOString() });
      } else {
        sseManager.broadcast({ type: "pipeline:updated", payload: { projectId: project.id }, timestamp: new Date().toISOString() });
      }
    });

    sseManager.broadcast({ type: "project:updated", payload: { id: project.id }, timestamp: new Date().toISOString() });
    return c.json({ data: project }, 201);
  });

  /**
   * Iterate 14.4 — POST /api/projects/pipeline
   *
   * Creates a brand-new pipeline-mode project: validates the path against
   * traversal + collisions, validates the profile, writes a fresh
   * shipwright_run_config.json, registers the project, and spawns the
   * initial `project` phase task. Returns 202 Accepted with { projectId,
   * taskId }.
   *
   * Path safety:
   *   - reject `..` segments in raw input (400)
   *   - resolve to absolute path
   *   - target directory must exist (400)
   *   - not already registered as a project (409)
   *   - target must not already have shipwright_run_config.json unless
   *     `?overwrite=true` query is set (409)
   *   - profile name must resolve via loadProfile (400)
   */
  app.post("/api/projects/pipeline", async (c) => {
    const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const rawPath = typeof body.path === "string" ? body.path : "";
    const profileName = typeof body.profile === "string" ? body.profile : "";
    const overwrite = c.req.query("overwrite") === "true";

    if (!name) throw new AppError("name is required", 400);
    if (!rawPath) throw new AppError("path is required", 400);
    if (!profileName) throw new AppError("profile is required", 400);

    // 1. Reject path traversal segments in RAW input (before resolve)
    const segments = rawPath.split(/[\\/]/);
    if (segments.includes("..")) {
      throw new AppError("path must not contain '..' segments", 400);
    }

    // 2. Normalize
    const resolvedPath = pathResolve(rawPath);

    // 3. Directory must exist
    const statFn = fsDeps?.statSync ?? ((p: string) => fsStatSync(p));
    let isDir = false;
    try {
      const st = statFn(resolvedPath);
      isDir = st.isDirectory();
    } catch {
      isDir = false;
    }
    if (!isDir) {
      throw new AppError("path does not exist or is not a directory", 400);
    }

    // 4. Not already registered
    const allProjects = projectManager.getAll();
    const duplicate = allProjects.some((p) => pathResolve(p.path) === resolvedPath);
    if (duplicate) {
      throw new AppError("project already registered for this path", 409);
    }

    // 5. No existing run_config (unless ?overwrite=true)
    const existsFn = fsDeps?.existsSync ?? (() => false);
    const runConfigPath = `${resolvedPath}/shipwright_run_config.json`;
    if (!overwrite && existsFn(runConfigPath)) {
      throw new AppError("shipwright_run_config.json already exists at path", 409);
    }

    // 6. Validate profile
    const profilesDir = fsDeps?.profilesDir ?? getProfilesDir();
    const loadProfileFn = fsDeps?.loadProfile ?? loadProfile;
    const profileData = loadProfileFn(profileName, profilesDir);
    if (!profileData) {
      throw new AppError(`profile '${profileName}' not found`, 400);
    }

    // 7. Write run config
    const now = new Date().toISOString();
    const runConfig = {
      pipeline: ["project", "design", "plan", "build", "test", "changelog", "deploy", "compliance"],
      status: "pending",
      current_step: "project",
      completed_steps: [] as string[],
      profile: profileName,
      standalone: false,
      project_summary: { name },
      created_at: now,
      updated_at: now,
    };
    if (fsDeps) {
      try {
        const webuiDir = `${resolvedPath}/.shipwright-webui`;
        if (!fsDeps.existsSync(webuiDir)) {
          fsDeps.mkdirSync(webuiDir, { recursive: true });
        }
        fsDeps.writeFileSync(runConfigPath, JSON.stringify(runConfig, null, 2));
      } catch (err) {
        const code = (err as NodeJS.ErrnoException).code ?? "EWRITE";
        return c.json(
          { error: "Failed to write shipwright_run_config.json", code, detail: String(err) },
          500,
        );
      }
    }

    // 8. Register the project
    let project;
    try {
      project = projectManager.create({
        name,
        path: resolvedPath,
        profile: profileName,
        status: "active",
      } as Parameters<typeof projectManager.create>[0]);
    } catch (err) {
      return c.json(
        { error: "Failed to register project", detail: String(err) },
        500,
      );
    }

    // 9. Watch for events
    fileWatcher.watchProject(project.id, project.path, (type) => {
      if (type === "event") {
        sseManager.broadcast({
          type: "task:updated",
          payload: { projectId: project.id },
          timestamp: new Date().toISOString(),
        });
      } else {
        sseManager.broadcast({
          type: "pipeline:updated",
          payload: { projectId: project.id },
          timestamp: new Date().toISOString(),
        });
      }
    });

    sseManager.broadcast({
      type: "project:updated",
      payload: { id: project.id },
      timestamp: new Date().toISOString(),
    });

    // 10. Spawn the initial project-phase task (best-effort)
    let taskId: string | undefined;
    if (fsDeps?.spawnInitialProjectPhase) {
      try {
        const result = await fsDeps.spawnInitialProjectPhase({ id: project.id, path: project.path });
        taskId = result.taskId;
      } catch (err) {
        console.error(JSON.stringify({
          level: "warn",
          message: "Initial project phase spawn failed",
          projectId: project.id,
          error: String(err),
        }));
      }
    }

    return c.json({ data: { projectId: project.id, taskId } }, 202);
  });

  app.get("/api/projects/:id", (c) => {
    const project = projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    return c.json({ data: project });
  });

  app.patch("/api/projects/:id", async (c) => {
    const body = await c.req.json();
    const id = c.req.param("id");

    // Iterate 10 — if the patch touches settings.autonomy, route through
    // updateAutonomy so the per-project run_config.json stays in sync with
    // projects.json. Other settings fields flow through the generic update.
    const autonomyPatch =
      body && typeof body === "object" && body.settings && typeof body.settings === "object"
        ? (body.settings as Record<string, unknown>).autonomy
        : undefined;

    let project;
    if (autonomyPatch === "guided" || autonomyPatch === "autonomous") {
      project = await projectManager.updateAutonomy(id, autonomyPatch);
      // Still apply any OTHER patch fields (envVars, name, etc) via update
      const restPatch = { ...body } as Record<string, unknown>;
      const restSettings = { ...(body.settings ?? {}) } as Record<string, unknown>;
      delete restSettings.autonomy;
      if (Object.keys(restSettings).length > 0 || Object.keys(restPatch).some((k) => k !== "settings")) {
        const merged = { ...restPatch, settings: { ...project.settings, ...restSettings } };
        project = projectManager.update(id, merged as Partial<typeof project>);
      }
    } else {
      project = projectManager.update(id, body);
    }

    return c.json({ data: project });
  });

  app.delete("/api/projects/:id", (c) => {
    const id = c.req.param("id");
    fileWatcher.unwatchProject(id);
    projectManager.delete(id);
    sseManager.broadcast({
      type: "project:updated",
      payload: { id, deleted: true },
      timestamp: new Date().toISOString(),
    });
    return c.body(null, 204);
  });

  return app;
}
