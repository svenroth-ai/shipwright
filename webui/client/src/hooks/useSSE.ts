import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { API_BASE } from '../lib/api';
import type { SSEEventType } from '../types';

interface SSEPayload {
  projectId?: string;
  taskId?: string;
  [key: string]: unknown;
}

function invalidateForEvent(
  queryClient: ReturnType<typeof useQueryClient>,
  type: SSEEventType,
  payload: SSEPayload,
) {
  const { projectId, taskId } = payload;

  switch (type) {
    case 'task:created':
      if (projectId) queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
      break;
    case 'task:updated':
      if (projectId) queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(projectId) });
      if (projectId && taskId) queryClient.invalidateQueries({ queryKey: queryKeys.tasks.detail(projectId, taskId) });
      break;
    case 'inbox:new':
    case 'inbox:answered':
      queryClient.invalidateQueries({ queryKey: queryKeys.inbox.all });
      break;
    case 'chat:message':
      if (projectId && taskId) queryClient.invalidateQueries({ queryKey: queryKeys.chat.byTask(projectId, taskId) });
      break;
    case 'pipeline:updated':
      if (projectId) queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.byProject(projectId) });
      break;
    case 'project:updated':
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
      break;
  }
}

export function useSSE() {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(`${API_BASE}/events`);

    es.onopen = () => setIsConnected(true);
    es.onerror = () => setIsConnected(false);

    es.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as { type: SSEEventType; payload: SSEPayload };
        invalidateForEvent(queryClient, parsed.type, parsed.payload);
      } catch {
        // ignore malformed SSE data
      }
    };

    return () => {
      es.close();
      setIsConnected(false);
    };
  }, [queryClient]);

  return { isConnected };
}
