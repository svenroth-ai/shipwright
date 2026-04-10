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
