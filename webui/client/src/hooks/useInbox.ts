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

/**
 * Look up a single inbox item by id (typically the ChatMessage.toolUseId).
 * Returns undefined while loading or when no matching item exists. AskUserCard
 * uses this to hydrate its answered state from persisted server state on
 * mount, so refreshing the page keeps the "Answered" display. See ADR-018.
 */
export function useInboxItem(id: string | undefined): InboxItem | undefined {
  const { data } = useInbox();
  if (!id || !data) return undefined;
  return data.find((item) => item.id === id);
}

/**
 * Iterate 14.2 — `answers` is an array of `{ index, answer }` so the
 * UI can submit all parts of a multi-question AskUserQuestion in one
 * round-trip. The legacy `{ id, answer: string }` shape is still
 * accepted by the backend route (mapped to index: 0).
 */
export interface AnswerInboxArgs {
  id: string;
  answers: Array<{ index: number; answer: string }>;
}

export function useAnswerInbox() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, answers }: AnswerInboxArgs) =>
      apiPost<InboxItem>(`/inbox/${id}/answer`, { answers }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inbox.all });
    },
  });
}
