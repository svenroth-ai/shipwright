import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { API_BASE } from '../lib/api';
import { mergeCommitted } from '../lib/mergeCommitted';
import { useTurnStatusStore, taskKeyOf, type TurnStatus } from '../stores/turnStatusStore';
import type { SSEEventType, ChatMessageSSEPayload } from '../types';
import type { ChatMessage } from '../types';
import type { InboxItem } from '../types/inbox';

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
  'inbox:flag_not_blocked',
  'chat:message',
  'pipeline:updated',
  'project:updated',
];

interface InboxFlagNotBlockedSSEPayload extends SSEPayload {
  inboxItemId: string;
  toolUseId: string;
  reason: 'continued' | 'turn_ended';
}

/**
 * Iterate 14.5 — patches the inbox query cache when the server reports
 * that Claude continued generating after an AskUserQuestion. Marks the
 * matching InboxItem as `notBlocked: true` in place so `useInboxItem()`
 * (and AskUserCard via that hook) immediately re-renders with the amber
 * warning banner. Falls back to a cache invalidation if the item isn't
 * in the cache yet (rare — inbox is fetched on mount, so it usually is).
 */
export function handleInboxFlagNotBlocked(
  queryClient: ReturnType<typeof useQueryClient>,
  payload: InboxFlagNotBlockedSSEPayload,
): void {
  const { inboxItemId } = payload;
  if (!inboxItemId) return;

  let patched = false;
  queryClient.setQueryData<InboxItem[]>(queryKeys.inbox.all, (prev) => {
    if (!prev) return prev;
    let changed = false;
    const next = prev.map((item) => {
      if (item.id === inboxItemId && item.notBlocked !== true) {
        changed = true;
        return { ...item, notBlocked: true };
      }
      return item;
    });
    if (changed) patched = true;
    return changed ? next : prev;
  });

  // Defensive fallback: if the cache didn't contain the item we refetch
  // so the next render still picks up the flag.
  if (!patched) {
    queryClient.invalidateQueries({ queryKey: queryKeys.inbox.all });
  }
}

const TERMINAL_TASK_STATUSES = new Set(['done', 'failed', 'cancelled', 'archived']);

const WATCHDOG_STALE_MS = 15_000;
const WATCHDOG_STALLED_MS = 120_000;
const TASK_UPDATED_GRACE_MS = 1_500;
const WATCHDOG_TICK_MS = 5_000;

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
      // Kanban board
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
      break;
    case 'inbox:new':
    case 'inbox:answered':
    case 'inbox:flag_not_blocked':
      queryClient.invalidateQueries({ queryKey: queryKeys.inbox.all });
      break;
    case 'chat:message':
      // Iterate 13: chat:message is handled directly in the event listener
      // via setQueryData + mergeCommitted. No invalidation — that was the
      // root cause of the mid-turn flip-flop (see plan vast-mapping-petal.md).
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

  // result cancels any pending task:updated grace timer — the stream
  // completed cleanly, no forced stall.
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
  if (!slot || (slot.status !== 'streaming' && slot.status !== 'awaiting_model')) {
    return;
  }
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
  const wasConnectedRef = useRef(false);

  useEffect(() => {
    const es = new EventSource(`${API_BASE}/events`);
    const graceTimers = graceTimersRef.current;

    es.onopen = () => {
      setIsConnected(true);
      // Reconnect resync: if we were connected before, the SSE pipeline just
      // recovered from an interruption. Refetch any active chat query so the
      // cache catches up with anything that may have been missed.
      if (wasConnectedRef.current) {
        queryClient.refetchQueries({ queryKey: ['chat'] });
      }
      wasConnectedRef.current = true;
    };
    es.onerror = () => setIsConnected(false);

    for (const eventType of SSE_EVENT_TYPES) {
      es.addEventListener(eventType, (event) => {
        try {
          const raw = JSON.parse((event as MessageEvent).data) as SSEPayload;

          if (eventType === 'chat:message') {
            handleChatMessagePayload(
              queryClient,
              raw as unknown as ChatMessageSSEPayload,
              graceTimers,
            );
            return;
          }

          if (eventType === 'inbox:flag_not_blocked') {
            handleInboxFlagNotBlocked(
              queryClient,
              raw as InboxFlagNotBlockedSSEPayload,
            );
            return;
          }

          if (eventType === 'task:updated') {
            handleTaskUpdatedForTurn(raw as TaskUpdatedPayload, graceTimers);
          }

          invalidateForEvent(queryClient, eventType, raw);
        } catch {
          // ignore malformed SSE data
        }
      });
    }

    const watchdogInterval = window.setInterval(() => tickWatchdog(), WATCHDOG_TICK_MS);

    return () => {
      es.close();
      setIsConnected(false);
      window.clearInterval(watchdogInterval);
      for (const t of graceTimers.values()) clearTimeout(t);
      graceTimers.clear();
    };
  }, [queryClient]);

  return { isConnected };
}
