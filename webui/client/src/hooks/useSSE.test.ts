import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createElement } from 'react';
import {
  useSSE,
  handleChatMessagePayload,
  handleTaskUpdatedForTurn,
  tickWatchdog,
} from './useSSE';
import { useTurnStatusStore, taskKeyOf } from '../stores/turnStatusStore';
import { queryKeys } from '../lib/queryKeys';
import type { ChatMessage } from '../types';

let mockEventSource: {
  onopen: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  close: ReturnType<typeof vi.fn>;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
  _listeners: Map<string, Array<(event: MessageEvent) => void>>;
};

function fireNamedEvent(type: string, payload: unknown) {
  const listeners = mockEventSource._listeners.get(type) ?? [];
  const event = new MessageEvent(type, { data: JSON.stringify(payload) });
  for (const listener of listeners) {
    listener(event);
  }
}

beforeEach(() => {
  const listeners = new Map<string, Array<(event: MessageEvent) => void>>();
  mockEventSource = {
    onopen: null,
    onerror: null,
    onmessage: null,
    close: vi.fn(),
    addEventListener: vi.fn((type: string, handler: (event: MessageEvent) => void) => {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type)!.push(handler);
    }),
    removeEventListener: vi.fn(),
    _listeners: listeners,
  };

  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => mockEventSource));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children),
    queryClient,
  };
}

