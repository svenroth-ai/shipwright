import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { Task } from '../types';

export function useTask(projectId: string, taskId: string) {
  return useQuery({
    queryKey: queryKeys.tasks.detail(projectId, taskId),
    queryFn: () => apiFetch<Task>(`/projects/${projectId}/tasks/${taskId}`),
    enabled: !!projectId && !!taskId,
  });
}
