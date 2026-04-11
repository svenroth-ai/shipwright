import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { createElement } from 'react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/mocks/server';
import { useCreateTask } from './useCreateTask';

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

describe('useCreateTask', () => {
  it('creates task and triggers classify', async () => {
    let classifyCalled = false;

    server.use(
      http.post('/api/projects/:id/tasks', () =>
        HttpResponse.json({
          data: { id: 'new-task', projectId: 'p1', description: 'Test', status: 'pending', kanbanStatus: 'backlog', sessionId: 's1', createdAt: '', updatedAt: '' },
        }),
      ),
      http.post('/api/projects/:id/classify', () => {
        classifyCalled = true;
        return HttpResponse.json({ data: { success: true } });
      }),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCreateTask(), { wrapper });

    result.current.createTask({ projectId: 'p1', description: 'Test' });

    await waitFor(() => expect(result.current.isCreating).toBe(false));
    // Give fire-and-forget classify time to execute
    await waitFor(() => expect(classifyCalled).toBe(true), { timeout: 2000 });
  });

  it('handles classify failure gracefully', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    server.use(
      http.post('/api/projects/:id/tasks', () =>
        HttpResponse.json({
          data: { id: 'new-task', projectId: 'p1', description: 'Test', status: 'pending', kanbanStatus: 'backlog', sessionId: 's1', createdAt: '', updatedAt: '' },
        }),
      ),
      http.post('/api/projects/:id/classify', () =>
        HttpResponse.json({ error: 'Classification failed' }, { status: 500 }),
      ),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCreateTask(), { wrapper });

    result.current.createTask({ projectId: 'p1', description: 'Test' });

    // Task creation should succeed despite classify failure
    await waitFor(() => expect(result.current.isCreating).toBe(false));

    consoleSpy.mockRestore();
  });
});
