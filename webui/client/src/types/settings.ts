export type AutonomyOption = 'guided' | 'autonomous';

export interface GlobalSettings {
  port: number;
  maxConcurrent: number;
  heartbeatIntervalMs: number;
  claudeCliPath?: string;
  defaultProfile?: string;
  defaultAutonomy?: AutonomyOption;
  phaseToStatusMapping?: Record<string, string>;
}
