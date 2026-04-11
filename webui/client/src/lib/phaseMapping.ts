import type { KanbanStatus } from '../types';

export const DEFAULT_PHASE_MAPPING: Record<string, KanbanStatus> = {
  project: 'backlog',
  design: 'backlog',
  plan: 'backlog',
  build: 'in_progress',
  test: 'in_review',
  deploy: 'done',
  done: 'done',
};

export const KANBAN_COLUMNS = [
  { id: 'backlog' as const, label: 'Backlog' },
  { id: 'in_progress' as const, label: 'In Progress' },
  { id: 'in_review' as const, label: 'In Review' },
  { id: 'done' as const, label: 'Done' },
] as const;

export const PIPELINE_PHASES = [
  'project', 'design', 'plan', 'build', 'test', 'deploy', 'done',
] as const;

export function resolvePhaseMapping(
  projectOverrides?: Record<string, KanbanStatus>,
): Record<string, KanbanStatus> {
  if (!projectOverrides) return { ...DEFAULT_PHASE_MAPPING };
  return { ...DEFAULT_PHASE_MAPPING, ...projectOverrides };
}

export function getKanbanStatus(
  phase: string,
  mapping: Record<string, KanbanStatus>,
): KanbanStatus {
  return mapping[phase] ?? 'backlog';
}
