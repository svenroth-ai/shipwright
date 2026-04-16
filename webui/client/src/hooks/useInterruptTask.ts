import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { useTurnStatusStore, taskKeyOf } from '../stores/turnStatusStore';

/**
 * Iterate 14.8.3 — user-initiated task interrupt via Stop button.
 *
 * Fires `POST /api/projects/:projectId/tasks/:taskId/interrupt` which
 * terminates the running Claude process and emits a `task_orphaned` event
 * with detail `user_interrupted`. The task becomes resumable via the
 * existing Resume action (same path as stale_on_startup in 14.7.0).
 *
 * Iterate 14.9 (Bug F2): on success, flip the local turnStatusStore
 * slot back to `idle` immediately. The SSE task:updated broadcast also
 * carries status="orphaned" which the watchdog will eventually pick up,
 * but resetting locally avoids the 1.5s grace-timer window during which
 * ChatInput would otherwise keep showing the red Stop button.
 */
export function useInterruptTask(projectId: string, taskId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiPost(`/projects/${projectId}/tasks/${taskId}/interrupt`, {}),
    onSuccess: () => {
      useTurnStatusStore.getState().setStatus(taskKeyOf(projectId, taskId), 'idle');
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });
}