describe('useSSE', () => {
  it('creates EventSource connection', () => {
    const { wrapper } = createWrapper();
    renderHook(() => useSSE(), { wrapper });

    expect(EventSource).toHaveBeenCalledWith('/api/events');
  });

  it('tracks connection state', () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useSSE(), { wrapper });

    expect(result.current.isConnected).toBe(false);

    act(() => {
      mockEventSource.onopen?.(new Event('open'));
    });

    expect(result.current.isConnected).toBe(true);
  });

  it('registers addEventListener for each SSE event type', () => {
    const { wrapper } = createWrapper();
    renderHook(() => useSSE(), { wrapper });

    expect(mockEventSource.addEventListener).toHaveBeenCalledWith('task:created', expect.any(Function));
    expect(mockEventSource.addEventListener).toHaveBeenCalledWith('chat:message', expect.any(Function));
    expect(mockEventSource.addEventListener).toHaveBeenCalledWith('inbox:new', expect.any(Function));
  });

  it('invalidates task queries on task:created event', () => {
    const { wrapper, queryClient } = createWrapper();
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    renderHook(() => useSSE(), { wrapper });

    act(() => {
      fireNamedEvent('task:created', { projectId: 'proj-1' });
    });

    expect(spy).toHaveBeenCalled();
  });

  it('invalidates inbox queries on inbox:new event', () => {
    const { wrapper, queryClient } = createWrapper();
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    renderHook(() => useSSE(), { wrapper });

    act(() => {
      fireNamedEvent('inbox:new', { projectId: 'proj-1', taskId: 'task-1' });
    });

    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['inbox'] }),
    );
  });

  it('closes EventSource on unmount', () => {
    const { wrapper } = createWrapper();
    const { unmount } = renderHook(() => useSSE(), { wrapper });

    unmount();
    expect(mockEventSource.close).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Iterate 13 / Step 4: new chat-message handler tests (NEW_PROTOCOL path)
// The handlers are exported so they can be tested in isolation without
// wiring up the full effect + env flag plumbing.
// ---------------------------------------------------------------------------

const PID = 'p1';
const TID = 't1';
const TASK_KEY = taskKeyOf(PID, TID);

function chatMsg(id: string, type: ChatMessage['type'] = 'assistant', content = `c-${id}`): ChatMessage {
  return { id, taskId: TID, type, content, timestamp: '2026-04-14T10:00:00.000Z' };
}

function freshClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function resetTurnStore() {
  useTurnStatusStore.setState({ byTask: {} });
}

describe('handleChatMessagePayload', () => {
  let client: QueryClient;
  let timers: Map<string, ReturnType<typeof setTimeout>>;

  beforeEach(() => {
    resetTurnStore();
    client = freshClient();
    timers = new Map();
  });

  it('merges the message into the chat query cache via setQueryData', () => {
    const m = chatMsg('a', 'assistant');
    handleChatMessagePayload(client, { taskId: TID, projectId: PID, message: m }, timers);
    const cached = client.getQueryData<ChatMessage[]>(queryKeys.chat.byTask(PID, TID));
    expect(cached).toEqual([m]);
  });

  it('never calls invalidateQueries on chat.byTask across a full turn', () => {
    const spy = vi.spyOn(client, 'invalidateQueries');
    const sequence: ChatMessage[] = [
      chatMsg('m-1', 'assistant'),
      chatMsg('m-2', 'thinking'),
      chatMsg('m-3', 'tool_use'),
      chatMsg('m-4', 'tool_result'),
      chatMsg('m-5', 'result'),
    ];
    for (const m of sequence) {
      handleChatMessagePayload(client, { taskId: TID, projectId: PID, message: m }, timers);
    }
    expect(spy).not.toHaveBeenCalled();
  });

  it('grows the cache monotonically across a 12-event sequence', () => {
    const lengths: number[] = [];
    for (let i = 0; i < 12; i++) {
      handleChatMessagePayload(
        client,
        {
          taskId: TID,
          projectId: PID,
          message: {
            id: `m-${i}`,
            taskId: TID,
            type: 'assistant',
            content: `t${i}`,
            timestamp: `2026-04-14T10:${String(i).padStart(2, '0')}:00.000Z`,
          },
        },
        timers,
      );
      const cached = client.getQueryData<ChatMessage[]>(queryKeys.chat.byTask(PID, TID)) ?? [];
      lengths.push(cached.length);
    }
    expect(lengths).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  });

  it('transitions turn status to streaming on assistant / thinking / tool_use / tool_result', () => {
    for (const t of ['assistant', 'thinking', 'tool_use', 'tool_result'] as const) {
      resetTurnStore();
      handleChatMessagePayload(
        client,
        { taskId: TID, projectId: PID, message: chatMsg(`x-${t}`, t) },
        timers,
      );
      expect(useTurnStatusStore.getState().byTask[TASK_KEY]?.status).toBe('streaming');
    }
  });

  it('transitions to idle on result', () => {
    handleChatMessagePayload(client, { taskId: TID, projectId: PID, message: chatMsg('a', 'assistant') }, timers);
    handleChatMessagePayload(client, { taskId: TID, projectId: PID, message: chatMsg('r', 'result') }, timers);
    expect(useTurnStatusStore.getState().byTask[TASK_KEY]?.status).toBe('idle');
  });

  it('records lastEventAt on each message', () => {
    handleChatMessagePayload(client, { taskId: TID, projectId: PID, message: chatMsg('a', 'assistant') }, timers);
    expect(useTurnStatusStore.getState().byTask[TASK_KEY].lastEventAt).toBeGreaterThan(0);
  });

  it('ignores messages with a non-string id', () => {
    handleChatMessagePayload(
      client,
      {
        taskId: TID,
        projectId: PID,
        message: { ...chatMsg('a'), id: undefined as unknown as string },
      },
      timers,
    );
    expect(client.getQueryData(queryKeys.chat.byTask(PID, TID))).toBeUndefined();
  });

  it('result cancels a pending task:updated grace timer', () => {
    vi.useFakeTimers();
    try {
      useTurnStatusStore.getState().setStatus(TASK_KEY, 'streaming');
      handleTaskUpdatedForTurn({ projectId: PID, taskId: TID, status: 'done' }, timers);
      expect(timers.has(TASK_KEY)).toBe(true);

      handleChatMessagePayload(
        client,
        { taskId: TID, projectId: PID, message: chatMsg('r', 'result') },
        timers,
      );
      expect(timers.has(TASK_KEY)).toBe(false);

      vi.advanceTimersByTime(2_000);
      expect(useTurnStatusStore.getState().byTask[TASK_KEY]?.status).toBe('idle');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('handleTaskUpdatedForTurn', () => {
  let timers: Map<string, ReturnType<typeof setTimeout>>;

  beforeEach(() => {
    resetTurnStore();
    timers = new Map();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('schedules a 1500ms grace timer when a streaming task goes terminal', () => {
    useTurnStatusStore.getState().setStatus(TASK_KEY, 'streaming');
    handleTaskUpdatedForTurn({ projectId: PID, taskId: TID, status: 'done' }, timers);

    expect(timers.has(TASK_KEY)).toBe(true);
    expect(useTurnStatusStore.getState().byTask[TASK_KEY]?.status).toBe('streaming');

    vi.advanceTimersByTime(1_500);
    expect(useTurnStatusStore.getState().byTask[TASK_KEY]?.status).toBe('stalled');
  });

  it('does not schedule a timer when the task has no active turn', () => {
    handleTaskUpdatedForTurn({ projectId: PID, taskId: TID, status: 'done' }, timers);
    expect(timers.has(TASK_KEY)).toBe(false);
  });

  it('ignores non-terminal task updates', () => {
    useTurnStatusStore.getState().setStatus(TASK_KEY, 'streaming');
    handleTaskUpdatedForTurn({ projectId: PID, taskId: TID, status: 'running' }, timers);
    expect(timers.has(TASK_KEY)).toBe(false);
  });

  it('does not schedule duplicate timers for the same task', () => {
    useTurnStatusStore.getState().setStatus(TASK_KEY, 'streaming');
    handleTaskUpdatedForTurn({ projectId: PID, taskId: TID, status: 'done' }, timers);
    const firstTimer = timers.get(TASK_KEY);
    handleTaskUpdatedForTurn({ projectId: PID, taskId: TID, status: 'done' }, timers);
    expect(timers.get(TASK_KEY)).toBe(firstTimer);
  });

  it('does not flip to stalled if the turn is no longer streaming when the timer fires', () => {
    useTurnStatusStore.getState().setStatus(TASK_KEY, 'streaming');
    handleTaskUpdatedForTurn({ projectId: PID, taskId: TID, status: 'done' }, timers);
    useTurnStatusStore.getState().setStatus(TASK_KEY, 'idle');

    vi.advanceTimersByTime(1_500);
    expect(useTurnStatusStore.getState().byTask[TASK_KEY]?.status).toBe('idle');
  });
});

describe('tickWatchdog', () => {
  beforeEach(resetTurnStore);

  it('flips streaming tasks to watchdogStale after 15s of silence', () => {
    const now = 100_000;
    useTurnStatusStore.getState().setStatus(TASK_KEY, 'streaming');
    useTurnStatusStore.getState().recordEvent(TASK_KEY, now - 16_000);

    tickWatchdog(now);

    const slot = useTurnStatusStore.getState().byTask[TASK_KEY];
    expect(slot.watchdogStale).toBe(true);
    expect(slot.status).toBe('streaming');
  });

  it('flips streaming tasks to stalled after 120s of silence', () => {
    const now = 200_000;
    useTurnStatusStore.getState().setStatus(TASK_KEY, 'streaming');
    useTurnStatusStore.getState().recordEvent(TASK_KEY, now - 121_000);

    tickWatchdog(now);

    expect(useTurnStatusStore.getState().byTask[TASK_KEY]?.status).toBe('stalled');
  });

  it('does not touch non-streaming tasks', () => {
    const now = 300_000;
    useTurnStatusStore.getState().setStatus(TASK_KEY, 'awaiting_user');
    useTurnStatusStore.getState().recordEvent(TASK_KEY, now - 200_000);

    tickWatchdog(now);

    expect(useTurnStatusStore.getState().byTask[TASK_KEY]?.status).toBe('awaiting_user');
  });

  it('is safe when no tasks are in the store', () => {
    expect(() => tickWatchdog(Date.now())).not.toThrow();
  });
});
