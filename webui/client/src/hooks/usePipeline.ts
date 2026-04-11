import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { PipelineRun } from '../types';

export function usePipeline(projectId: string) {
  return useQuery({
    queryKey: queryKeys.pipeline.byProject(projectId),
    queryFn: () => apiFetch<PipelineRun>(`/projects/${projectId}/pipeline`),
    enabled: !!projectId,
  });
}
