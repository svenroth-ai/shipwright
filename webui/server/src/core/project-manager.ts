import { randomUUID } from "crypto";
import type { Project } from "../../../client/src/types/project.js";
import { AppError } from "../middleware/error-handler.js";

export interface ProjectManagerDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
  readdirSync: (path: string, opts?: { withFileTypes: boolean }) => Array<{ name: string; isDirectory: () => boolean }>;
}

export class ProjectManager {
  private projects = new Map<string, Project>();

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
    return project;
  }

  getAll(): Project[] {
    return Array.from(this.projects.values()).sort(
      (a, b) => new Date(b.lastActive).getTime() - new Date(a.lastActive).getTime()
    );
  }

  getById(id: string): Project | undefined {
    return this.projects.get(id);
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
    return updated;
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
    this.deps.writeFile(this.registryPath, JSON.stringify(arr, null, 2));
  }
}
