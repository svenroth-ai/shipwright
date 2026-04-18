import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createElement } from 'react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/mocks/server';
import { useCreateTask } from './useCreateTask';

beforeEach(() => localStorage.clear());

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
          data: { id: 'new-task', projectId: 'p1', title: 'Test', description: 'Test', status: 'pending', kanbanStatus: 'backlog', sessionId: 's1', createdAt: '', updatedAt: '' },
        }),
      ),
      http.post('/api/projects/:id/classify', () => {
        classifyCalled = true;
        return HttpResponse.json({ data: { success: true } });
      }),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCreateTask(), { wrapper });

    result.current.createTask({ projectId: 'p1', title: 'Test' });

    await waitFor(() => expect(result.current.isCreating).toBe(false));
    // Give fire-and-forget classify time to execute
    await waitFor(() => expect(classifyCalled).toBe(true), { timeout: 2000 });
  });

  it('iterate modelswitch-uat-round2 — settings.defaultModel wins over localStorage chat-model', async () => {
    // Reproduction of Finding 2: user had switched mid-task to Opus 4.6
    // (persisted to localStorage), then created a new task. Expectation:
    // new task uses settings.defaultModel (4.7), not the session-scoped
    // localStorage override (4.6).
    localStorage.setItem('chat-model', JSON.stringify('claude-opus-4-6'));
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.get('/api/settings', () =>
        HttpResponse.json({ data: { defaultModel: 'claude-opus-4-7' } }),
      ),
      http.post('/api/projects/:id/tasks', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          data: { id: 'new-task', projectId: 'p1', title: 'T', description: '', status: 'pending', kanbanStatus: 'backlog', sessionId: 's', createdAt: '', updatedAt: '' },
        });
      }),
      http.post('/api/projects/:id/classify', () =>
        HttpResponse.json({ data: { success: true } }),
      ),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCreateTask(), { wrapper });

    // Wait for settings query to land.
    await waitFor(() => {
      // Internal check: the useSettings query should have resolved.
      expect(localStorage.getItem('chat-model')).toBe('"claude-opus-4-6"');
    });
    // Give one more microtask for useSettings to populate.
    await new Promise((r) => setTimeout(r, 30));

    result.current.createTask({ projectId: 'p1', title: 'T' });
    await waitFor(() => expect(result.current.isCreating).toBe(false));
    expect(capturedBody).toMatchObject({ model: 'claude-opus-4-7' });
  });

  it('Sub-iterate C — sends concrete CLI model id (not alias) when hydrated from settings.defaultModel', async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.get('/api/settings', () =>
        HttpResponse.json({ data: { defaultModel: 'claude-opus-4-7' } }),
      ),
      http.post('/api/projects/:id/tasks', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          data: { id: 'new-task', projectId: 'p1', title: 'Test', description: '', status: 'pending', kanbanStatus: 'backlog', sessionId: 's1', createdAt: '', updatedAt: '' },
        });
      }),
      http.post('/api/projects/:id/classify', () =>
        HttpResponse.json({ data: { success: true } }),
      ),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCreateTask(), { wrapper });

    // Wait for settings hydration to populate localStorage.
    await waitFor(() => expect(localStorage.getItem('chat-model')).toBe('"claude-opus-4-7"'));

    result.current.createTask({ projectId: 'p1', title: 'Test' });
    await waitFor(() => expect(result.current.isCreating).toBe(false));

    expect(capturedBody).toMatchObject({ model: 'claude-opus-4-7' });
    // Critical contract: never send the coarse alias.
    const model = (capturedBody as unknown as { model?: string }).model;
    expect(model).not.toBe('opus');
    expect(model).not.toBe('sonnet');
    expect(model).not.toBe('haiku');
  });

  it('handles classify failure gracefully', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    server.use(
      http.post('/api/projects/:id/tasks', () =>
        HttpResponse.json({
          data: { id: 'new-task', projectId: 'p1', title: 'Test', description: 'Test', status: 'pending', kanbanStatus: 'backlog', sessionId: 's1', createdAt: '', updatedAt: '' },
        }),
      ),
      http.post('/api/projects/:id/classify', () =>
        HttpResponse.json({ error: 'Classification failed' }, { status: 500 }),
      ),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCreateTask(), { wrapper });

    result.current.createTask({ projectId: 'p1', title: 'Test' });

    // Task creation should succeed despite classify failure
    await waitFor(() => expect(result.current.isCreating).toBe(false));

    consoleSpy.mockRestore();
  });
});
