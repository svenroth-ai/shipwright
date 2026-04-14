import { randomUUID } from "crypto";
import * as fs from "fs";
import type { Project } from "../../../client/src/types/project.js";
import { AppError } from "../middleware/error-handler.js";
import { getProjectMode } from "../bridge/config-reader.js";
import { loadProfile, getProfilesDir, type ProfileConfig } from "./profile-loader.js";

export interface ProjectManagerDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
  readdirSync: (path: string, opts?: { withFileTypes: boolean }) => Array<{ name: string; isDirectory: () => boolean }>;
  // Optional: cross-process file lock + file-exists guard. Injected by
  // index.ts in production (wraps proper-lockfile). Omitted in unit tests,
  // which exercise persist() sequentially against an in-memory store.
  lock?: (path: string) => Promise<() => Promise<void>>;
  ensureFile?: (path: string) => void;
  // Iterate 14.1 — preview capability detection.
  //
  // statSync / readFileSync are used for mtime-cached sync reads of
  // shipwright_run_config.json and shared/profiles/{name}.json so the
  // derivation is safe to call from hot paths like getAll(). Both are
  // optional — if omitted (unit tests) hasPreview is derived off
  // loadProfile + plain read, which is fine because tests control the
  // filesystem via existsSync/readFile anyway.
  statSync?: (path: string) => { mtimeMs: number };
  readFileSync?: (path: string, encoding: "utf-8" | "utf8") => string;
  loadProfile?: (profileName: string) => ProfileConfig | null;
}

/**
 * Iterate 14.1 — preview capability cache.
 *
 * Key = absolute projectPath. Invalidated when the project's
 * shipwright_run_config.json mtime changes. Avoids re-reading the file
 * on every /api/projects list call (which touches every project).
 *
 * Per-instance so tests get isolation. Production has exactly one
 * ProjectManager, so this is effectively process-global.
 */
interface PreviewCapEntry {
  hasPreview: boolean;
  mtimeMs: number;
}

export class ProjectManager {
  private projects = new Map<string, Project>();
  private previewCapCache = new Map<string, PreviewCapEntry>();

  constructor(
    private registryPath: string,
    private deps: ProjectManagerDeps
  ) {}

  async load(): Promise<void> {
    const dir = this.registryPath.substring(0, this.registryPath.lastIndexOf("/"));
    if (dir && !this.deps.existsSync(dir)) {
      this.deps.mkdirSync(dir, { recursive: true });
    }

    if (!this.deps.existsSync(this.registryPath)) {
      await this.deps.writeFile(this.registryPath, "[]");
      return;
    }

    const content = await this.deps.readFile(this.registryPath, "utf-8");
    const projects: Project[] = JSON.parse(content);
    for (const p of projects) {
      this.projects.set(p.id, p);
    }
  }

  create(data: Omit<Project, "id" | "createdAt" | "lastActive">): Project {
    if (!this.deps.existsSync(data.path)) {
      throw new AppError("Project path does not exist", 400);
    }
    const now = new Date().toISOString();
    const project: Project = {
      ...data,
      id: randomUUID(),
      createdAt: now,
      lastActive: now,
    };
    this.projects.set(project.id, project);
    this.persist();
    return this.withMode(project);
  }

  /**
   * Iterate 14.0 — projects are serialized with a derived `mode` field
   * read from shipwright_run_config.json on each call. Kept here (not in
   * route handlers) so every consumer — REST, SSE broadcasts, etc. —
   * sees consistent mode values without each one re-deriving.
   *
   * Iterate 14.1 — also injects `hasPreview` derived from the profile's
   * dev_server.command entry. Same pattern as mode: server-derived so
   * clients never re-derive it.
   */
  private withMode(project: Project): Project {
    return {
      ...project,
      mode: getProjectMode(project.path),
      hasPreview: this.hasPreviewCapability(project.path),
    };
  }

  /**
   * Iterate 14.1 — true when the project's profile (as written into
   * shipwright_run_config.json by shipwright-run) declares a dev_server.
   *
   * Chain:
   *   projectPath → shipwright_run_config.json.profile →
   *   shared/profiles/{profile}.json.dev_server.command exists?
   *
   * Any missing link → false (no preview button). The cache key is
   * projectPath, invalidated on run_config mtime change. profile-loader
   * has its own separate mtime cache so the profile JSON is only re-read
   * when the profile file itself changes.
   *
   * Public for direct use by the preview-route authorization check.
   */
  hasPreviewCapability(projectPath: string): boolean {
    const runCfgPath = `${projectPath}/shipwright_run_config.json`;
    if (!this.deps.existsSync(runCfgPath)) return false;

    // Try to stat for mtime-based cache. If the injected stat helper is
    // absent (unit tests) or stat fails, we fall through to an uncached
    // read each call — correctness over performance in that degraded path.
    let mtimeMs: number | null = null;
    try {
      const stat = (this.deps.statSync ?? fs.statSync)(runCfgPath);
      mtimeMs = stat.mtimeMs;
      const cached = this.previewCapCache.get(projectPath);
      if (cached && cached.mtimeMs === mtimeMs) return cached.hasPreview;
    } catch {
      // fall through — uncached read
    }

    let profileName = "";
    try {
      const readFileSync = this.deps.readFileSync ?? fs.readFileSync;
      const content = readFileSync(runCfgPath, "utf-8") as string;
      const config = JSON.parse(content) as { profile?: unknown };
      if (typeof config.profile === "string") profileName = config.profile;
    } catch {
      return false;
    }

    if (!profileName) {
      if (mtimeMs !== null) {
        this.previewCapCache.set(projectPath, { hasPreview: false, mtimeMs });
      }
      return false;
    }

    const loader = this.deps.loadProfile ?? ((n: string) => loadProfile(n, getProfilesDir()));
    const profile = loader(profileName);
    const hasPreview = Boolean(profile?.dev_server?.command);

    if (mtimeMs !== null) {
      this.previewCapCache.set(projectPath, { hasPreview, mtimeMs });
    }
    return hasPreview;
  }

