import { useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { ChatMessage } from '../types';

/**
 * Iterate 13: useChat is now a one-shot hydration query. Every live update
 * flows through useSSE's chat:message handler into the cache via
 * setQueryData + mergeCommitted. We explicitly disable every automatic
 * refetch path so the cache is only mutated by the SSE pipeline, the
 * user-message POST (useSendChat.onSuccess), and the explicit
 * useRefetchChatOnResume hook below.
 */
export function useChat(projectId: string, taskId: string) {
  return useQuery({
    queryKey: queryKeys.chat.byTask(projectId, taskId),
    queryFn: () => apiFetch<ChatMessage[]>(`/projects/${projectId}/chat/${taskId}`),
    enabled: !!projectId && !!taskId,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
  });
}

/**
 * Explicit resync: refetch committed chat history when external signals
 * suggest the SSE pipeline may have missed messages (network online event,
 * user returning after a reported stalled turn, panel mount after a
 * disconnect). Call this unconditionally from ChatPanel — it only binds
 * listeners, does not fire on every render.
 */
export function useRefetchChatOnResume(projectId: string, taskId: string) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!projectId || !taskId) return;
    const refetch = () => {
      queryClient.refetchQueries({
        queryKey: queryKeys.chat.byTask(projectId, taskId),
      });
    };
    window.addEventListener('online', refetch);
    return () => {
      window.removeEventListener('online', refetch);
    };
  }, [queryClient, projectId, taskId]);
}

interface SendChatParams {
  projectId: string;
  taskId: string;
  message: string;
  images?: Array<{ media_type: string; data: string }>;
  model?: string;
  mode?: string;
  effort?: string;
  autonomy?: string;
}

export function useSendChat() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, taskId, message, images, model, mode, effort, autonomy }: SendChatParams) =>
      apiPost(`/projects/${projectId}/chat`, { message, taskId, images, model, mode, effort, autonomy }),
    onSuccess: (_data, variables) => {
      // Refetch after the user's own message is persisted, so the user
      // message ChatMessage lands in the cache. This is the ONE place we
      // refetch chat.byTask outside of the one-shot hydration — it fires
      // once per user send, which is fine.
      queryClient.refetchQueries({
        queryKey: queryKeys.chat.byTask(variables.projectId, variables.taskId),
      });
    },
  });
}
