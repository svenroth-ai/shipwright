import type { KanbanStatus } from "./task.js";
import type { AutonomyOption } from "./settings.js";

export type ProjectStatus = "active" | "archived" | "error";

/**
 * Iterate 14.0 — derived on the server from shipwright_run_config.json
 * by getProjectMode(). Drives WebUI affordances:
 *   pipeline   → default SDLC flow (phase dropdown visible, standard header)
 *   iterate    → pipeline finished, further work is iteration (no phase dropdown)
 *   standalone → no run_config present (ad-hoc project, info message shown)
 */
export type ProjectMode = "pipeline" | "iterate" | "standalone";

export interface ProjectSettings {
  phaseToStatusMapping?: Record<string, KanbanStatus>;
  claudePluginDirs?: string[];
  autonomy?: AutonomyOption;
  envVars?: Record<string, string>;
  /** Iterate 14.8.2 — custom project color for the Kanban strip. */
  color?: string;
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
  /**
   * Server-derived from shipwright_run_config.json via getProjectMode().
   * Present in API responses; not stored in projects.json.
   */
  mode?: ProjectMode;
  /**
   * Iterate 14.1 — server-derived flag, true when the project's profile
   * declares a `dev_server.command`. Drives the Preview button in the
   * KanbanPage header. Present in API responses; not stored in projects.json.
   */
  hasPreview?: boolean;
}
