import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, apiPost } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { InboxItem } from '../types';

export function useInbox() {
  return useQuery({
    queryKey: queryKeys.inbox.all,
    queryFn: () => apiFetch<InboxItem[]>('/inbox'),
  });
}

export function useInboxCount() {
  const { data } = useInbox();
  return data?.filter((item) => item.status === 'pending').length ?? 0;
}

export function useAnswerInbox() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, answer }: { id: string; answer: string }) =>
      apiPost<InboxItem>(`/inbox/${id}/answer`, { answer }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inbox.all });
    },
  });
}
