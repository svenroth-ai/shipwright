import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import InboxPage from './InboxPage';
import { server } from '../test/mocks/server';

beforeEach(() => {
  vi.stubGlobal('EventSource', vi.fn().mockImplementation(() => ({
    onopen: null, onerror: null, onmessage: null, close: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <InboxPage />
    </QueryClientProvider>,
  );
}

describe('InboxPage', () => {
  it('renders inbox heading', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Inbox')).toBeInTheDocument();
    });
  });

  it('renders pending questions from API', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Which auth provider?')).toBeInTheDocument();
    });
  });

  // ──────────────────────────────────────────────────────────────
  // Iterate 14.5 — notBlocked warning icon in inbox list
  // ──────────────────────────────────────────────────────────────

  it('does NOT render the notBlocked icon when flag is absent', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Which auth provider?')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('inbox-not-blocked-icon')).toBeNull();
  });

  it('renders the notBlocked warning icon when item has notBlocked=true', async () => {
    server.use(
      http.get('/api/inbox', () =>
        HttpResponse.json({
          data: [
            {
              id: 'inbox-flagged',
              projectId: 'proj-1',
              taskId: 'task-1',
              parts: [{ question: 'Was ignored?' }],
              status: 'pending',
              createdAt: '2026-04-14T10:00:00Z',
              notBlocked: true,
            },
          ],
        }),
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Was ignored?')).toBeInTheDocument();
    });
    expect(screen.getByTestId('inbox-not-blocked-icon')).toBeInTheDocument();
  });
});
