export type AutonomyOption = 'guided' | 'autonomous';

export interface GlobalSettings {
  port: number;
  maxConcurrent: number;
  heartbeatIntervalMs: number;
  claudeCliPath?: string;
  defaultProfile?: string;
  defaultAutonomy?: AutonomyOption;
  phaseToStatusMapping?: Record<string, string>;
  /** Iterate 14.8.2 — concrete model id used as the default for new tasks. */
  defaultModel?: string;
  /** Iterate 14.8.2 — permission mode used as the default for new tasks. */
  defaultMode?: string;
}
