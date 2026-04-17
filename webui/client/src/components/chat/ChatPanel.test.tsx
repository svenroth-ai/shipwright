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
      expect(screen.getByPlaceholderText('Send a message or paste an image...')).toBeInTheDocument();
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
      await waitFor(() => {
        expect(screen.getByTestId('chat-panel')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('chat-spawn-indicator')).toBeNull();
    });
  });
});
