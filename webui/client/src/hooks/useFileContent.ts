import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';

export function useFileContent(projectId: string, filePath: string, enabled = true) {
  return useQuery({
    queryKey: ['file-content', projectId, filePath],
    queryFn: () => apiFetch<string>(`/projects/${projectId}/docs?path=${encodeURIComponent(filePath)}`),
    enabled: enabled && !!filePath && !!projectId,
    staleTime: 30_000,
  });
}
