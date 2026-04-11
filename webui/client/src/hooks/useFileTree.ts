import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';

export interface FileTreeNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileTreeNode[];
  gitStatus?: string;
}

export function useFileTree(projectId: string) {
  return useQuery({
    queryKey: ['file-tree', projectId],
    queryFn: () => apiFetch<FileTreeNode[]>(`/projects/${projectId}/docs?mode=tree`),
    enabled: !!projectId,
    staleTime: 30_000,
  });
}
