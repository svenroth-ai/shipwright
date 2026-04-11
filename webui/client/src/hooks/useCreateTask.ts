import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { Task } from '../types';

interface CreateTaskParams {
  projectId: string;
  description: string;
}

export function useCreateTask() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: ({ projectId, description }: CreateTaskParams) =>
      apiPost<Task>(`/projects/${projectId}/tasks`, { description }),
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
