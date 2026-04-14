import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { API_BASE } from '../lib/api';
import { mergeCommitted } from '../lib/mergeCommitted';
import { useTurnStatusStore, taskKeyOf, type TurnStatus } from '../stores/turnStatusStore';
import type { SSEEventType, ChatMessageSSEPayload } from '../types';
import type { ChatMessage } from '../types';

interface SSEPayload {
  projectId?: string;
  taskId?: string;
  [key: string]: unknown;
}

interface TaskUpdatedPayload extends SSEPayload {
  status?: string;
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

function isNewProtocol(): boolean {
  return (
    typeof import.meta !== 'undefined' &&
    import.meta.env?.VITE_SHIPWRIGHT_NEW_CHAT_PROTOCOL === '1'
  );
}

const TERMINAL_TASK_STATUSES = new Set(['done', 'failed', 'cancelled', 'archived']);

const WATCHDOG_STALE_MS = 15_000;
const WATCHDOG_STALLED_MS = 120_000;
const TASK_UPDATED_GRACE_MS = 1_500;

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
      // Iterate 13: when the new protocol is active, chat:message is handled
      // directly in the event listener via setQueryData + turn status store,
      // NOT through invalidation. When the old protocol is active we still
      // invalidate so the legacy useStreamingSSE / useStreamingChat path
      // keeps working. See plan vast-mapping-petal.md.
      if (!isNewProtocol() && projectId && taskId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.chat.byTask(projectId, taskId) });
      }
      break;
    case 'pipeline:updated':
      if (projectId) queryClient.invalidateQueries({ queryKey: queryKeys.pipeline.byProject(projectId) });
      break;
    case 'project:updated':
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
      break;
  }
}

function statusForMessage(msg: ChatMessage): TurnStatus | null {
  switch (msg.type) {
    case 'assistant':
    case 'thinking':
    case 'tool_use':
    case 'tool_result':
      return 'streaming';
    case 'result':
      return 'idle';
    case 'system':
      return 'awaiting_model';
    default:
      return null;
  }
}

export function handleChatMessagePayload(
  queryClient: ReturnType<typeof useQueryClient>,
  payload: ChatMessageSSEPayload,
  graceTimers: Map<string, ReturnType<typeof setTimeout>>,
): void {
  const { taskId, projectId, message } = payload;
  if (typeof message?.id !== 'string') return;

  queryClient.setQueryData<ChatMessage[]>(queryKeys.chat.byTask(projectId, taskId), (prev) =>
    mergeCommitted(prev, message),
  );

  const taskKey = taskKeyOf(projectId, taskId);
  const turn = useTurnStatusStore.getState();
  turn.recordEvent(taskKey, Date.now());

  const nextStatus = statusForMessage(message);
  if (nextStatus) {
    turn.setStatus(taskKey, nextStatus);
  }

  // A `result` message cancels any pending task:updated grace timer — the
  // stream completed cleanly, no need to force a stall.
  if (message.type === 'result') {
    const pending = graceTimers.get(taskKey);
    if (pending) {
      clearTimeout(pending);
      graceTimers.delete(taskKey);
    }
  }
}

export function handleTaskUpdatedForTurn(
  payload: TaskUpdatedPayload,
  graceTimers: Map<string, ReturnType<typeof setTimeout>>,
): void {
  const { projectId, taskId, status } = payload;
  if (!projectId || !taskId) return;
  if (!status || !TERMINAL_TASK_STATUSES.has(status)) return;

  const taskKey = taskKeyOf(projectId, taskId);
  const slot = useTurnStatusStore.getState().byTask[taskKey];
  // If no turn is active for this task we have nothing to grace-schedule.
  if (!slot || (slot.status !== 'streaming' && slot.status !== 'awaiting_model')) {
    return;
  }

  // Don't schedule duplicate timers.
  if (graceTimers.has(taskKey)) return;

  const timer = setTimeout(() => {
    graceTimers.delete(taskKey);
    const current = useTurnStatusStore.getState().byTask[taskKey];
    if (current && (current.status === 'streaming' || current.status === 'awaiting_model')) {
      useTurnStatusStore.getState().setStatus(taskKey, 'stalled');
    }
  }, TASK_UPDATED_GRACE_MS);

  graceTimers.set(taskKey, timer);
}

export function tickWatchdog(nowOverride?: number): void {
  const now = nowOverride ?? Date.now();
  const { byTask, markWatchdogStale, setStatus } = useTurnStatusStore.getState();
  for (const [taskKey, slot] of Object.entries(byTask)) {
    if (slot.status !== 'streaming') continue;
    const idle = now - slot.lastEventAt;
    if (idle >= WATCHDOG_STALLED_MS) {
      setStatus(taskKey, 'stalled');
    } else if (idle >= WATCHDOG_STALE_MS && !slot.watchdogStale) {
      markWatchdogStale(taskKey, true);
    }
  }
}

export function useSSE() {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(false);
  const graceTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    const es = new EventSource(`${API_BASE}/events`);
    const newProtocol = isNewProtocol();

    es.onopen = () => setIsConnected(true);
    es.onerror = () => setIsConnected(false);

    // Listen for each named SSE event type individually.
    // The server sends named events (event: chat:message, etc.) which
    // are NOT caught by onmessage — they require addEventListener.
    for (const eventType of SSE_EVENT_TYPES) {
      es.addEventListener(eventType, (event) => {
        try {
          const raw = JSON.parse((event as MessageEvent).data) as SSEPayload;

          if (eventType === 'chat:message' && newProtocol) {
            handleChatMessagePayload(
              queryClient,
              raw as unknown as ChatMessageSSEPayload,
              graceTimersRef.current,
            );
            return;
          }

          if (eventType === 'task:updated' && newProtocol) {
            handleTaskUpdatedForTurn(raw as TaskUpdatedPayload, graceTimersRef.current);
          }

          invalidateForEvent(queryClient, eventType, raw);
        } catch {
          // ignore malformed SSE data
        }
      });
    }

    const watchdogInterval = newProtocol ? window.setInterval(() => tickWatchdog(), 5_000) : null;

    return () => {
      es.close();
      setIsConnected(false);
      if (watchdogInterval !== null) window.clearInterval(watchdogInterval);
      for (const t of graceTimersRef.current.values()) clearTimeout(t);
      graceTimersRef.current.clear();
    };
  }, [queryClient]);

  return { isConnected };
}
