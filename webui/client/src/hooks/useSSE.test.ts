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
};

beforeEach(() => {
  mockEventSource = {
    onopen: null,
    onerror: null,
    onmessage: null,
    close: vi.fn(),
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

  it('invalidates task queries on task:created event', () => {
    const { wrapper, queryClient } = createWrapper();
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    renderHook(() => useSSE(), { wrapper });

    act(() => {
      mockEventSource.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'task:created',
            payload: { projectId: 'proj-1' },
          }),
        }),
      );
    });

    expect(spy).toHaveBeenCalled();
  });

  it('invalidates inbox queries on inbox:new event', () => {
    const { wrapper, queryClient } = createWrapper();
    const spy = vi.spyOn(queryClient, 'invalidateQueries');

    renderHook(() => useSSE(), { wrapper });

    act(() => {
      mockEventSource.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'inbox:new',
            payload: { projectId: 'proj-1', taskId: 'task-1' },
          }),
        }),
      );
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
