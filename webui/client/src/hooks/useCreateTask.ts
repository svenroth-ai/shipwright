import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';

interface CreateTaskParams {
  projectId: string;
  title: string;
  description?: string;
  startImmediately?: boolean;
}

export function useCreateTask() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: ({ projectId, title, description = '', startImmediately = true }: CreateTaskParams) =>
      apiPost(`/projects/${projectId}/tasks`, { title, description, startImmediately }),
    onSuccess: (_data, variables) => {
      // Always invalidate using the variables (reliable) not the response
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(variables.projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });

      // Fire-and-forget classification
      apiPost(`/projects/${variables.projectId}/classify`, { taskId: (_data as { id?: string })?.id }).catch(() => {
        // Classification failure is non-critical
      });
    },
  });

  return {
    createTask: mutation.mutate,
    isCreating: mutation.isPending,
  };
}
