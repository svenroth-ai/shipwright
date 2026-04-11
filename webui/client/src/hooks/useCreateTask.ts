import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { Task } from '../types';

interface CreateTaskParams {
  projectId: string;
  description: string;
  startImmediately?: boolean;
}

export function useCreateTask() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: ({ projectId, description, startImmediately = true }: CreateTaskParams) =>
      apiPost<Task>(`/projects/${projectId}/tasks`, { description, startImmediately }),
    onSuccess: (task) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(task.projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });

      // Fire-and-forget classification
      apiPost(`/projects/${task.projectId}/classify`, { taskId: task.id }).catch(() => {
        // Classification failure is non-critical
      });
    },
  });

  return {
    createTask: mutation.mutate,
    isCreating: mutation.isPending,
  };
}
