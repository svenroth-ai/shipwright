import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { ChatMessage } from '../types';

export function useChat(projectId: string, taskId: string) {
  return useQuery({
    queryKey: queryKeys.chat.byTask(projectId, taskId),
    queryFn: () => apiFetch<ChatMessage[]>(`/projects/${projectId}/chat/${taskId}`),
    enabled: !!projectId && !!taskId,
  });
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
      queryClient.invalidateQueries({
        queryKey: queryKeys.chat.byTask(variables.projectId, variables.taskId),
      });
    },
  });
}
