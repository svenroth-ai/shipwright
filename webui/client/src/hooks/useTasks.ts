import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { Task } from '../types';

export function useTasks(projectId?: string) {
  return useQuery({
    queryKey: projectId ? queryKeys.tasks.byProject(projectId) : queryKeys.tasks.all,
    queryFn: () =>
      projectId
        ? apiFetch<Task[]>(`/projects/${projectId}/tasks`)
        : apiFetch<Task[]>('/tasks'),
    staleTime: 10_000,
  });
}
