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

const SSE_EVENT_TYPES: SSEEventType[] = [
  'task:created',
  'task:updated',
  'inbox:new',
  'inbox:answered',
  'chat:message',
  'pipeline:updated',
  'project:updated',
];

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
      // Also invalidate the all-tasks query so kanban board updates
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
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

    // Listen for each named SSE event type individually.
    // The server sends named events (event: chat:message, etc.) which
    // are NOT caught by onmessage — they require addEventListener.
    for (const eventType of SSE_EVENT_TYPES) {
      es.addEventListener(eventType, (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent).data) as SSEPayload;
          invalidateForEvent(queryClient, eventType, payload);
        } catch {
          // ignore malformed SSE data
        }
      });
    }

    return () => {
      es.close();
      setIsConnected(false);
    };
  }, [queryClient]);

  return { isConnected };
}
