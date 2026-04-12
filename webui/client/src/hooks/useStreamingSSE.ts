import { useEffect, useRef } from 'react';
import { API_BASE } from '../lib/api';
import type { NdjsonMessage } from '../types';

/**
 * Subscribes to SSE chat:message events for a specific task and invokes
 * the callback with each raw NDJSON message. Used by ChatPanel to feed
 * streaming messages into useStreamingChat's processNdjsonMessage.
 */
export function useStreamingSSE(
  taskId: string | null,
  onMessage: (taskId: string, msg: NdjsonMessage) => void,
  onStreamStart: () => void,
  onStreamEnd: () => void,
) {
  const streamingRef = useRef(false);
  const endTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!taskId) return;

    const es = new EventSource(`${API_BASE}/events`);

    es.addEventListener('chat:message', (event) => {
      try {
        const data = JSON.parse(event.data) as { taskId: string; message: NdjsonMessage };
        if (data.taskId !== taskId) return;

        const msg = data.message;
        if (!msg || typeof msg.type !== 'string') return;

        // Start streaming on first relevant message
        if (!streamingRef.current) {
          streamingRef.current = true;
          onStreamStart();
        }

        // Clear any pending end timer — more messages are coming
        if (endTimerRef.current) {
          clearTimeout(endTimerRef.current);
          endTimerRef.current = null;
        }

        onMessage(data.taskId, msg);

        // End streaming when we get a result or the process exits
        if (msg.type === 'result') {
          // Small delay to let React Query refetch persisted messages
          endTimerRef.current = setTimeout(() => {
            streamingRef.current = false;
            onStreamEnd();
          }, 500);
        }
      } catch {
        // Ignore malformed events
      }
    });

    // Also listen for task:updated which fires on process exit
    es.addEventListener('task:updated', (event) => {
      try {
        const data = JSON.parse(event.data) as { taskId?: string };
        if (data.taskId === taskId && streamingRef.current) {
          endTimerRef.current = setTimeout(() => {
            streamingRef.current = false;
            onStreamEnd();
          }, 500);
        }
      } catch {
        // Ignore
      }
    });

    return () => {
      es.close();
      if (endTimerRef.current) clearTimeout(endTimerRef.current);
      streamingRef.current = false;
    };
  }, [taskId, onMessage, onStreamStart, onStreamEnd]);
}
