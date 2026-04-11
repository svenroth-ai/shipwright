import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { Project } from '../types';

interface CreateProjectParams {
  name: string;
  path: string;
  profile: string;
  settings?: Record<string, unknown>;
}

export function useCreateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: CreateProjectParams) =>
      apiPost<Project>('/projects', params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
    },
  });
}
