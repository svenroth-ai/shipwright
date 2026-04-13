import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { ModeOption } from './useChatSettings';

/**
 * Iterate 10 — mid-task permission mode switching.
 *
 * Fires `POST /api/projects/:projectId/tasks/:taskId/mode` which SIGTERMs
 * the running Claude process, then respawns it with `--resume <sessionId>`
 * and the new `--permission-mode` flag. Takes ~2-3s (one cold start) but
 * preserves the full conversation history because chat-history.jsonl is
 * per-task, not per-process, and Claude resumes by its real session_id
 * captured from the previous process's system/init event.
 *
 * Server returns 409 when:
 *   - The Claude session_id hasn't been captured yet (process just spawned)
 *   - There is a pending AskUserQuestion in the inbox for this task
 *
 * Callers should surface the 409 error message to the user so they know
 * whether to retry in a moment or answer the pending question first.
 */
export function useChangeMode(projectId: string, taskId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (mode: ModeOption) =>
      apiPost(`/projects/${projectId}/tasks/${taskId}/mode`, { mode }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });
}
