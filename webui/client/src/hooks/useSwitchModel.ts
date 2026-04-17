import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';

/**
 * Iterate 14.12 — mid-task model switching.
 *
 * Companion to {@link useChangeMode}. Fires
 * `POST /api/projects/:projectId/tasks/:taskId/mode` with `{ model }` so
 * the server SIGTERMs the running Claude process and respawns it with
 * `--resume <sessionId>` plus `--model <id>`, preserving the conversation.
 *
 * Iterate 14.13 — bug fix. 14.12 sent the COARSE family alias
 * (`opus`/`sonnet`/`haiku`) by passing the concrete id through
 * `aliasFromConcrete()` first. The CLI's `opus` alias resolves to whatever
 * the CLI considers the latest stable opus (4.5 / 4.6 in CLI 2.1.1),
 * NOT the concrete id the user picked — so picking Opus 4.7 silently
 * landed on 4.5 and the ModelSelector "stayed" at the wrong version once
 * the new system/init arrived. Now sends the concrete id directly: per
 * `claude --help`, `--model` accepts both alias and full name forms.
 *
 * Server returns 409 when:
 *   - The Claude session_id hasn't been captured yet (process just spawned)
 *   - There is a pending AskUserQuestion in the inbox for this task
 *
 * Returns 400 when the model field is empty / non-string / shell-unsafe.
 */
export function useSwitchModel(projectId: string, taskId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (concreteModelId: string) => {
      return apiPost(`/projects/${projectId}/tasks/${taskId}/mode`, { model: concreteModelId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });
}
