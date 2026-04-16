import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';

/**
 * Iterate 14.8.3 — user-initiated task interrupt via Stop button.
 *
 * Fires `POST /api/projects/:projectId/tasks/:taskId/interrupt` which
 * terminates the running Claude process and emits a `task_orphaned` event
 * with detail `user_interrupted`. The task becomes resumable via the
 * existing Resume action (same path as stale_on_startup in 14.7.0).
 */
export function useInterruptTask(projectId: string, taskId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiPost(`/projects/${projectId}/tasks/${taskId}/interrupt`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });
}
