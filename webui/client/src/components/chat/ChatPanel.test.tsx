import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/mocks/server';
import { ChatPanel } from './ChatPanel';
import { useChatStore } from '../../stores/chatStore';
import { mockTasks } from '../../test/mocks/handlers';

beforeEach(() => {
  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => ({
    onopen: null, onerror: null, onmessage: null, close: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })));
  // Iterate 14.13 — chatStore is module-scoped Zustand state shared
  // across tests. Reset between cases so the awaitingInit derivation
  // doesn't see leftover systemInit data from a previous test that
  // hydrated the store via REST scan.
  useChatStore.setState({ systemInitByTask: {} });
});

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ChatPanel projectId="proj-1" taskId="task-1" />
    </QueryClientProvider>,
  );
}

describe('ChatPanel', () => {
  it('renders chat panel with input', async () => {
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
      // Iterate 2026-04-18 — assert on the input element, not a specific
      // placeholder string. The placeholder switches to "Waiting for
      // Claude…" during awaitingInit; the input's presence is what
      // matters for this smoke test.
      expect(
        screen.getByTestId('send-button').closest('form') ||
          screen.getByTestId('send-button').closest('div'),
      ).toBeInTheDocument();
    });
  });

  it('renders messages from API', async () => {
    renderPanel();
    await waitFor(() => {
      // MSW returns mockChatMessages with "Start building auth" (user) and assistant message
      expect(screen.getByText('Start building auth')).toBeInTheDocument();
    });
  });

  // Iterate 14.13 — spawn indicator. When the task exists and is in a
  // spawning/running state but no system/init has arrived yet (chatStore
  // empty for this taskKey), the empty chat area shows a spinner +
  // "Starting Claude…" instead of the static "Send a message" placeholder.
  describe('spawn indicator (iterate 14.13)', () => {
    it('renders spinner + "Starting Claude…" when task is running and chat history is empty', async () => {
      // Override the chat history to be empty so we hit the awaitingInit
      // empty-state branch. Task `task-1` is already `running` per mockTasks.
      server.use(
        http.get('/api/projects/:projectId/chat/:taskId', () =>
          HttpResponse.json({ data: [] }),
        ),
      );
      renderPanel();
      await waitFor(() => {
        expect(screen.getByTestId('chat-spawn-indicator')).toBeInTheDocument();
      });
      expect(screen.getByText('Starting Claude…')).toBeInTheDocument();
      // Static empty-state copy must be suppressed.
      expect(screen.queryByText('No messages yet.')).toBeNull();
    });

    it('clears the spawn indicator once chatStore.systemInit has a model', async () => {
      server.use(
        http.get('/api/projects/:projectId/chat/:taskId', () =>
          HttpResponse.json({ data: [] }),
        ),
      );
      // Pre-seed the store as if system/init had already arrived for this
      // task — the indicator must NOT render in that case.
      useChatStore.setState({
        systemInitByTask: { 'proj-1::task-1': { model: 'claude-opus-4-7' } },
      });
      renderPanel();
      // Give the panel a tick to settle on the empty chat history.
      await waitFor(() => {
        expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('chat-spawn-indicator')).toBeNull();
      // With systemInit present and messages empty + no awaiting flag,
      // the static empty-state shows.
      expect(screen.getByText('No messages yet.')).toBeInTheDocument();
    });

    // Iterate 14.14 — when the user creates a task with an initial
    // description, the user's prompt is already in the chat messages
    // array by the time the task detail page mounts. The 14.13
    // `messages.length === 0` gate silently suppressed the indicator
    // in the one case it was designed for. Spinner must still render
    // while awaiting the first system/init, even when the latest
    // message is the user's own prompt.
    it('renders spinner even when the last message is the user prompt (pre system/init)', async () => {
      server.use(
        http.get('/api/projects/:projectId/chat/:taskId', () =>
          HttpResponse.json({
            data: [
              {
                id: 'user-msg-1',
                taskId: 'task-1',
                type: 'user',
                content: 'Build me an auth system',
                timestamp: '2026-04-17T10:00:00Z',
              },
            ],
          }),
        ),
      );
      renderPanel();
      await waitFor(() => {
        expect(screen.getByTestId('chat-spawn-indicator')).toBeInTheDocument();
      });
      expect(screen.getByText('Starting Claude…')).toBeInTheDocument();
    });

    // Iterate 2026-04-18 modelswitch-spawn-ux — fresh tasks momentarily
    // have `task === undefined` because the tasks query hasn't landed
    // yet. Without this case covered, the spawn indicator doesn't render
    // for new tasks (the original user UAT report).
    it('renders spinner when task is undefined (fresh-mount race) and systemInit is empty', async () => {
      server.use(
        http.get('/api/projects/:projectId/chat/:taskId', () =>
          HttpResponse.json({ data: [] }),
        ),
        http.get('/api/projects/:projectId/tasks/:taskId', () =>
          // Simulate the server not knowing about the task yet — 404.
          HttpResponse.json({ error: 'Task not found' }, { status: 404 }),
        ),
      );
      renderPanel();
      await waitFor(() => {
        expect(screen.getByTestId('chat-spawn-indicator')).toBeInTheDocument();
      });
      expect(screen.getByText('Starting Claude…')).toBeInTheDocument();
    });

    // Iterate 2026-04-18 — the dezent "weisser Balken" leading-indicator
    // (chat-leading-indicator) was ambiguous (no visible text for the
    // user). It is now removed; the spawn indicator is the single
    // source of visual feedback during the boot gap.
    it('does NOT render the legacy chat-leading-indicator', async () => {
      server.use(
        http.get('/api/projects/:projectId/chat/:taskId', () =>
          HttpResponse.json({ data: [] }),
        ),
      );
      renderPanel();
      await waitFor(() =>
        expect(screen.getByTestId('chat-panel')).toBeInTheDocument(),
      );
      expect(screen.queryByTestId('chat-leading-indicator')).toBeNull();
    });

    it('does NOT render the spawn indicator for a done task', async () => {
      // Override the task lookup to return the `done` task (task-2),
      // and clear chat to be empty.
      server.use(
        http.get('/api/projects/:projectId/chat/:taskId', () =>
          HttpResponse.json({ data: [] }),
        ),
        http.get('/api/projects/:projectId/tasks/:taskId', () =>
          HttpResponse.json({ data: mockTasks.find((t) => t.id === 'task-2') }),
        ),
      );
      renderPanel();
      // Iterate 2026-04-18 — spawn indicator may render transiently while
      // the tasks query is loading. Wait for it to clear once the 'done'
      // task state settles.
      await waitFor(() => {
        expect(screen.queryByTestId('chat-spawn-indicator')).toBeNull();
      }, { timeout: 2000 });
    });
  });
});
