import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { useChatStore } from '../stores/chatStore';
import { taskKeyOf } from '../stores/turnStatusStore';

/**
 * Iterate 14.7.0 — POST /api/projects/:id/tasks/:taskId/resume
 *
 * Spawns a new Claude CLI process with `--resume <claudeSessionId>` for
 * tasks that were interrupted by a server restart, user Stop action, or
 * (per iterate modelswitch-uat-round2) a failed mid-task mode/model
 * switch respawn.
 *
 * Iterate modelswitch-uat-round2 (2026-04-18) — on mutate, clear the
 * chatStore's cached `system/init` for this task. Rationale: the task's
 * previous CLI process already emitted a `system/init` which hydrated
 * the store during the earlier session. After resume, a fresh CLI
 * process will emit a NEW `system/init`. Without clearing, `awaitingInit`
 * in `ChatPanel` stays false (systemInit is truthy) and the user never
 * sees "Starting Claude…" during the 1–2s resume-boot gap. Clearing on
 * mutate makes the spawn indicator render for resumes the same way it
 * renders for fresh task creation.
 */
export function useResumeTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, taskId }: { projectId: string; taskId: string }) =>
      apiPost(`/projects/${projectId}/tasks/${taskId}/resume`, {}),
    onMutate: ({ projectId, taskId }) => {
      useChatStore.getState().clearSystemInit(taskKeyOf(projectId, taskId));
    },
    onSuccess: (_data, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });
}
