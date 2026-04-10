import type { KanbanStatus } from "./task.js";

export type ProjectStatus = "active" | "archived" | "error";

export interface ProjectSettings {
  phaseToStatusMapping?: Record<string, KanbanStatus>;
  claudePluginDirs?: string[];
}

export interface Project {
  id: string;
  name: string;
  path: string;
  profile: string;
  status: ProjectStatus;
  lastActive: string;
  settings?: ProjectSettings;
  createdAt: string;
}
