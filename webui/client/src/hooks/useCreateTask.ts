import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { useChatSettings } from './useChatSettings';

interface CreateTaskParams {
  projectId: string;
  title: string;
  description?: string;
  startImmediately?: boolean;
  phase?: string;
}

export function useCreateTask() {
  const queryClient = useQueryClient();
  const { mode, model } = useChatSettings();

  const mutation = useMutation({
    mutationFn: ({ projectId, title, description = '', startImmediately = true, phase }: CreateTaskParams) =>
      apiPost(`/projects/${projectId}/tasks`, {
        title,
        description,
        startImmediately,
        mode,
        model,
        ...(phase ? { phase } : {}),
      }),
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
