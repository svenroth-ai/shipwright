import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/mocks/server';
import { useSwitchModel } from './useSwitchModel';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useSwitchModel', () => {
  it('POSTs to /api/projects/:id/tasks/:taskId/mode with the alias derived from the concrete id', async () => {
    let receivedBody: Record<string, unknown> | null = null;
    let receivedUrl: string | null = null;

    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', async ({ request }) => {
        receivedUrl = request.url;
        receivedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ data: { taskId: 'task-1', model: 'opus', status: 'running' } });
      }),
    );

    const { result } = renderHook(() => useSwitchModel('proj-1', 'task-1'), {
      wrapper: createWrapper(),
    });

    result.current.mutate('claude-opus-4-7');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(receivedUrl).toContain('/api/projects/proj-1/tasks/task-1/mode');
    expect(receivedBody).toEqual({ model: 'opus' });
  });

  it('maps Sonnet concrete id to sonnet alias', async () => {
    let receivedBody: Record<string, unknown> | null = null;

    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ data: { taskId: 'task-1', model: 'sonnet', status: 'running' } });
      }),
    );

    const { result } = renderHook(() => useSwitchModel('proj-1', 'task-1'), {
      wrapper: createWrapper(),
    });

    result.current.mutate('claude-sonnet-4-6');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(receivedBody).toEqual({ model: 'sonnet' });
  });

  it('surfaces server 409 errors (e.g. pending question) as a mutation failure', async () => {
    server.use(
      http.post('/api/projects/:projectId/tasks/:taskId/mode', () =>
        HttpResponse.json(
          { error: 'Answer the pending question before switching mode' },
          { status: 409 },
        ),
      ),
    );

    const { result } = renderHook(() => useSwitchModel('proj-1', 'task-1'), {
      wrapper: createWrapper(),
    });

    result.current.mutate('claude-opus-4-7');

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
