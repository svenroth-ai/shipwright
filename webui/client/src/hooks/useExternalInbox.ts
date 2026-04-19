import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dismissInboxItem, listInbox, type InboxItem } from "../lib/externalApi";

const KEY = ["external-inbox"] as const;

export function useExternalInbox() {
  return useQuery<InboxItem[]>({
    queryKey: KEY,
    queryFn: listInbox,
    refetchInterval: 3_000,
    refetchIntervalInBackground: false,
  });
}

export function useDismissInboxItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: dismissInboxItem,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
