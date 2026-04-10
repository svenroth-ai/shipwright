export type PhaseStatus = "pending" | "running" | "completed" | "failed" | "skipped";

export interface PipelinePhase {
  name: string;
  status: PhaseStatus;
  startedAt?: string;
  completedAt?: string;
  detail?: string;
}

export interface PipelineRun {
  projectId: string;
  phases: PipelinePhase[];
  currentPhase?: string;
  taskId?: string;
}
