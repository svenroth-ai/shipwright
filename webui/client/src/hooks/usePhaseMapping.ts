import { useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useProject } from './useProjects';
import { apiPatch } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { resolvePhaseMapping, getKanbanStatus } from '../lib/phaseMapping';
import type { KanbanStatus } from '../types';

export function usePhaseMapping(projectId?: string) {
  const { data: project } = useProject(projectId ?? '');

  const mapping = useMemo(
    () => resolvePhaseMapping(project?.settings?.phaseToStatusMapping),
    [project?.settings?.phaseToStatusMapping],
  );

  const getStatus = useMemo(
    () => (phase: string) => getKanbanStatus(phase, mapping),
    [mapping],
  );

  return { mapping, getStatus };
}

export function useSavePhaseMapping(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (phaseToStatusMapping: Record<string, KanbanStatus>) =>
      apiPatch(`/projects/${projectId}`, { settings: { phaseToStatusMapping } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.detail(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
    },
  });
}
