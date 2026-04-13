import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, apiPost } from '../lib/api';

export type CliCapability = {
  name: 'claude';
  available: boolean;
  version?: string;
  path?: string;
  error?: string;
  checkedAt: string;
};

type CapabilitiesResponse = { cli: CliCapability };

export function useCliCapability() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['capabilities'],
    queryFn: () => apiFetch<CapabilitiesResponse>('/capabilities'),
    staleTime: 60_000,
  });

  const refreshMutation = useMutation({
    mutationFn: () => apiPost<CapabilitiesResponse>('/capabilities/refresh', {}),
    onSuccess: (data) => {
      queryClient.setQueryData(['capabilities'], data);
    },
  });

  return {
    cli: query.data?.cli,
    isLoading: query.isLoading,
    refresh: () => refreshMutation.mutate(),
    isRefreshing: refreshMutation.isPending,
  };
}
