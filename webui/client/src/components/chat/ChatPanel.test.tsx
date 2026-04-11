import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatPanel } from './ChatPanel';

beforeEach(() => {
  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => ({
    onopen: null, onerror: null, onmessage: null, close: vi.fn(),
  })));
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
      expect(screen.getByPlaceholderText('Send a message...')).toBeInTheDocument();
    });
  });

  it('renders messages from API', async () => {
    renderPanel();
    await waitFor(() => {
      // MSW returns mockChatMessages with "Start building auth" (user) and assistant message
      expect(screen.getByText('Start building auth')).toBeInTheDocument();
    });
  });
});
