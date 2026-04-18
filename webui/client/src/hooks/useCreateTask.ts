import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { useChatSettings } from './useChatSettings';
import { useSettings } from './useSettings';

interface CreateTaskParams {
  projectId: string;
  title: string;
  description?: string;
  startImmediately?: boolean;
  phase?: string;
}

/**
 * Iterate modelswitch-uat-round2 (2026-04-18) — new-task model precedence.
 *
 * Model field for new-task creation reads from `settings.defaultModel`
 * directly, NOT from `useChatSettings.model` (localStorage). Reason: the
 * localStorage model tracks the LAST mid-task ModelSelector pick, which
 * is a session-scoped override for chat-send purposes. New tasks must
 * honor the global Settings default instead — otherwise switching a
 * single task to Opus 4.6 persistently biases every subsequent new task
 * away from the user's configured default (4.7).
 *
 * Fallback order: settings.defaultModel → useChatSettings.model (legacy
 * fallback if settings hasn't loaded yet) → undefined (server applies
 * its own fallback). Mode + autonomy still come from chat settings /
 * project settings; only model is affected by this rule.
 */
export function useCreateTask() {
  const queryClient = useQueryClient();
  const { mode, model: legacyModel } = useChatSettings();
  const { data: settings } = useSettings();

  const model = settings?.defaultModel ?? legacyModel;

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