  getAll(): Project[] {
    return Array.from(this.projects.values())
      .sort(
        (a, b) => new Date(b.lastActive).getTime() - new Date(a.lastActive).getTime()
      )
      .map((p) => this.withMode(p));
  }

  getById(id: string): Project | undefined {
    const project = this.projects.get(id);
    return project ? this.withMode(project) : undefined;
  }

  update(id: string, patch: Partial<Project>): Project {
    const existing = this.projects.get(id);
    if (!existing) throw new AppError("Project not found", 404);
    const updated: Project = {
      ...existing,
      ...patch,
      id: existing.id,
      lastActive: new Date().toISOString(),
    };
    this.projects.set(id, updated);
    this.persist();
    return this.withMode(updated);
  }

  /**
   * Iterate 10 — write the per-project autonomy setting into BOTH
   * projects.json (in-memory + webui registry) AND the project's own
   * `shipwright_run_config.json` so the Shipwright plugin chain
   * (shipwright-project, shipwright-build, etc.) actually reads the
   * same value. Prior to this, autonomy set via the webui Settings page
   * was a silent placebo because the plugins load run_config.json
   * directly, not projects.json.
   *
   * The run_config write merges with existing content so we don't
   * clobber other fields. A missing file is created fresh with just
   * the autonomy field. Write failures are logged but non-fatal —
   * the in-memory update always succeeds so the UI stays responsive.
   */
  async updateAutonomy(id: string, autonomy: "guided" | "autonomous"): Promise<Project> {
    const existing = this.projects.get(id);
    if (!existing) throw new AppError("Project not found", 404);

    // 1. Update in-memory + projects.json
    const updated = this.update(id, {
      settings: { ...existing.settings, autonomy },
    });

    // 2. Merge into <project>/shipwright_run_config.json (non-fatal).
    const runConfigPath = `${existing.path}/shipwright_run_config.json`;
    try {
      let runConfig: Record<string, unknown> = {};
      if (this.deps.existsSync(runConfigPath)) {
        const content = await this.deps.readFile(runConfigPath, "utf-8");
        try {
          runConfig = JSON.parse(content) as Record<string, unknown>;
        } catch {
          // Malformed — fall back to fresh object so we don't lose the write.
          runConfig = {};
        }
      }
      runConfig.autonomy = autonomy;
      await this.deps.writeFile(runConfigPath, JSON.stringify(runConfig, null, 2));
    } catch (err) {
      console.error(JSON.stringify({
        level: "warn",
        message: "Autonomy sync to shipwright_run_config.json failed",
        projectId: id,
        error: String(err),
      }));
    }

    return updated;
  }

  delete(id: string): void {
    if (!this.projects.has(id)) throw new AppError("Project not found", 404);
    this.projects.delete(id);
    this.persist();
  }

  touchLastActive(id: string): void {
    const existing = this.projects.get(id);
    if (existing) {
      existing.lastActive = new Date().toISOString();
      this.persist();
    }
  }

  discover(directory: string): Project[] {
    const entries = this.deps.readdirSync(directory, { withFileTypes: true });
    const found: Project[] = [];
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const fullPath = `${directory}/${entry.name}`;
      const hasRunConfig = this.deps.existsSync(`${fullPath}/shipwright_run_config.json`);
      const hasProjectConfig = this.deps.existsSync(`${fullPath}/shipwright_project_config.json`);
      if (hasRunConfig || hasProjectConfig) {
        const now = new Date().toISOString();
        found.push({
          id: randomUUID(),
          name: entry.name,
          path: fullPath,
          profile: "default",
          status: "active",
          createdAt: now,
          lastActive: now,
        });
      }
    }
    return found;
  }

  private persist(): void {
    const arr = Array.from(this.projects.values());
    const data = JSON.stringify(arr, null, 2);
    // Fire-and-forget: keeps create/update/delete/touchLastActive sync so
    // route handlers don't need to await file I/O. proper-lockfile
    // serializes concurrent writers in-process, so the JSON stays
    // consistent even under bursty updates (e.g. multiple HTTP requests
    // + touchLastActive from heartbeat). Errors are logged, not thrown,
    // because the in-memory Map is still authoritative until next load.
    void this.persistLocked(data).catch((err) =>
      console.error(
        JSON.stringify({
          level: "error",
          message: "projects.json persist failed",
          error: String(err),
        })
      )
    );
  }

  private async persistLocked(data: string): Promise<void> {
    if (this.deps.ensureFile) this.deps.ensureFile(this.registryPath);
    if (!this.deps.lock) {
      await this.deps.writeFile(this.registryPath, data);
      return;
    }
    const release = await this.deps.lock(this.registryPath);
    try {
      await this.deps.writeFile(this.registryPath, data);
    } finally {
      await release();
    }
  }
}
