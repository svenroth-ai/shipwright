import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createElement } from 'react';
import { useSSE } from './useSSE';

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
