import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';

/**
 * Iterate 14.7.0 — POST /api/projects/:id/tasks/:taskId/resume
 *
 * Spawns a new Claude CLI process with `--resume <claudeSessionId>` for
 * tasks that were interrupted by a server restart. Only valid when the
 * task's kanbanStatus is `interrupted`; server returns 404 otherwise.
 */
export function useResumeTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, taskId }: { projectId: string; taskId: string }) =>
      apiPost(`/projects/${projectId}/tasks/${taskId}/resume`, {}),
    onSuccess: (_data, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });
}
