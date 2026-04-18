import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/mocks/server';
import { useResumeTask } from './useResumeTask';
import { useChatStore } from '../stores/chatStore';
import { taskKeyOf } from '../stores/turnStatusStore';

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: qc }, children),
    queryClient: qc,
  };
}

describe('useResumeTask — iterate modelswitch-uat-round2', () => {
  it('clears systemInit on mutate so the spawn indicator fires on resume', async () => {
    const taskKey = taskKeyOf('p1', 't1');
    useChatStore.setState({
      systemInitByTask: {
        [taskKey]: { model: 'claude-opus-4-7' },
      },
    });
    expect(useChatStore.getState().systemInitByTask[taskKey]).toBeDefined();

    server.use(
      http.post('/api/projects/:id/tasks/:taskId/resume', () =>
        HttpResponse.json({ data: { taskId: 't1', status: 'running' } }),
      ),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useResumeTask(), { wrapper });
    result.current.mutate({ projectId: 'p1', taskId: 't1' });

    // onMutate runs synchronously before the HTTP request — systemInit
    // should be cleared immediately.
    await waitFor(() => {
      expect(useChatStore.getState().systemInitByTask[taskKey]).toBeUndefined();
    });

    await waitFor(() => expect(result.current.isPending).toBe(false));
  });

  it('clearSystemInit is only called for the specific taskKey, not others', async () => {
    useChatStore.setState({
      systemInitByTask: {
        'p1::t-keep': { model: 'claude-sonnet-4-6' },
        'p1::t-clear': { model: 'claude-opus-4-7' },
      },
    });

    server.use(
      http.post('/api/projects/:id/tasks/:taskId/resume', () =>
        HttpResponse.json({ data: {} }),
      ),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useResumeTask(), { wrapper });
    result.current.mutate({ projectId: 'p1', taskId: 't-clear' });

    await waitFor(() => {
      expect(useChatStore.getState().systemInitByTask['p1::t-clear']).toBeUndefined();
    });
    // Other task's systemInit stays intact.
    expect(useChatStore.getState().systemInitByTask['p1::t-keep']?.model).toBe('claude-sonnet-4-6');
  });
});
