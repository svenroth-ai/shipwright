import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { aliasFromConcrete } from '../components/chat/ModelSelector';

/**
 * Iterate 14.12 — mid-task model switching.
 *
 * Companion to {@link useChangeMode}. Fires
 * `POST /api/projects/:projectId/tasks/:taskId/mode` with `{ model }` (the
 * coarse alias `opus`/`sonnet`/`haiku` derived from the concrete CLI id the
 * user picked in `ModelSelector`). The server SIGTERMs the running Claude
 * process and respawns it with `--resume <sessionId>` plus
 * `--model <alias>`, preserving the full conversation history.
 *
 * This existed as a TODO comment in 14.8.3's ChatToolbar. Iterate 14.12
 * implements it: clicking a different model in the ModelSelector dropdown
 * now actually switches the running Claude process to that model.
 *
 * Server returns 409 when:
 *   - The Claude session_id hasn't been captured yet (process just spawned)
 *   - There is a pending AskUserQuestion in the inbox for this task
 *
 * Returns 400 when the alias maps to nothing valid (defence in depth — the
 * concrete-to-alias map covers every model in `KNOWN_MODELS`).
 */
export function useSwitchModel(projectId: string, taskId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (concreteModelId: string) => {
      const alias = aliasFromConcrete(concreteModelId);
      return apiPost(`/projects/${projectId}/tasks/${taskId}/mode`, { model: alias });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });
}
